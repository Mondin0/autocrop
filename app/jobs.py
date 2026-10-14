"""Jobs API and worker (stage V2-03).

FastAPI front-end plus a single-job worker around ``process_archive()``.
Queue/state live in a state store (Redis in deployment) and the input and
output ZIPs in a blob store (RustFS in deployment); the in-memory stores
below share the same interface for tests and local runs.
"""

from __future__ import annotations

import collections
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app.archive import process_archive
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

MAX_UPLOAD_BYTES = 500 * 1024 * 1024
RESULT_TTL_SECONDS = 3 * 3600
_CHUNK = 1024 * 1024
INTERRUPTED_ERROR = ("worker interrupted before finishing; "
                     "please submit the ZIP again")
_JOB_PREFIX = "jobs/"
_PUBLIC_FIELDS = ("job_id", "status", "current", "processed",
                  "total", "saved", "review", "error")

log = logging.getLogger("autocrop.jobs")


class JobNotFound(Exception):
    pass


class PendingClaimsError(Exception):
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


def _drop(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _job_object_id(key: str) -> str | None:
    """Return the job UUID when ``key`` is one of its owned objects."""
    parts = key.split("/")
    if len(parts) != 3 or parts[0] != "jobs":
        return None
    if parts[2] not in ("input.zip", "output.zip"):
        return None
    try:
        uuid.UUID(parts[1])
    except ValueError:
        return None
    return parts[1]


class MemoryStateStore:
    """In-memory queue/state with the Redis store interface."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._queue: collections.deque[str] = collections.deque()
        self._active: list[str] = []

    def enqueue(self, job_id: str) -> None:
        self._queue.append(job_id)

    def dequeue(self) -> str | None:
        return self._queue.popleft() if self._queue else None

    def claim(self) -> str | None:
        if not self._queue:
            return None
        job_id = self._queue.popleft()
        self._active.append(job_id)
        return job_id

    def release(self, job_id: str) -> None:
        try:
            self._active.remove(job_id)
        except ValueError:
            pass

    def claimed(self) -> list[str]:
        return list(self._active)

    def unqueue(self, job_id: str) -> bool:
        found = False
        try:
            while True:
                self._queue.remove(job_id)
                found = True
        except ValueError:
            pass
        return found

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

    def __init__(self, *, now: Callable[[], float] | None = None) -> None:
        self._blobs: dict[str, bytes] = {}
        self._mtimes: dict[str, float] = {}
        self._now = now or time.time

    def put(self, key: str, data: bytes) -> None:
        self._blobs[key] = bytes(data)
        self._mtimes[key] = self._now()

    def put_file(self, key: str, path: str) -> None:
        buf = bytearray()
        with open(path, "rb") as fh:
            while True:
                block = fh.read(_CHUNK)
                if not block:
                    break
                buf += block
        self._blobs[key] = bytes(buf)
        self._mtimes[key] = self._now()

    def get(self, key: str) -> bytes:
        return self._blobs[key]

    def get_file(self, key: str, dest: str) -> None:
        data = self._blobs[key]
        with open(dest, "wb") as fh:
            for i in range(0, len(data), _CHUNK):
                fh.write(data[i:i + _CHUNK])

    def delete(self, key: str) -> None:
        self._blobs.pop(key, None)
        self._mtimes.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._blobs

    def keys(self) -> list[str]:
        return list(self._blobs)

    def scan_prefix(self, prefix: str) -> list[tuple[str, float | None]]:
        return [(k, self._mtimes.get(k)) for k in self._blobs
                if k.startswith(prefix)]


class RedisStateStore:
    """Redis queue/state. Real-service validation in a later stage."""

    def __init__(self, client: Any, prefix: str = "jobs") -> None:
        self._r = client
        self._prefix = prefix

    def _queue_key(self) -> str:
        return f"{self._prefix}:queue"

    def _active_key(self) -> str:
        return f"{self._prefix}:active"

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

    def claim(self) -> str | None:
        job_id = self._r.lmove(self._queue_key(), self._active_key(),
                               "LEFT", "RIGHT")
        if job_id is None:
            return None
        return job_id.decode() if isinstance(job_id, bytes) else str(job_id)

    def release(self, job_id: str) -> None:
        self._r.lrem(self._active_key(), 0, job_id)

    def claimed(self) -> list[str]:
        items = self._r.lrange(self._active_key(), 0, -1)
        return [m.decode() if isinstance(m, bytes) else str(m)
                for m in items]

    def unqueue(self, job_id: str) -> bool:
        return bool(self._r.lrem(self._queue_key(), 0, job_id))

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

    def get_file(self, key: str, dest: str) -> None:
        body = self._s3.get_object(Bucket=self._bucket, Key=key)["Body"]
        try:
            with open(dest, "wb") as fh:
                while True:
                    block = body.read(_CHUNK)
                    if not block:
                        break
                    fh.write(block)
        except Exception:
            try:
                os.unlink(dest)
            except OSError:
                pass
            raise
        finally:
            try:
                body.close()
            except Exception:
                pass

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

    def scan_prefix(self, prefix: str) -> list[tuple[str, float | None]]:
        found: list[tuple[str, float | None]] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                modified = obj.get("LastModified")
                ts = modified.timestamp() if hasattr(modified, "timestamp") \
                    else None
                found.append((obj["Key"], ts))
        return found


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
        try:
            self.blobs.put(record["input_key"], data)
        except Exception:
            self._revert_new(record, "upload")
            raise
        try:
            self.state.save(record["job_id"], record)
        except Exception:
            self._revert_new(record, "save")
            raise
        try:
            self.state.enqueue(record["job_id"])
        except Exception:
            self._revert_new(record, "enqueue")
            raise
        return _public(record)

    def submit_file(self, path: str) -> dict[str, Any]:
        import os

        if os.path.getsize(path) > self.max_upload_bytes:
            raise TooLargeError(f"upload exceeds {self.max_upload_bytes} bytes")
        record = self._new_record()
        try:
            self.blobs.put_file(record["input_key"], path)
        except Exception:
            self._revert_new(record, "upload")
            raise
        try:
            self.state.save(record["job_id"], record)
        except Exception:
            self._revert_new(record, "save")
            raise
        try:
            self.state.enqueue(record["job_id"])
        except Exception:
            self._revert_new(record, "enqueue")
            raise
        return _public(record)

    def _revert_new(self, record: dict[str, Any], step: str) -> None:
        job_id = record["job_id"]
        if step == "enqueue":
            taken = self._took_back_from_queue(job_id)
            if taken is True or (taken is False
                                 and not self._worker_may_own(job_id)):
                # Removed our only queued copy, or the enqueue never took
                # effect with no worker involved. Unknown take-back and
                # worker-owned ids are preserved (already logged).
                self._delete_own(record, step)
            return
        # Never queued: no worker can own it through the queue.
        unqueue = getattr(self.state, "unqueue", None)
        if unqueue is not None:
            try:
                unqueue(job_id)
            except Exception:
                log.exception("submit rollback: cannot unqueue %s "
                              "after %s failure", job_id, step)
        self._delete_own(record, step)

    def _delete_own(self, record: dict[str, Any], step: str) -> None:
        job_id = record["job_id"]
        try:
            self.state.delete(job_id)
        except Exception:
            log.exception("submit rollback: cannot delete state for %s "
                          "after %s failure", job_id, step)
        try:
            self.blobs.delete(record["input_key"])
        except Exception:
            log.exception("submit rollback: cannot delete object for %s "
                          "after %s failure; orphan sweep will retry",
                          job_id, step)

    def _worker_may_own(self, job_id: str) -> bool:
        """Whether the single worker may own this id after take-back.

        Runs only after the atomic take-back found nothing queued, so no
        future claim is possible: the id is unknown to anyone else and
        absent from the queue. A present claim or a terminal state proves
        past worker involvement (preserve); anything unreadable also
        preserves. Only a readable non-terminal unclaimed state means the
        enqueue never took effect.
        """
        try:
            claimed = getattr(self.state, "claimed", None)
            owned = job_id in (claimed() or []) if claimed is not None \
                else False
        except Exception:
            log.exception("submit rollback: cannot list claims for %s; "
                          "keeping state and objects", job_id)
            return True
        if owned:
            log.warning("submit rollback: %s already claimed; keeping "
                        "state and objects", job_id)
            return True
        try:
            rec = self.state.load(job_id)
        except Exception:
            log.exception("submit rollback: cannot verify state for %s; "
                          "keeping state and objects", job_id)
            return True
        if rec is not None and rec.get("status") in ("completed", "failed"):
            log.warning("submit rollback: %s already terminal; keeping "
                        "state and objects", job_id)
            return True
        return False

    def _took_back_from_queue(self, job_id: str) -> bool | None:
        """Atomically remove our own id from the pending queue.

        ``True`` removed the only queued copy, so the worker can never
        claim it afterwards and deleting state/object is safe. ``False``
        means the id is absent: either the enqueue never took effect or
        the worker already took it (distinguished afterwards). ``None``
        means the removal itself failed and nothing is known: preserve.
        There is no separate prior check (no TOCTOU): each store removes
        atomically, so exactly one side wins the id.
        """
        unqueue = getattr(self.state, "unqueue", None)
        if unqueue is None:
            log.warning("submit rollback: no atomic take-back for %s; "
                        "reverting without coordination", job_id)
            return True
        try:
            taken = bool(unqueue(job_id))
        except Exception:
            log.exception("submit rollback: cannot take back %s; keeping "
                          "state and objects", job_id)
            return None
        if not taken:
            log.warning("submit rollback: %s not queued (enqueue may not "
                        "have taken effect or worker may own it)",
                        job_id)
        return taken

    def get(self, job_id: str) -> dict[str, Any]:
        rec = self.state.load(job_id)
        if rec is None:
            raise JobNotFound(job_id)
        return _public(rec)

    def reconcile(self) -> int:
        """Fail jobs claimed by a previous run without a terminal state.

        Claimed ids with a persisted terminal keep their result; only the
        stale claim is released. Ids whose state cannot be loaded or saved
        keep their claim for a later retry.
        """
        claimed = getattr(self.state, "claimed", lambda: [])() or []
        fixed = 0
        for job_id in list(claimed):
            try:
                rec = self.state.load(job_id)
            except Exception:
                log.exception("reconcile: cannot load %s; keeping claim",
                              job_id)
                continue
            if rec is None or rec.get("status") in ("completed", "failed"):
                self._release_quiet(job_id)
                continue
            rec["status"] = "failed"
            rec["current"] = None
            rec["error"] = INTERRUPTED_ERROR
            rec["finished_at"] = self._now()
            try:
                self.state.save(job_id, rec)
            except Exception:
                log.exception("reconcile: cannot persist interruption for "
                              "%s; keeping claim", job_id)
                continue
            self._release_quiet(job_id)
            fixed += 1
        return fixed

    def _release_quiet(self, job_id: str) -> None:
        release = getattr(self.state, "release", None)
        if release is None:
            return
        try:
            release(job_id)
        except Exception:
            log.exception("cannot release claim for %s; reconcile will "
                          "retry", job_id)

    def run_next(self, detector: Any = None, ratio: Any = None,
                 margin: float = 0.15) -> dict[str, Any] | None:
        claim = getattr(self.state, "claim", None)
        if claim is None:
            job_id = self.state.dequeue()
        else:
            try:
                job_id = claim()
            except Exception:
                log.exception("cannot claim next job; keeping queue")
                raise
        if job_id is None:
            return None
        try:
            rec = self.state.load(job_id)
        except Exception:
            log.exception("cannot load %s; keeping claim", job_id)
            raise
        if rec is None:
            self._release_quiet(job_id)
            return None
        rec["status"] = "processing"
        try:
            self.state.save(job_id, rec)
        except Exception:
            log.exception("cannot persist processing state for %s; keeping "
                          "claim", job_id)
            raise

        def _on_progress(event: dict[str, Any]) -> None:
            for key in ("current", "processed", "total", "saved", "review"):
                rec[key] = event[key]
            self.state.save(job_id, rec)

        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "input.zip"
            out_path = Path(tmp) / "output.zip"
            try:
                self.blobs.get_file(rec["input_key"], str(in_path))
            except Exception as exc:
                return self._fail(job_id, rec, f"cannot load input: {exc}")
            try:
                self.process_fn(in_path, out_path, detector, ratio, margin,
                                on_progress=_on_progress)
            except Exception as exc:
                return self._fail(job_id, rec, str(exc) or repr(exc))
            try:
                self.blobs.put_file(rec["output_key"], str(out_path))
            except Exception as exc:
                return self._fail(job_id, rec, f"cannot store result: {exc}")
            rec["status"] = "completed"
            rec["finished_at"] = self._now()
            try:
                self.state.save(job_id, rec)
            except Exception:
                log.exception("cannot persist completed state for %s; "
                              "keeping claim", job_id)
                raise
            self._release_quiet(job_id)
            return _public(rec)

    def _fail(self, job_id: str, rec: dict[str, Any],
              message: str) -> dict[str, Any]:
        rec["status"] = "failed"
        rec["current"] = None
        rec["error"] = message
        rec["finished_at"] = self._now()
        try:
            self.blobs.delete(rec["output_key"])
        except Exception:
            pass
        self.state.save(job_id, rec)
        self._release_quiet(job_id)
        return _public(rec)

    def _require_completed(self, job_id: str) -> dict[str, Any]:
        rec = self.state.load(job_id)
        if rec is None:
            raise JobNotFound(job_id)
        if rec["status"] != "completed":
            raise NotReadyError(rec["status"])
        finished = rec.get("finished_at") or 0
        if self._now() - finished > self.ttl_seconds:
            raise ExpiredError(job_id)
        return rec

    def result_bytes(self, job_id: str) -> bytes:
        rec = self._require_completed(job_id)
        try:
            return self.blobs.get(rec["output_key"])
        except Exception:
            raise NotReadyError("missing result")

    def result_to_file(self, job_id: str, dest: str) -> dict[str, Any]:
        rec = self._require_completed(job_id)
        try:
            self.blobs.get_file(rec["output_key"], dest)
        except Exception:
            raise NotReadyError("missing result")
        return _public(rec)

    def cleanup(self) -> int:
        removed = 0
        for job_id in list(self.state.ids()):
            try:
                rec = self.state.load(job_id)
            except Exception:
                log.exception("cleanup: cannot load %s; will retry", job_id)
                continue
            if rec is None or rec.get("status") not in ("completed",
                                                        "failed"):
                continue
            if rec.get("finished_at") is None:
                rec["finished_at"] = self._now()
                try:
                    self.state.save(job_id, rec)
                except Exception:
                    log.exception("cleanup: cannot stamp retention for %s; "
                                  "will retry", job_id)
                continue
            if self._now() - rec["finished_at"] <= self.ttl_seconds:
                continue
            try:
                self.blobs.delete(rec["input_key"])
                self.blobs.delete(rec["output_key"])
            except Exception:
                log.exception("cleanup: cannot delete objects for %s; "
                              "keeping record", job_id)
                continue
            try:
                self.state.delete(job_id)
            except Exception:
                log.exception("cleanup: cannot delete state for %s; will "
                              "retry", job_id)
                continue
            self._release_quiet(job_id)
            removed += 1
        try:
            self._sweep_orphans()
        except Exception:
            log.exception("cleanup: orphan sweep failed; will retry")
        return removed

    def _sweep_orphans(self) -> int:
        """Delete aged ``jobs/`` blobs no job or claim references anymore.

        Only ``input.zip``/``output.zip`` of a valid UUID can be owned;
        anything else is foreign and kept. Absence of state is verified by
        a direct load per UUID: a read failure keeps the object, even when
        the listing omits the job.
        """
        scan = getattr(self.blobs, "scan_prefix", None)
        if scan is not None:
            entries = scan(_JOB_PREFIX)
        else:
            entries = [(k, None) for k in self.blobs.keys()
                       if k.startswith(_JOB_PREFIX)]
        claimed = getattr(self.state, "claimed", lambda: [])() or []
        guarded = set(claimed)
        swept = 0
        for key, mtime in entries:
            job_id = _job_object_id(key)
            if job_id is None or job_id in guarded:
                continue
            try:
                rec = self.state.load(job_id)
            except Exception:
                log.exception("cleanup: cannot verify %s; keeping object",
                              key)
                continue
            if rec is not None:
                continue
            if mtime is None or self._now() - mtime <= self.ttl_seconds:
                continue
            try:
                self.blobs.delete(key)
            except Exception:
                log.exception("cleanup: cannot delete orphan %s; will "
                              "retry", key)
                continue
            swept += 1
        return swept


class _ResultFileResponse(FileResponse):
    """FileResponse that always removes its temp file, even if send fails.

    Starlette only runs ``background`` after a successful send, so a plain
    ``BackgroundTask`` cleanup would leak the temp on client disconnect.
    ``Range`` is ignored on purpose: this endpoint always serves the whole
    ZIP with 200, as before.
    """

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            headers = [(k, v) for k, v in scope.get("headers", [])
                       if k.lower() != b"range"]
            await super().__call__({**scope, "headers": headers},
                                   receive, send)
        finally:
            _drop(str(self.path))


def create_app(service: JobService) -> Any:
    app = FastAPI(title="autocrop jobs")

    @app.get("/health")
    def health():  # type: ignore[no-untyped-def]
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def home():  # type: ignore[no-untyped-def]
        return RedirectResponse("http://localhost:8080")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():  # type: ignore[no-untyped-def]
        return Response(status_code=204)

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
        fd, tmp_name = tempfile.mkstemp(suffix=".zip", prefix="autocrop-result-")
        os.close(fd)
        try:
            service.result_to_file(job_id, tmp_name)
        except JobNotFound:
            _drop(tmp_name)
            raise HTTPException(status_code=404, detail="unknown job")
        except ExpiredError:
            _drop(tmp_name)
            raise HTTPException(status_code=410, detail="result expired")
        except NotReadyError as exc:
            _drop(tmp_name)
            raise HTTPException(status_code=409, detail=f"not ready: {exc.status}")
        except Exception:
            _drop(tmp_name)
            raise
        return _ResultFileResponse(tmp_name, media_type="application/zip",
                                   filename=f"{job_id}.zip")

    return app
