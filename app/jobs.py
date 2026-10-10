"""Jobs API and worker (stage V2-03).

FastAPI front-end plus a single-job worker around ``process_archive()``.
Queue/state live in a state store (Redis in deployment) and the input and
output ZIPs in a blob store (RustFS in deployment); the in-memory stores
below share the same interface for tests and local runs.
"""

from __future__ import annotations

import collections
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app.archive import process_archive
from fastapi import FastAPI, File, HTTPException, Response, UploadFile

MAX_UPLOAD_BYTES = 500 * 1024 * 1024
RESULT_TTL_SECONDS = 3 * 3600
_CHUNK = 1024 * 1024
_PUBLIC_FIELDS = ("job_id", "status", "current", "processed",
                  "total", "saved", "review", "error")


class JobNotFound(Exception):
    pass


class TooLargeError(Exception):
    pass


class NotReadyError(Exception):
    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


class ExpiredError(Exception):
    pass


def _public(rec: dict[str, Any]) -> dict[str, Any]:
    return {k: rec[k] for k in _PUBLIC_FIELDS}


class MemoryStateStore:
    """In-memory queue/state with the Redis store interface."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._queue: collections.deque[str] = collections.deque()

    def enqueue(self, job_id: str) -> None:
        self._queue.append(job_id)

    def dequeue(self) -> str | None:
        return self._queue.popleft() if self._queue else None

    def save(self, job_id: str, record: dict[str, Any]) -> None:
        self._jobs[job_id] = dict(record)

    def load(self, job_id: str) -> dict[str, Any] | None:
        rec = self._jobs.get(job_id)
        return dict(rec) if rec is not None else None

    def delete(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)

    def ids(self) -> list[str]:
        return list(self._jobs)


class MemoryBlobStore:
    """In-memory blobs with the RustFS/S3 store interface."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self._blobs[key] = bytes(data)

    def put_file(self, key: str, path: str) -> None:
        buf = bytearray()
        with open(path, "rb") as fh:
            while True:
                block = fh.read(_CHUNK)
                if not block:
                    break
                buf += block
        self._blobs[key] = bytes(buf)

    def get(self, key: str) -> bytes:
        return self._blobs[key]

    def delete(self, key: str) -> None:
        self._blobs.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._blobs

    def keys(self) -> list[str]:
        return list(self._blobs)


class RedisStateStore:
    """Redis queue/state. Real-service validation in a later stage."""

    def __init__(self, client: Any, prefix: str = "jobs") -> None:
        self._r = client
        self._prefix = prefix

    def _queue_key(self) -> str:
        return f"{self._prefix}:queue"

    def _job_key(self, job_id: str) -> str:
        return f"{self._prefix}:state:{job_id}"

    def _ids_key(self) -> str:
        return f"{self._prefix}:ids"

    def enqueue(self, job_id: str) -> None:
        self._r.rpush(self._queue_key(), job_id)
        self._r.sadd(self._ids_key(), job_id)

    def dequeue(self) -> str | None:
        value = self._r.lpop(self._queue_key())
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    def save(self, job_id: str, record: dict[str, Any]) -> None:
        self._r.hset(self._job_key(job_id), mapping={
            "status": record["status"],
            "current": record["current"] or "",
            "processed": record["processed"],
            "total": record["total"],
            "saved": record["saved"],
            "review": record["review"],
            "error": record["error"] or "",
            "finished_at": "" if record["finished_at"] is None else repr(record["finished_at"]),
            "input_key": record["input_key"],
            "output_key": record["output_key"],
        })
        self._r.sadd(self._ids_key(), job_id)

    def load(self, job_id: str) -> dict[str, Any] | None:
        raw = self._r.hgetall(self._job_key(job_id))
        if not raw:
            return None

        def field(name: str) -> str:
            value = raw.get(name.encode(), raw.get(name))
            if value is None:
                return ""
            return value.decode() if isinstance(value, bytes) else str(value)

        def num(name: str) -> int:
            return int(field(name) or 0)

        finished = field("finished_at")
        current = field("current") or None
        error = field("error") or None
        return {"job_id": job_id, "status": field("status") or "queued",
                "current": current, "processed": num("processed"),
                "total": num("total"), "saved": num("saved"),
                "review": num("review"), "error": error,
                "finished_at": float(finished) if finished else None,
                "input_key": field("input_key"),
                "output_key": field("output_key")}

    def delete(self, job_id: str) -> None:
        pipe = self._r.pipeline()
        pipe.delete(self._job_key(job_id))
        pipe.srem(self._ids_key(), job_id)
        pipe.execute()

    def ids(self) -> list[str]:
        members = self._r.smembers(self._ids_key())
        out = []
        for m in members:
            out.append(m.decode() if isinstance(m, bytes) else str(m))
        return out


class S3BlobStore:
    """S3-compatible (RustFS) blobs. Real-service validation in a later stage."""

    def __init__(self, client: Any, bucket: str) -> None:
        self._s3 = client
        self._bucket = bucket

    def put(self, key: str, data: bytes) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data)

    def put_file(self, key: str, path: str) -> None:
        self._s3.upload_file(str(path), self._bucket, key)

    def get(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self._bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
        except Exception as exc:
            if "404" in str(exc) or "Not Found" in str(exc):
                return False
            raise
        return True


class JobService:
    def __init__(self, state: Any, blobs: Any, *,
                 now: Callable[[], float] | None = None,
                 max_upload_bytes: int = MAX_UPLOAD_BYTES,
                 ttl_seconds: float = RESULT_TTL_SECONDS,
                 process_fn: Any | None = None) -> None:
        self.state = state
        self.blobs = blobs
        self._now = now or time.time
        self.max_upload_bytes = max_upload_bytes
        self.ttl_seconds = ttl_seconds
        self.process_fn = process_fn or process_archive

    def _new_record(self) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        return {"job_id": job_id, "status": "queued", "current": None,
                "processed": 0, "total": 0, "saved": 0, "review": 0,
                "error": None, "finished_at": None,
                "input_key": f"jobs/{job_id}/input.zip",
                "output_key": f"jobs/{job_id}/output.zip"}

    def submit(self, data: bytes) -> dict[str, Any]:
        if len(data) > self.max_upload_bytes:
            raise TooLargeError(f"upload exceeds {self.max_upload_bytes} bytes")
        record = self._new_record()
        self.blobs.put(record["input_key"], data)
        self.state.save(record["job_id"], record)
        self.state.enqueue(record["job_id"])
        return _public(record)

    def submit_file(self, path: str) -> dict[str, Any]:
        import os

        if os.path.getsize(path) > self.max_upload_bytes:
            raise TooLargeError(f"upload exceeds {self.max_upload_bytes} bytes")
        record = self._new_record()
        self.blobs.put_file(record["input_key"], path)
        self.state.save(record["job_id"], record)
        self.state.enqueue(record["job_id"])
        return _public(record)

    def get(self, job_id: str) -> dict[str, Any]:
        rec = self.state.load(job_id)
        if rec is None:
            raise JobNotFound(job_id)
        return _public(rec)

    def run_next(self, detector: Any = None, ratio: Any = None,
                 margin: float = 0.15) -> dict[str, Any] | None:
        job_id = self.state.dequeue()
        if job_id is None:
            return None
        rec = self.state.load(job_id)
        if rec is None:
            return None
        rec["status"] = "processing"
        self.state.save(job_id, rec)

        def _on_progress(event: dict[str, Any]) -> None:
            for key in ("current", "processed", "total", "saved", "review"):
                rec[key] = event[key]
            self.state.save(job_id, rec)

        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "input.zip"
            out_path = Path(tmp) / "output.zip"
            try:
                in_path.write_bytes(self.blobs.get(rec["input_key"]))
            except Exception as exc:
                return self._fail(job_id, rec, f"cannot load input: {exc}")
            try:
                self.process_fn(in_path, out_path, detector, ratio, margin,
                                on_progress=_on_progress)
            except Exception as exc:
                return self._fail(job_id, rec, str(exc) or repr(exc))
            try:
                self.blobs.put(rec["output_key"], out_path.read_bytes())
            except Exception as exc:
                return self._fail(job_id, rec, f"cannot store result: {exc}")
            rec["status"] = "completed"
            rec["finished_at"] = self._now()
            self.state.save(job_id, rec)
            return _public(rec)

    def _fail(self, job_id: str, rec: dict[str, Any], message: str) -> dict[str, Any]:
        rec["status"] = "failed"
        rec["error"] = message
        try:
            self.blobs.delete(rec["output_key"])
        except Exception:
            pass
        self.state.save(job_id, rec)
        return _public(rec)

    def result_bytes(self, job_id: str) -> bytes:
        rec = self.state.load(job_id)
        if rec is None:
            raise JobNotFound(job_id)
        if rec["status"] != "completed":
            raise NotReadyError(rec["status"])
        finished = rec.get("finished_at") or 0
        if self._now() - finished > self.ttl_seconds:
            raise ExpiredError(job_id)
        try:
            return self.blobs.get(rec["output_key"])
        except Exception:
            raise NotReadyError("missing result")

    def cleanup(self) -> int:
        removed = 0
        for job_id in list(self.state.ids()):
            rec = self.state.load(job_id)
            if not rec or rec["status"] != "completed":
                continue
            if self._now() - (rec.get("finished_at") or 0) <= self.ttl_seconds:
                continue
            for key in (rec["input_key"], rec["output_key"]):
                try:
                    self.blobs.delete(key)
                except Exception:
                    pass
            self.state.delete(job_id)
            removed += 1
        return removed


def create_app(service: JobService) -> Any:
    app = FastAPI(title="autocrop jobs")

    @app.post("/api/jobs", status_code=202)
    async def create_job(file: UploadFile = File(...)):  # type: ignore[no-untyped-def]
        import os

        fd, tmp_name = tempfile.mkstemp(suffix=".zip")
        try:
            size = 0
            with os.fdopen(fd, "wb") as fh:
                while True:
                    chunk = await file.read(_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > service.max_upload_bytes:
                        raise HTTPException(
                            status_code=413, detail="upload exceeds 500 MiB")
                    fh.write(chunk)
            try:
                record = service.submit_file(tmp_name)
            except TooLargeError:
                raise HTTPException(
                    status_code=413, detail="upload exceeds 500 MiB")
            return {"job_id": record["job_id"], "status": record["status"]}
        finally:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):  # type: ignore[no-untyped-def]
        try:
            return service.get(job_id)
        except JobNotFound:
            raise HTTPException(status_code=404, detail="unknown job")

    @app.get("/api/jobs/{job_id}/result")
    def get_result(job_id: str):  # type: ignore[no-untyped-def]
        try:
            data = service.result_bytes(job_id)
        except JobNotFound:
            raise HTTPException(status_code=404, detail="unknown job")
        except ExpiredError:
            raise HTTPException(status_code=410, detail="result expired")
        except NotReadyError as exc:
            raise HTTPException(status_code=409, detail=f"not ready: {exc.status}")
        return Response(content=data, media_type="application/zip",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{job_id}.zip"'})

    return app
