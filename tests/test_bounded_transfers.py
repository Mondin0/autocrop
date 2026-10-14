"""Tests for V2-07 bounded in-server transfers (contract first)."""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.jobs as jobs_mod
from app.jobs import JobService, MemoryBlobStore, MemoryStateStore, create_app

BLOCK = 8192


def _stored_zip(payload: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("big.bin", payload)
    return buf.getvalue()


def _payload(n: int = 64 * 1024) -> bytes:
    return bytes(range(256)) * (n // 256)


def _fake_block_copy(in_path, out_path, detector=None, ratio=None,
                     margin=0.15, on_progress=None):
    buf = bytearray()
    with open(in_path, "rb") as fh:
        while True:
            block = fh.read(BLOCK)
            if not block:
                break
            buf += block
    assert bytes(buf)[:2] == b"PK"
    if on_progress is not None:
        on_progress({"current": None, "processed": 1, "total": 1,
                     "saved": 1, "review": 0})
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("out.bin", _payload(32 * 1024))


class BoundedBlobs(MemoryBlobStore):
    """Memory double forbidding full-byte materialization in production."""

    def __init__(self) -> None:
        super().__init__()
        self.get_file_blocks: list[int] = []
        self.put_file_blocks: list[int] = []

    def get(self, key: str) -> bytes:
        raise AssertionError("production path must not call get()")

    def put(self, key: str, data: bytes) -> None:
        raise AssertionError("production path must not call put(bytes)")

    def get_file(self, key: str, dest: str) -> None:
        data = self._blobs[key]
        with open(dest, "wb") as fh:
            for i in range(0, len(data), BLOCK):
                block = data[i:i + BLOCK]
                self.get_file_blocks.append(len(block))
                fh.write(block)

    def put_file(self, key: str, path: str) -> None:
        buf = bytearray()
        with open(path, "rb") as fh:
            while True:
                block = fh.read(BLOCK)
                if not block:
                    break
                self.put_file_blocks.append(len(block))
                buf += block
        self._blobs[key] = bytes(buf)


def _bounded_service(**kw):
    kw.setdefault("now", lambda: 1000.0)
    kw.setdefault("process_fn", _fake_block_copy)
    return JobService(MemoryStateStore(), BoundedBlobs(), **kw)


def _post(client, payload: bytes):
    r = client.post("/api/jobs", files={"file": ("in.zip", payload, "application/zip")})
    assert r.status_code == 202, r.text
    return r.json()["job_id"]


def _complete(client, svc, payload: bytes) -> str:
    job_id = _post(client, payload)
    done = svc.run_next()
    assert done["status"] == "completed"
    return job_id


def test_f1_t1_worker_and_download_avoid_full_bytes(monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(
        AssertionError("production path must not call Path.read_bytes")))
    svc = _bounded_service()
    client = TestClient(create_app(svc))
    payload = _stored_zip(_payload())
    assert len(payload) > BLOCK
    job_id = _post(client, payload)
    assert len(svc.blobs.put_file_blocks) > 1
    assert sum(svc.blobs.put_file_blocks) == len(payload)
    svc.blobs.put_file_blocks.clear()
    done = svc.run_next()
    assert done["status"] == "completed"
    r = client.get(f"/api/jobs/{job_id}/result")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert f'attachment; filename="{job_id}.zip"' == r.headers["content-disposition"]
    tmp = tempfile.mkdtemp()
    try:
        expect = os.path.join(tmp, "expect.zip")
        svc.blobs.get_file(f"jobs/{job_id}/output.zip", expect)
        with open(expect, "rb") as fh:
            assert r.content == fh.read()
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    assert len(svc.blobs.get_file_blocks) > 1
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert zf.read("out.bin") == _payload(32 * 1024)


def test_f2_result_states_and_exact_ttl_boundary():
    now = [2000.0]
    svc = _bounded_service(now=lambda: now[0])
    client = TestClient(create_app(svc))
    assert client.get("/api/jobs/does-not-exist/result").status_code == 404
    job_id = _post(client, _stored_zip(b"0123456789"))
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
    rec = svc.state.load(job_id)
    rec["status"] = "processing"
    svc.state.save(job_id, rec)
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
    rec["status"] = "failed"
    rec["error"] = "bad"
    svc.state.save(job_id, rec)
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
    # fresh completed job for boundary checks
    svc2 = _bounded_service(now=lambda: now[0])
    client2 = TestClient(create_app(svc2))
    good = _post(client2, _stored_zip(b"0123456789"))
    svc2.run_next()
    now[0] += jobs_mod.RESULT_TTL_SECONDS
    assert client2.get(f"/api/jobs/{good}/result").status_code == 200
    now[0] += 1
    assert client2.get(f"/api/jobs/{good}/result").status_code == 410
    svc2.blobs._blobs.pop(f"jobs/{good}/output.zip")
    now[0] -= 1  # back inside ttl: missing blob reads as not-ready
    assert client2.get(f"/api/jobs/{good}/result").status_code == 409


def test_f2_range_requests_ignored_with_full_200():
    svc = _bounded_service()
    client = TestClient(create_app(svc))
    job_id = _complete(client, svc, _stored_zip(b"0123456789"))
    full = client.get(f"/api/jobs/{job_id}/result").content
    assert len(full) > 3
    for range_value in ("bytes=0-2", "bytes=bogus"):
        r = client.get(f"/api/jobs/{job_id}/result",
                       headers={"Range": range_value})
        assert r.status_code == 200, range_value
        assert r.content == full, range_value
        assert int(r.headers["content-length"]) == len(full), range_value


def test_f3_input_download_error_fails_without_partial():
    svc = _bounded_service()
    client = TestClient(create_app(svc))
    job_id = _post(client, _stored_zip(b"0123456789"))

    def _boom(key, dest):
        raise ConnectionError("rustfs-down")
    svc.blobs.get_file = _boom
    done = svc.run_next()
    assert done["status"] == "failed"
    assert "rustfs-down" in done["error"]
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
    assert f"jobs/{job_id}/output.zip" not in svc.blobs.keys()


def test_f3_output_upload_error_fails_without_partial():
    svc = _bounded_service()
    client = TestClient(create_app(svc))
    job_id = _post(client, _stored_zip(b"0123456789"))

    def _boom(key, path):
        raise ConnectionError("cannot-store")
    svc.blobs.put_file = _boom
    done = svc.run_next()
    assert done["status"] == "failed"
    assert "cannot-store" in done["error"]
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
    assert f"jobs/{job_id}/output.zip" not in svc.blobs.keys()


def test_f3_worker_partial_upload_cleans_temp_and_output(monkeypatch):
    svc = _bounded_service()
    client = TestClient(create_app(svc))
    job_id = _post(client, _stored_zip(b"0123456789"))
    created = []
    real_td = tempfile.TemporaryDirectory

    def _spy(*a, **k):
        td = real_td(*a, **k)
        created.append(td.name)
        return td
    monkeypatch.setattr(tempfile, "TemporaryDirectory", _spy)

    def _partial_then_boom(key, path):
        with open(path, "rb") as fh:
            svc.blobs._blobs[key] = fh.read(10)
        raise ConnectionError("store-broken")
    svc.blobs.put_file = _partial_then_boom
    done = svc.run_next()
    assert done["status"] == "failed"
    assert "store-broken" in done["error"]
    assert f"jobs/{job_id}/output.zip" not in svc.blobs.keys()
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
    assert created and not any(Path(p).exists() for p in created)


def _spy_mkstemp(monkeypatch):
    created = []
    real_mkstemp = tempfile.mkstemp

    def _spy(*a, **k):
        fd, name = real_mkstemp(*a, **k)
        created.append(name)
        return fd, name
    monkeypatch.setattr(tempfile, "mkstemp", _spy)
    return created


def _result_temps(created):
    return [p for p in created if "autocrop-result-" in p]


def test_f3_prepare_download_error_is_409_and_cleans_temp(monkeypatch):
    svc = _bounded_service()
    client = TestClient(create_app(svc))
    job_id = _post(client, _stored_zip(b"0123456789"))
    svc.run_next()
    created = _spy_mkstemp(monkeypatch)

    def _boom(key, dest):
        raise ConnectionError("read-failed")
    monkeypatch.setattr(svc.blobs, "get_file", _boom)
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
    temps = _result_temps(created)
    assert temps and not any(Path(p).exists() for p in temps)


def test_f3_success_cleans_server_temp(monkeypatch):
    svc = _bounded_service()
    client = TestClient(create_app(svc))
    job_id = _post(client, _stored_zip(b"0123456789"))
    svc.run_next()
    created = _spy_mkstemp(monkeypatch)
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 200
    temps = _result_temps(created)
    assert temps and not any(Path(p).exists() for p in temps)


def _http_scope(job_id: str) -> dict:
    raw = f"/api/jobs/{job_id}/result".encode()
    return {"type": "http", "http_version": "1.1", "method": "GET",
            "scheme": "http", "path": f"/api/jobs/{job_id}/result",
            "raw_path": raw, "query_string": b"", "root_path": "",
            "headers": [], "client": ("test", 50000), "server": ("test", 80)}


def _run_asgi(app, scope, receive, send):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(app(scope, receive, send))
    finally:
        loop.close()


def _asgi_send_failure(monkeypatch, exc):
    svc = _bounded_service()
    TestClient(create_app(svc))  # smoke: public app builds
    app = create_app(svc)
    posted = TestClient(app)
    job_id = _complete(posted, svc, _stored_zip(b"0123456789"))
    created = _spy_mkstemp(monkeypatch)
    seen = []

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def _send(message):
        seen.append(message)
        if message["type"] == "http.response.body":
            raise exc

    with pytest.raises(type(exc)):
        _run_asgi(app, _http_scope(job_id), _receive, _send)
    assert seen and seen[0]["type"] == "http.response.start"
    assert seen[0]["status"] == 200
    temps = _result_temps(created)
    assert temps and not any(Path(p).exists() for p in temps)


def test_f3_asgi_send_failure_cleans_temp(monkeypatch):
    _asgi_send_failure(monkeypatch, RuntimeError("client went away"))


def test_f3_asgi_cancelled_cleans_temp(monkeypatch):
    _asgi_send_failure(monkeypatch, asyncio.CancelledError("cancelled"))


class _GuardedBody:
    """S3 body double: only bounded reads of 1.._CHUNK bytes are served."""

    def __init__(self, data: bytes, fail_after: int | None = None) -> None:
        self._buf = io.BytesIO(data)
        self._fail_after = fail_after
        self._reads = 0
        self.sizes: list[int] = []
        self.closed: list[bool] = []

    def read(self, n=None):
        if n is None or n <= 0 or n > jobs_mod._CHUNK:
            raise AssertionError(f"bounded transfer must read 1..{jobs_mod._CHUNK}, got {n!r}")
        self._reads += 1
        if self._fail_after is not None and self._reads > self._fail_after:
            raise IOError("s3-read-broken")
        block = self._buf.read(n)
        self.sizes.append(len(block))
        return block

    def close(self):
        self.closed.append(True)


def _guarded_client(data: bytes, **kw):
    from app.jobs import S3BlobStore

    body = _GuardedBody(data, **kw)

    class _Client:
        def get_object(self, Bucket, Key):
            assert (Bucket, Key) == ("bkt", "jobs/j1/output.zip")
            return {"Body": body}

    return S3BlobStore(_Client(), "bkt"), body


def test_s3_get_file_streams_bounded_blocks_and_closes_body(tmp_path):
    data = _payload(2 * jobs_mod._CHUNK + 512)
    store, body = _guarded_client(data)
    dest = str(tmp_path / "out.zip")
    store.get_file("jobs/j1/output.zip", dest)
    assert Path(dest).read_bytes() == data
    nonzero = [s for s in body.sizes if s]
    assert len(nonzero) >= 3
    assert all(s <= jobs_mod._CHUNK for s in nonzero)
    assert sum(nonzero) == len(data)
    assert body.closed == [True]


def test_s3_get_file_read_failure_removes_partial_and_closes(tmp_path):
    data = _payload(2 * jobs_mod._CHUNK + 512)
    store, body = _guarded_client(data, fail_after=1)
    dest = str(tmp_path / "out.zip")
    with pytest.raises(IOError, match="s3-read-broken"):
        store.get_file("jobs/j1/output.zip", dest)
    assert not Path(dest).exists()
    assert body.closed == [True]


def test_s3_get_file_write_failure_removes_partial_and_closes(tmp_path, monkeypatch):
    import builtins

    real_open = open
    data = _payload(2 * jobs_mod._CHUNK + 512)
    store, body = _guarded_client(data)
    dest = str(tmp_path / "out.zip")

    class _FlakyFile:
        def __init__(self, fh):
            self._fh = fh
            self._writes = 0

        def write(self, block):
            self._writes += 1
            if self._writes > 1:
                raise OSError("disk-full")
            return self._fh.write(block)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self._fh.__exit__(*args)

    def _open(path, *args, **kwargs):
        fh = real_open(path, *args, **kwargs)
        if str(path) == dest and "w" in (args[0] if args else kwargs.get("mode", "")):
            return _FlakyFile(fh)
        return fh

    monkeypatch.setattr(builtins, "open", _open)
    with pytest.raises(OSError, match="disk-full"):
        store.get_file("jobs/j1/output.zip", dest)
    assert not Path(dest).exists()
    assert body.closed == [True]


def test_f4_bytes_api_kept_for_callers():
    svc = JobService(MemoryStateStore(), MemoryBlobStore(),
                     now=lambda: 1000.0, process_fn=_fake_block_copy)
    client = TestClient(create_app(svc))
    job_id = _post(client, _stored_zip(b"0123456789"))
    svc.run_next()
    via_bytes = svc.result_bytes(job_id)
    assert client.get(f"/api/jobs/{job_id}/result").content == via_bytes
    assert svc.submit(b"compat-bytes")["status"] == "queued"
    assert svc.get(job_id)["status"] == "completed"
    import app.archive as archive
    assert JobService(MemoryStateStore(), MemoryBlobStore()).process_fn is \
        archive.process_archive
