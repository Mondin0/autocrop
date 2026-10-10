"""Tests for V2-03 API and worker (contract first)."""

from __future__ import annotations

import io
import pathlib
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.jobs as jobs
from app.jobs import JobService, MemoryBlobStore, MemoryStateStore, create_app


class Stub:
    def __init__(self, by_size=None, default=()):
        self.by_size = dict(by_size or {})
        self.default = list(default)

    def detect_people(self, image):
        return list(self.by_size.get(tuple(image.size), self.default))


def make_jpg_bytes(width=800, height=600, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "JPEG")
    return buf.getvalue()


def write_zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def two_photo_zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("b.jpg", make_jpg_bytes(500, 500, color=(10, 200, 10)))
        zf.writestr("a.jpg", make_jpg_bytes(800, 600))
    return buf.getvalue()


def two_photo_stub():
    return Stub(by_size={(800, 600): [(100, 100, 300, 300)], (500, 500): []})


def make_service(**kw):
    now = kw.pop("now_list", [1000.0])
    kw.setdefault("now", lambda: now[0])
    svc = JobService(MemoryStateStore(), MemoryBlobStore(), **kw)
    return svc, now


def make_client(svc):
    return TestClient(create_app(svc))


def post_zip(client, payload, filename="in.zip", field="file"):
    return client.post("/api/jobs", files={field: (filename, payload, "application/zip")})


def fake_ok(expected_events=None):
    def run(in_path, out_path, detector=None, ratio=None, margin=0.15, on_progress=None):
        assert pathlib.Path(in_path).exists()
        if on_progress is not None:
            on_progress({"current": None, "processed": 0, "total": 2,
                         "saved": 0, "review": 0})
            on_progress({"current": "a.jpg", "processed": 0, "total": 2,
                         "saved": 0, "review": 0})
            on_progress({"current": "a.jpg", "processed": 1, "total": 2,
                         "saved": 1, "review": 0})
            on_progress({"current": "b.jpg", "processed": 1, "total": 2,
                         "saved": 1, "review": 0})
            on_progress({"current": "b.jpg", "processed": 2, "total": 2,
                         "saved": 1, "review": 1})
            on_progress({"current": None, "processed": 2, "total": 2,
                         "saved": 1, "review": 1})
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("a.jpg", b"crop-a")
            zf.writestr("review/", b"")
        if expected_events is not None:
            expected_events.append("called")
        return {"processed": 2, "saved": 1, "review": 1, "skipped": 0}

    return run


def check_status_body(body, status):
    assert body["status"] == status
    assert set(body.keys()) == {"job_id", "status", "current", "processed",
                                "total", "saved", "review", "error"}
    assert body["processed"] == body["saved"] + body["review"]
    assert body["processed"] <= body["total"]
    for k in ("processed", "total", "saved", "review"):
        assert isinstance(body[k], int) and body[k] >= 0
    if status == "failed":
        assert isinstance(body["error"], str) and body["error"]
    else:
        assert body["error"] is None


def test_f1_create_valid_returns_202_queued_and_enqueues():
    svc, _ = make_service(process_fn=fake_ok())
    client = make_client(svc)
    r = post_zip(client, two_photo_zip_bytes())
    assert r.status_code == 202, r.text
    body = r.json()
    uuid.UUID(body["job_id"])
    assert body == {"job_id": body["job_id"], "status": "queued"}
    assert set(svc.state.ids()) == {body["job_id"]}
    got = svc.run_next(two_photo_stub())
    assert got["status"] == "completed"


def test_f1_wrong_field_rejected():
    svc, _ = make_service(process_fn=fake_ok())
    client = make_client(svc)
    r = client.post("/api/jobs", files={"upload": ("in.zip", b"data")})
    assert r.status_code == 422


def test_f1_too_large_returns_413_and_stores_nothing():
    svc, _ = make_service(process_fn=fake_ok(), max_upload_bytes=1024)
    client = make_client(svc)
    r = post_zip(client, b"x" * 2048)
    assert r.status_code == 413
    assert svc.state.ids() == []
    assert svc.blobs.keys() == []
    assert svc.run_next() is None


def test_f2_status_cycle_and_invariants():
    svc, _ = make_service(process_fn=fake_ok())
    client = make_client(svc)
    job_id = post_zip(client, two_photo_zip_bytes()).json()["job_id"]
    r = client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    check_status_body(r.json(), "queued")
    assert r.json()["current"] is None
    done = svc.run_next(two_photo_stub())
    assert done["status"] == "completed"
    r = client.get(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    body = r.json()
    check_status_body(body, "completed")
    assert (body["processed"], body["total"], body["saved"], body["review"]) == (2, 2, 1, 1)
    assert body["current"] is None


def test_f2_unknown_id_404_and_malformed_404():
    svc, _ = make_service(process_fn=fake_ok())
    client = make_client(svc)
    assert client.get(f"/api/jobs/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/jobs/not-a-uuid").status_code == 404


def test_f2_progress_fields_match_v202_names():
    seen = []

    def run(in_path, out_path, detector=None, ratio=None, margin=0.15, on_progress=None):
        on_progress({"current": None, "processed": 0, "total": 1, "saved": 0, "review": 0})
        on_progress({"current": "a.jpg", "processed": 0, "total": 1, "saved": 0, "review": 0})
        on_progress({"current": "a.jpg", "processed": 1, "total": 1, "saved": 0, "review": 1})
        on_progress({"current": None, "processed": 1, "total": 1, "saved": 0, "review": 1})
        with zipfile.ZipFile(out_path, "w") as zf:
            zf.writestr("review/a.jpg", b"x")
        return {"processed": 1, "saved": 0, "review": 1, "skipped": 0}

    svc, _ = make_service(process_fn=run)
    client = make_client(svc)
    job_id = post_zip(client, two_photo_zip_bytes()).json()["job_id"]

    orig_save = svc.state.save
    mid = {}

    def spy(jid, rec):
        if rec["status"] == "processing" and rec["processed"] == 1:
            mid.update(client.get(f"/api/jobs/{jid}").json())
        return orig_save(jid, rec)

    svc.state.save = spy
    svc.run_next()
    assert mid["status"] == "processing"
    assert set(mid.keys()) == {"job_id", "status", "current", "processed",
                               "total", "saved", "review", "error"}
    assert mid["current"] == "a.jpg"
    final = client.get(f"/api/jobs/{job_id}").json()
    check_status_body(final, "completed")
    assert seen == []  # silence unused guard


def test_f3_fifo_single_job_isolation_and_publish_before_completed():
    order = []

    def run_for(tag):
        def run(in_path, out_path, detector=None, ratio=None, margin=0.15, on_progress=None):
            order.append(tag)
            data = pathlib.Path(in_path).read_bytes()
            assert data == payloads[tag]
            with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(f"{tag}.bin", tag.encode())
            return {"processed": 0, "saved": 0, "review": 0, "skipped": 0}
        return run

    svc, _ = make_service(process_fn=run_for("first"))
    client = make_client(svc)
    buf1 = io.BytesIO()
    with zipfile.ZipFile(buf1, "w") as zf:
        zf.writestr("a.jpg", make_jpg_bytes())
    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as zf:
        zf.writestr("a.jpg", make_jpg_bytes(640, 480, color=(1, 2, 3)))
    payloads = {"first": buf1.getvalue(), "second": buf2.getvalue()}
    id1 = post_zip(client, payloads["first"]).json()["job_id"]
    id2 = post_zip(client, payloads["second"]).json()["job_id"]
    assert id1 != id2
    svc.process_fn = run_for("first")
    svc.run_next()
    assert order == ["first"]
    assert client.get(f"/api/jobs/{id1}").json()["status"] == "completed"
    assert client.get(f"/api/jobs/{id2}").json()["status"] == "queued"
    svc.process_fn = run_for("second")
    svc.run_next()
    assert order == ["first", "second"]
    b1 = client.get(f"/api/jobs/{id1}/result")
    b2 = client.get(f"/api/jobs/{id2}/result")
    assert b1.status_code == b2.status_code == 200
    assert b1.content != b2.content
    with zipfile.ZipFile(io.BytesIO(b1.content)) as zf:
        assert zf.read("first.bin") == b"first"


def test_f4_invalid_zip_marks_failed_no_partial():
    def bad(in_path, out_path, detector=None, ratio=None, margin=0.15, on_progress=None):
        raise ValueError("invalid zip file: bad input")

    svc, _ = make_service(process_fn=bad)
    client = make_client(svc)
    job_id = post_zip(client, b"not a zip").json()["job_id"]
    done = svc.run_next()
    assert done["status"] == "failed"
    body = client.get(f"/api/jobs/{job_id}").json()
    check_status_body(body, "failed")
    assert "invalid zip" in body["error"]
    r = client.get(f"/api/jobs/{job_id}/result")
    assert r.status_code == 409
    assert not svc.blobs.exists(f"jobs/{job_id}/output.zip")


def test_f4_processing_failure_marks_failed():
    def boom(in_path, out_path, detector=None, ratio=None, margin=0.15, on_progress=None):
        raise RuntimeError("boom-processing")

    svc, _ = make_service(process_fn=boom)
    client = make_client(svc)
    job_id = post_zip(client, two_photo_zip_bytes()).json()["job_id"]
    svc.run_next()
    body = client.get(f"/api/jobs/{job_id}").json()
    check_status_body(body, "failed")
    assert "boom-processing" in body["error"]
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409


def test_f5_download_codes_and_exact_bytes():
    svc, now = make_service(process_fn=fake_ok())
    client = make_client(svc)
    job_id = post_zip(client, two_photo_zip_bytes()).json()["job_id"]
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
    svc.run_next(two_photo_stub())
    r = client.get(f"/api/jobs/{job_id}/result")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    expected = svc.blobs.get(f"jobs/{job_id}/output.zip")
    assert r.content == expected
    now[0] += jobs.RESULT_TTL_SECONDS + 1
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 410
    assert client.get(f"/api/jobs/{uuid.uuid4()}/result").status_code == 404


def test_f5_result_not_available_while_processing():
    def slow(in_path, out_path, detector=None, ratio=None, margin=0.15, on_progress=None):
        on_progress({"current": None, "processed": 0, "total": 1, "saved": 0, "review": 0})
        code = client.get(f"/api/jobs/{jid[0]}/result").status_code
        assert code == 409
        with zipfile.ZipFile(out_path, "w") as zf:
            zf.writestr("review/", b"")
        on_progress({"current": None, "processed": 1, "total": 1, "saved": 0, "review": 1})
        return {"processed": 1, "saved": 0, "review": 1, "skipped": 0}

    svc, _ = make_service(process_fn=slow)
    client = make_client(svc)
    jid = [post_zip(client, two_photo_zip_bytes()).json()["job_id"]]
    svc.run_next()
    assert client.get(f"/api/jobs/{jid[0]}/result").status_code == 200


def test_f6_cleanup_deletes_only_expired():
    svc, now = make_service(process_fn=fake_ok())
    client = make_client(svc)
    id1 = post_zip(client, two_photo_zip_bytes()).json()["job_id"]
    svc.run_next(two_photo_stub())
    now[0] += jobs.RESULT_TTL_SECONDS + 10
    id2 = post_zip(client, two_photo_zip_bytes()).json()["job_id"]
    svc.run_next(two_photo_stub())
    assert svc.cleanup() == 1
    assert client.get(f"/api/jobs/{id1}").status_code == 404
    assert client.get(f"/api/jobs/{id2}").status_code == 200
    assert not svc.blobs.exists(f"jobs/{id1}/input.zip")
    assert not svc.blobs.exists(f"jobs/{id1}/output.zip")
    assert svc.blobs.exists(f"jobs/{id2}/output.zip")
    now[0] += jobs.RESULT_TTL_SECONDS + 10
    assert svc.cleanup() == 1
    assert svc.cleanup() == 0


def test_t1_reuses_process_archive_with_real_engine(tmp_path):
    svc, _ = make_service()
    assert svc.process_fn is not None
    import app.archive as archive

    assert svc.process_fn is archive.process_archive
    client = make_client(svc)
    job_id = post_zip(client, two_photo_zip_bytes()).json()["job_id"]
    done = svc.run_next(two_photo_stub())
    assert done["status"] == "completed"
    body = client.get(f"/api/jobs/{job_id}").json()
    assert (body["processed"], body["saved"], body["review"]) == (2, 1, 1)
    raw = client.get(f"/api/jobs/{job_id}/result").content
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
    assert "review/" in names
    assert any(n.endswith(".jpg") for n in names if not n.endswith("/"))


def test_storage_error_marks_failed_with_readable_error():
    svc, _ = make_service(process_fn=fake_ok())
    client = make_client(svc)
    job_id = post_zip(client, two_photo_zip_bytes()).json()["job_id"]

    def broken(key):
        raise ConnectionError("rustfs-down")

    svc.blobs.get = broken
    done = svc.run_next(two_photo_stub())
    assert done["status"] == "failed"
    assert "rustfs-down" in done["error"]
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409


def test_failed_result_is_409_and_completed_exact_bytes(tmp_path):
    svc, _ = make_service(process_fn=fake_ok())
    client = make_client(svc)
    good = post_zip(client, two_photo_zip_bytes()).json()["job_id"]
    svc.run_next(two_photo_stub())
    assert client.get(f"/api/jobs/{good}/result").status_code == 200


class ChunkedBlobs(MemoryBlobStore):
    """Blob double that only accepts file-streamed transfers in blocks."""

    def __init__(self):
        super().__init__()
        self.chunks = []

    def put(self, key, data):
        raise AssertionError("upload path must not materialize full bytes via put()")

    def put_file(self, key, path):
        buf = bytearray()
        with open(path, "rb") as fh:
            while True:
                block = fh.read(8192)
                if not block:
                    break
                self.chunks.append(len(block))
                buf += block
        self._blobs[key] = bytes(buf)


def test_f1_upload_streams_temp_to_store_without_full_bytes(monkeypatch):
    import pathlib as _pl

    def _boom(self):
        raise AssertionError("upload path materialized whole file via read_bytes")

    monkeypatch.setattr(_pl.Path, "read_bytes", _boom)
    svc = JobService(MemoryStateStore(), ChunkedBlobs(), now=lambda: 1000.0)
    client = TestClient(create_app(svc))
    payload = bytes(range(256)) * 400
    assert len(payload) > 8192
    r = client.post("/api/jobs", files={"file": ("in.zip", payload, "application/zip")})
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    assert svc.blobs.get(f"jobs/{job_id}/input.zip") == payload
    assert len(svc.blobs.chunks) > 1
    assert sum(svc.blobs.chunks) == len(payload)


def test_f1_oversize_discards_temp_input(monkeypatch):
    import pathlib as _pl
    import tempfile as _tf

    svc = JobService(MemoryStateStore(), MemoryBlobStore(),
                     now=lambda: 1000.0, max_upload_bytes=1024)
    created = []
    real_mkstemp = _tf.mkstemp

    def _spy(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        created.append(name)
        return fd, name

    monkeypatch.setattr(_tf, "mkstemp", _spy)
    client = TestClient(create_app(svc))
    r = client.post("/api/jobs", files={"file": ("in.zip", b"x" * 2048,
                                                "application/zip")})
    assert r.status_code == 413
    assert created and not _pl.Path(created[0]).exists()
    assert svc.state.ids() == []
    assert svc.blobs.keys() == []
