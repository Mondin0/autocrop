"""Tests for V2-03 Redis/RustFS adapters with controlled clients."""

from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.jobs import (RESULT_TTL_SECONDS, JobService, RedisStateStore,
                      S3BlobStore, MemoryBlobStore, MemoryStateStore,
                      create_app)


class FakeRedis:
    """Minimal Redis-like client storing bytes, as redis-py returns."""

    def __init__(self):
        self.lists: dict[str, list[bytes]] = {}
        self.hashes: dict[str, dict[bytes, bytes]] = {}
        self.sets: dict[str, set[bytes]] = {}

    @staticmethod
    def _enc(value):
        return value.encode() if isinstance(value, str) else bytes(value)

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(self._enc(value))

    def lpop(self, key):
        items = self.lists.get(key, [])
        return items.pop(0) if items else None

    def sadd(self, key, *values):
        self.sets.setdefault(key, set()).update(self._enc(v) for v in values)

    def srem(self, key, *values):
        current = self.sets.get(key, set())
        for v in values:
            current.discard(self._enc(v))

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def hset(self, key, mapping=None, **kwargs):
        dest = self.hashes.setdefault(key, {})
        for k, v in dict(mapping or {}, **kwargs).items():
            dest[self._enc(str(k))] = self._enc(str(v))

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def delete(self, key):
        self.hashes.pop(key, None)
        self.lists.pop(key, None)
        self.sets.pop(key, None)

    def pipeline(self):
        return _FakePipe(self)


class _FakePipe:
    def __init__(self, client):
        self._client = client
        self._ops = []

    def delete(self, key):
        self._ops.append(("delete", key))
        return self

    def srem(self, key, *values):
        self._ops.append(("srem", key, values))
        return self

    def execute(self):
        for op in self._ops:
            if op[0] == "delete":
                self._client.delete(op[1])
            else:
                self._client.srem(op[1], *op[2])
        self._ops = []
        return []


class S3Error(Exception):
    pass


class FakeS3:
    """Minimal S3-like client keyed by (bucket, key)."""

    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, Bucket, Key, Body):
        data = Body.read() if hasattr(Body, "read") else bytes(Body)
        self.objects[(Bucket, Key)] = data
        return {}

    def get_object(self, Bucket, Key):
        try:
            return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}
        except KeyError:
            raise S3Error(f"NoSuchKey: {Key}")

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)
        return {}

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise S3Error("404 Not Found")
        return {}

    def upload_file(self, Filename, Bucket, Key):
        with open(Filename, "rb") as fh:
            self.objects[(Bucket, Key)] = fh.read()
        return None


def _record(**kw):
    base = {"job_id": "j1", "status": "queued", "current": None,
            "processed": 0, "total": 0, "saved": 0, "review": 0,
            "error": None, "finished_at": None,
            "input_key": "jobs/j1/input.zip", "output_key": "jobs/j1/output.zip"}
    base.update(kw)
    return base


def _ok_process(in_path, out_path, detector=None, ratio=None, margin=0.15,
                on_progress=None):
    if on_progress is not None:
        on_progress({"current": None, "processed": 0, "total": 1,
                     "saved": 0, "review": 0})
        on_progress({"current": None, "processed": 1, "total": 1,
                     "saved": 1, "review": 0})
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.jpg", b"out")
    return {"processed": 1, "saved": 1, "review": 0, "skipped": 0}


def test_redis_queue_push_pop_fifo():
    store = RedisStateStore(FakeRedis())
    assert store.dequeue() is None
    store.enqueue("a")
    store.enqueue("b")
    store.enqueue("c")
    assert store.dequeue() == "a"
    assert store.dequeue() == "b"
    assert store.dequeue() == "c"
    assert store.dequeue() is None


def test_redis_state_round_trip():
    store = RedisStateStore(FakeRedis())
    rec = _record(status="processing", current="a.jpg", processed=1, total=2,
                  saved=1, review=0)
    store.save("j1", rec)
    assert store.load("j1") == rec
    failed = _record(status="failed", error="bad zip", finished_at=1234.5,
                     processed=0, total=0)
    store.save("j1", failed)
    assert store.load("j1") == failed
    assert store.load("missing") is None
    store.delete("j1")
    assert store.load("j1") is None
    assert store.ids() == []


def test_redis_state_ids_track_enqueued():
    store = RedisStateStore(FakeRedis())
    store.save("j1", _record())
    store.enqueue("j1")
    store.save("j2", _record(job_id="j2"))
    store.enqueue("j2")
    assert sorted(store.ids()) == ["j1", "j2"]


def test_redis_state_ttl_cleanup_via_service():
    now = [5000.0]
    svc = JobService(RedisStateStore(FakeRedis()), MemoryBlobStore(),
                     now=lambda: now[0], process_fn=_ok_process)
    svc.submit(b"zip-1")
    svc.run_next()
    now[0] += RESULT_TTL_SECONDS + 1
    keep = svc.submit(b"zip-2")["job_id"]
    svc.run_next()
    assert svc.cleanup() == 1
    assert svc.state.ids() == [keep]


def test_s3_put_get_delete_exists():
    store = S3BlobStore(FakeS3(), "bkt")
    assert not store.exists("jobs/j1/input.zip")
    store.put("jobs/j1/input.zip", b"data")
    assert store.exists("jobs/j1/input.zip")
    assert store.get("jobs/j1/input.zip") == b"data"
    store.delete("jobs/j1/input.zip")
    assert not store.exists("jobs/j1/input.zip")
    with pytest.raises(Exception):
        store.get("jobs/j1/input.zip")


def test_s3_exists_propagates_non_404():
    class _Bad(FakeS3):
        def head_object(self, Bucket, Key):
            raise S3Error("500 Internal Error")

    with pytest.raises(S3Error):
        S3BlobStore(_Bad(), "bkt").exists("jobs/j1/input.zip")


def test_s3_put_file_uploads_from_disk(tmp_path):
    fake = FakeS3()
    store = S3BlobStore(fake, "bkt")
    src = tmp_path / "in.zip"
    src.write_bytes(bytes(range(256)) * 200)
    store.put_file("jobs/j1/input.zip", str(src))
    assert ("bkt", "jobs/j1/input.zip") in fake.objects
    assert store.get("jobs/j1/input.zip") == src.read_bytes()


def test_redis_s3_full_cycle_via_http():
    now = [7000.0]
    fake_s3 = FakeS3()
    svc = JobService(RedisStateStore(FakeRedis()),
                     S3BlobStore(fake_s3, "autocrop"),
                     now=lambda: now[0], process_fn=_ok_process)
    client = TestClient(create_app(svc))
    r = client.post("/api/jobs", files={"file": ("in.zip", b"zip-bytes",
                                                "application/zip")})
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    assert fake_s3.objects[("autocrop", f"jobs/{job_id}/input.zip")] == b"zip-bytes"
    done = svc.run_next()
    assert done["status"] == "completed"
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"
    dl = client.get(f"/api/jobs/{job_id}/result")
    assert dl.status_code == 200
    assert dl.content == fake_s3.objects[("autocrop", f"jobs/{job_id}/output.zip")]
