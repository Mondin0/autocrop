"""Tests for V2-08 job lifecycle (contract first).

Covers durable claim/reconcile (F1/F2), TTL retention (F3), retryable
cleanup (F4), cleanup on busy queues (F5) and failed-submit handling with
orphan sweep (F6), using controlled clocks and stores.
"""

from __future__ import annotations

import io
import logging
import uuid
import zipfile

import pytest

import app.jobs as jobs_mod
from app.jobs import (INTERRUPTED_ERROR, JobService, MemoryBlobStore,
                      MemoryStateStore, RedisStateStore, create_app)


def _zip_bytes(payload: bytes = b"data") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("a.jpg", payload)
    return buf.getvalue()


def _ok_process(tag: str = "ok"):
    def run(in_path, out_path, detector=None, ratio=None, margin=0.15,
            on_progress=None):
        if on_progress is not None:
            on_progress({"current": None, "processed": 0, "total": 1,
                         "saved": 0, "review": 0})
            on_progress({"current": None, "processed": 1, "total": 1,
                         "saved": 1, "review": 0})
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("out.txt", tag.encode())
        return {"processed": 1, "saved": 1, "review": 0, "skipped": 0}

    return run


def _svc(now, **kw):
    kw.setdefault("process_fn", _ok_process())
    return JobService(MemoryStateStore(),
                      MemoryBlobStore(now=lambda: now[0]),
                      now=lambda: now[0], **kw)


def _submit(svc: JobService, payload: bytes = b"data") -> str:
    return svc.submit(_zip_bytes(payload))["job_id"]


# F1 --------------------------------------------------------------------


def test_f1_restart_fails_interrupted_keeps_completed_and_fifo():
    now = [1000.0]
    svc = _svc(now)
    good = _submit(svc, b"payload-good")
    assert svc.run_next()["status"] == "completed"
    j1, j2, j3 = (_submit(svc, b"payload-1"), _submit(svc, b"payload-2"),
                  _submit(svc, b"payload-3"))
    # Crash after the worker claimed j1 and persisted processing state,
    # without ever persisting a terminal state.
    assert svc.state.claim() == j1
    rec = svc.state.load(j1)
    rec["status"] = "processing"
    svc.state.save(j1, rec)
    # Restart: a new service over the same stores reconciles first.
    svc2 = JobService(svc.state, svc.blobs, now=lambda: now[0],
                      process_fn=_ok_process())
    assert svc2.reconcile() == 1
    bad = svc2.get(j1)
    assert bad["status"] == "failed"
    assert bad["current"] is None
    assert isinstance(svc.state.load(j1)["finished_at"], float)
    assert INTERRUPTED_ERROR in (svc.state.load(j1)["error"] or "")
    assert svc2.get(good)["status"] == "completed"
    seen = []

    def run(in_path, out_path, detector=None, ratio=None, margin=0.15,
            on_progress=None):
        with zipfile.ZipFile(in_path) as zf:
            seen.append(zf.read("a.jpg"))
        return _ok_process()(in_path, out_path, detector, ratio, margin,
                             on_progress)

    svc2.process_fn = run
    assert svc2.run_next()["job_id"] == j2
    assert svc2.run_next()["job_id"] == j3
    assert svc2.run_next() is None
    assert seen == [b"payload-2", b"payload-3"]


def test_f1_queued_claim_fails_but_terminal_claim_keeps_result():
    now = [1000.0]
    svc = _svc(now)
    j1 = _submit(svc)
    # Claimed but still marked queued: interrupted, must fail visibly.
    assert svc.state.claim() == j1
    assert svc.reconcile() == 1
    assert svc.get(j1)["status"] == "failed"
    # Terminal persisted but crash struck before releasing the claim:
    # the result is preserved, only the claim is released.
    j2 = _submit(svc)
    assert svc.state.claim() == j2
    rec = svc.state.load(j2)
    rec.update(status="completed", finished_at=now[0])
    svc.state.save(j2, rec)
    assert svc.reconcile() == 0
    assert svc.get(j2)["status"] == "completed"
    assert svc.state.claimed() == []
    from fastapi.testclient import TestClient
    svc.blobs.put(f"jobs/{j2}/output.zip", b"out")
    assert TestClient(create_app(svc)).get(
        f"/api/jobs/{j2}/result").status_code == 200


def test_f1_worker_pump_reconciles_after_transient_error():
    from app import worker as worker_mod

    calls = {"reconcile": 0}

    class _Svc(JobService):
        def run_next(self, *a, **k):
            raise ConnectionError("redis-down")

        def reconcile(self):
            calls["reconcile"] += 1
            return 1

    svc = _Svc(MemoryStateStore(), MemoryBlobStore(),
               process_fn=_ok_process())
    with pytest.raises(ConnectionError):
        worker_mod.pump_once(svc, object())
    # Barrier before consuming plus once more after the transient error.
    assert calls["reconcile"] == 2


# F2 --------------------------------------------------------------------


def test_f2_claim_is_durable_and_processing_save_failure_keeps_claim():
    now = [1000.0]
    svc = _svc(now)
    j1, j2 = _submit(svc, b"payload-1"), _submit(svc, b"payload-2")
    # No window: claiming moves each id to the durable active set, so an
    # id is never handed out twice.
    assert svc.state.claim() == j1
    assert svc.state.claimed() == [j1]
    assert svc.state.claim() == j2
    assert svc.state.claimed() == [j1, j2]
    for jid in (j1, j2):
        rec = svc.state.load(jid)
        rec["status"] = "processing"
        svc.state.save(jid, rec)
    assert svc.reconcile() == 2
    assert svc.get(j1)["status"] == "failed"
    assert svc.get(j2)["status"] == "failed"
    # A state failure while persisting processing keeps the claim: the id
    # is neither lost nor re-queued, and nothing counts as processed.
    j3 = _submit(svc, b"payload-3")
    orig_save = svc.state.save
    calls = []

    def flaky(job_id, record):
        if record["status"] == "processing" and not calls:
            calls.append(1)
            raise ConnectionError("redis-down")
        return orig_save(job_id, record)

    svc.state.save = flaky
    with pytest.raises(ConnectionError):
        svc.run_next()
    assert svc.state.claimed() == [j3]
    assert svc.get(j3)["status"] == "queued"
    svc.state.save = orig_save
    assert svc.reconcile() == 1
    assert svc.get(j3)["status"] == "failed"


def test_f2_terminal_save_failure_is_not_success_and_keeps_claim():
    now = [1000.0]
    svc = _svc(now)
    job_id = _submit(svc)
    orig_save = svc.state.save

    def flaky(job_id_, record):
        if record["status"] == "completed":
            raise ConnectionError("redis-down")
        return orig_save(job_id_, record)

    svc.state.save = flaky
    with pytest.raises(ConnectionError):
        svc.run_next()
    assert svc.state.claimed() == [job_id]
    assert svc.get(job_id)["status"] in ("queued", "processing")
    from fastapi.testclient import TestClient
    assert TestClient(create_app(svc)).get(
        f"/api/jobs/{job_id}/result").status_code == 409
    svc.state.save = orig_save
    assert svc.reconcile() == 1
    assert svc.get(job_id)["status"] == "failed"


def test_f2_progress_save_outage_aborts_instead_of_succeeding():
    now = [1000.0]
    svc = _svc(now)
    job_id = _submit(svc)
    orig_save = svc.state.save
    calls = []

    def flaky(job_id_, record):
        if (record["status"] == "processing" and record["processed"] == 1
                and not calls):
            calls.append(1)
            raise ConnectionError("redis-down")
        return orig_save(job_id_, record)

    svc.state.save = flaky
    done = svc.run_next()
    assert calls == [1]
    assert done["status"] == "failed"
    assert "redis-down" in done["error"]
    assert svc.state.claimed() == []
    assert svc.get(job_id)["status"] == "failed"


# F3 --------------------------------------------------------------------


def test_f3_ttl_boundary_keeps_active_and_vigente_results():
    now = [2000.0]
    svc = _svc(now)
    from fastapi.testclient import TestClient
    client = TestClient(create_app(svc))
    good = _submit(svc)
    svc.run_next()
    queued = _submit(svc)
    rec = svc.state.load(queued)
    rec["status"] = "processing"
    svc.state.save(queued, rec)
    now[0] += jobs_mod.RESULT_TTL_SECONDS
    assert client.get(f"/api/jobs/{good}/result").status_code == 200
    assert svc.cleanup() == 0  # exact boundary is still valid
    now[0] += 1
    assert client.get(f"/api/jobs/{good}/result").status_code == 410
    assert svc.cleanup() == 1
    assert client.get(f"/api/jobs/{good}/result").status_code == 404
    # Active jobs are never cleaned no matter how old they get.
    now[0] += jobs_mod.RESULT_TTL_SECONDS * 10
    assert svc.cleanup() == 0
    assert svc.get(queued)["status"] == "processing"


def test_f3_failed_jobs_expire_and_legacy_failed_get_retention_start():
    now = [3000.0]
    svc = _svc(now)
    fresh = _submit(svc)
    svc.run_next()
    rec = svc.state.load(fresh)
    rec.update(status="failed", error="new boom",
               finished_at=now[0])
    svc.state.save(fresh, rec)
    # Legacy failed record without finished_at, crafted after the last
    # run so no earlier cleanup pass could have stamped it yet.
    legacy = _submit(svc)
    rec = svc.state.load(legacy)
    rec.update(status="failed", error="old boom", finished_at=None)
    svc.state.save(legacy, rec)
    svc.state.unqueue(legacy)  # historical record: no longer pending
    now[0] += jobs_mod.RESULT_TTL_SECONDS + 1
    # First pass assigns a retention start to the legacy record instead
    # of deleting it immediately; the aged failed job is removed.
    assert svc.cleanup() == 1
    assert svc.get(legacy)["status"] == "failed"
    assert svc.state.load(legacy)["finished_at"] == now[0]
    from fastapi.testclient import TestClient
    client = TestClient(create_app(svc))
    assert client.get(f"/api/jobs/{legacy}/result").status_code == 409
    now[0] += jobs_mod.RESULT_TTL_SECONDS + 1
    assert svc.cleanup() == 1
    assert svc.cleanup() == 0


# F4 --------------------------------------------------------------------


def test_f4_delete_failures_keep_record_retry_is_idempotent_and_isolated():
    now = [4000.0]
    svc = _svc(now)
    first = _submit(svc)
    svc.run_next()
    second = _submit(svc)
    svc.run_next()
    now[0] += jobs_mod.RESULT_TTL_SECONDS + 1
    orig_delete = svc.blobs.delete
    bad_keys = {f"jobs/{first}/input.zip"}

    def flaky(key):
        if key in bad_keys:
            raise ConnectionError("rustfs-down")
        return orig_delete(key)

    svc.blobs.delete = flaky
    assert svc.cleanup() == 1  # second cleaned, first kept for retry
    assert svc.get(first)["status"] == "completed"
    svc.blobs.delete = orig_delete
    assert svc.cleanup() == 1
    assert svc.cleanup() == 0
    # Idempotent: objects already missing do not block state removal.
    third = _submit(svc)
    svc.run_next()
    now[0] += jobs_mod.RESULT_TTL_SECONDS + 1
    svc.blobs.delete(f"jobs/{third}/input.zip")
    svc.blobs.delete(f"jobs/{third}/output.zip")
    assert svc.cleanup() == 1


def test_f4_state_delete_failure_keeps_record_for_retry(caplog):
    now = [4100.0]
    svc = _svc(now)
    job_id = _submit(svc)
    svc.run_next()
    now[0] += jobs_mod.RESULT_TTL_SECONDS + 1
    orig_delete = svc.state.delete

    def boom(job_id_):
        raise ConnectionError("redis-down")

    svc.state.delete = boom
    with caplog.at_level(logging.ERROR, logger="autocrop.jobs"):
        assert svc.cleanup() == 0
    assert svc.get(job_id)["status"] == "completed"
    svc.state.delete = orig_delete
    assert svc.cleanup() == 1


# F5 --------------------------------------------------------------------


def test_f5_cleanup_runs_between_jobs_without_idle_gap():
    from app import worker as worker_mod

    now = [5000.0]
    svc = _svc(now)
    old = _submit(svc)
    svc.run_next()
    now[0] += jobs_mod.RESULT_TTL_SECONDS + 1
    first, second = _submit(svc, b"payload-first"), _submit(
        svc, b"payload-second")
    calls = []
    orig_cleanup = svc.cleanup

    def spy():
        calls.append(1)
        return orig_cleanup()

    svc.cleanup = spy
    order = []

    def run(in_path, out_path, detector=None, ratio=None, margin=0.15,
            on_progress=None):
        with zipfile.ZipFile(in_path) as zf:
            order.append(zf.read("a.jpg"))
        return _ok_process()(in_path, out_path, detector, ratio, margin,
                             on_progress)

    svc.process_fn = run
    assert worker_mod.pump_once(svc, object()) is True
    assert svc.get(first)["status"] == "completed"
    assert worker_mod.pump_once(svc, object()) is True
    assert worker_mod.pump_once(svc, object()) is False  # queue idle now
    assert len(calls) >= 3  # one attempt per pass, never starved by load
    assert svc.state.load(old) is None  # expired job cleaned before new work
    assert order == [b"payload-first", b"payload-second"]
    assert svc.get(first)["status"] == "completed"
    assert svc.get(second)["status"] == "completed"


# F6 --------------------------------------------------------------------


def test_f6_submit_failures_never_accept_and_revert_own_objects():
    now = [6000.0]
    svc = _svc(now)
    # Upload failure persists nothing.
    orig_put = svc.blobs.put

    def put_boom(key, data):
        raise ConnectionError("rustfs-down")

    svc.blobs.put = put_boom
    with pytest.raises(ConnectionError):
        svc.submit(b"zip-bytes")
    assert svc.state.ids() == []
    svc.blobs.put = orig_put
    # State-save failure reverts the already stored object.
    orig_save = svc.state.save

    def save_boom(job_id, record):
        raise ConnectionError("redis-down")

    svc.state.save = save_boom
    with pytest.raises(ConnectionError):
        svc.submit(b"zip-bytes")
    assert svc.state.ids() == []
    assert svc.blobs.keys() == []
    svc.state.save = orig_save


def test_f6_enqueue_executes_then_fails_without_accepting(caplog):
    now = [6100.0]

    class _ExecuteThenFail(MemoryStateStore):
        def enqueue(self, job_id):
            super().enqueue(job_id)  # executes, then fails
            raise ConnectionError("redis-down")

    svc = JobService(_ExecuteThenFail(),
                     MemoryBlobStore(now=lambda: now[0]),
                     now=lambda: now[0], process_fn=_ok_process())
    with pytest.raises(ConnectionError):
        svc.submit(b"zip-bytes")
    assert svc.state.ids() == []
    assert svc.blobs.keys() == []
    assert svc.run_next() is None  # half-enqueued id was reverted, FIFO kept


def test_f6_revert_failure_is_logged_while_original_error_raises(caplog):
    now = [6200.0]
    svc = _svc(now)
    orig_save = svc.state.save

    def save_boom(job_id, record):
        raise ConnectionError("redis-down")

    svc.state.save = save_boom
    orig_delete = svc.blobs.delete

    def delete_boom(key):
        raise ConnectionError("rustfs-down")

    svc.blobs.delete = delete_boom
    with caplog.at_level(logging.ERROR, logger="autocrop.jobs"):
        with pytest.raises(ConnectionError, match="redis-down"):
            svc.submit(b"zip-bytes")
    assert any("rollback" in r.message for r in caplog.records)
    svc.state.save = orig_save
    svc.blobs.delete = orig_delete


def test_f6_orphan_sweep_removes_only_old_prefixed_orphans():
    now = [7000.0]
    svc = _svc(now)
    keep = _submit(svc)
    svc.run_next()
    recent_orphan = f"jobs/{uuid.uuid4()}/input.zip"
    old_orphan = f"jobs/{uuid.uuid4()}/input.zip"
    foreign = "other/dead-beef-3/input.zip"
    svc.blobs.put(recent_orphan, b"recent")
    svc.blobs.put(old_orphan, b"old")
    svc.blobs.put(foreign, b"foreign")
    svc.blobs._mtimes[old_orphan] = now[0] - jobs_mod.RESULT_TTL_SECONDS - 10
    svc.blobs._mtimes[foreign] = now[0] - jobs_mod.RESULT_TTL_SECONDS - 10
    assert svc.cleanup() == 0  # nothing terminal-expired; orphans swept
    assert svc.blobs.exists(f"jobs/{keep}/input.zip")
    assert svc.blobs.exists(f"jobs/{keep}/output.zip")
    assert svc.blobs.exists(recent_orphan)  # recent upload may be in flight
    assert not svc.blobs.exists(old_orphan)
    assert svc.blobs.exists(foreign)  # outside the jobs prefix: untouched
    assert svc.blobs.get(recent_orphan) == b"recent"


class _PagedS3:
    """S3 double serving two listing pages with controlled mtimes."""

    def __init__(self, entries):
        self.objects = dict(entries)
        self.deleted = []
        self.get_calls = 0

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        parent = self

        class _Paginator:
            def paginate(self, Bucket, Prefix):
                keys = sorted(k for k in parent.objects
                              if k.startswith(Prefix))
                for i in range(0, len(keys), 1):
                    yield {"Contents": [
                        {"Key": k, "LastModified": parent.objects[k][1]}
                        for k in keys[i:i + 1]]}

        return _Paginator()

    def get_object(self, Bucket, Key):
        self.get_calls += 1
        raise AssertionError("orphan sweep must not read bodies")

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)
        self.objects.pop(Key, None)
        return {}


class _Stamp:
    def __init__(self, ts):
        self._ts = ts

    def timestamp(self):
        return self._ts


def test_f6_orphan_sweep_uses_s3_pagination_without_reading_bodies():
    from app.jobs import S3BlobStore
    now = [8000.0]
    valid_uuid = str(uuid.uuid4())
    old_uuid = str(uuid.uuid4())
    new_uuid = str(uuid.uuid4())
    fake = _PagedS3({
        f"jobs/{valid_uuid}/input.zip": (b"in", _Stamp(now[0])),
        f"jobs/{valid_uuid}/output.zip": (b"out", _Stamp(now[0])),
        f"jobs/{old_uuid}/input.zip": (b"old", _Stamp(
            now[0] - jobs_mod.RESULT_TTL_SECONDS - 5)),
        f"jobs/{new_uuid}/input.zip": (b"new", _Stamp(now[0])),
    })
    state = MemoryStateStore()
    state.save(valid_uuid, {"job_id": valid_uuid, "status": "completed",
                            "current": None, "processed": 1, "total": 1,
                            "saved": 1, "review": 0, "error": None,
                            "finished_at": now[0],
                            "input_key": f"jobs/{valid_uuid}/input.zip",
                            "output_key": f"jobs/{valid_uuid}/output.zip"})
    svc = JobService(state, S3BlobStore(fake, "bkt"),
                     now=lambda: now[0], process_fn=_ok_process())
    assert svc.cleanup() == 0
    assert fake.deleted == [f"jobs/{old_uuid}/input.zip"]
    assert fake.get_calls == 0
    assert f"jobs/{new_uuid}/input.zip" in fake.objects


# Redis parity ------------------------------------------------------------


class _FakeRedis:
    """Minimal Redis double with atomic claim support."""

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

    def lmove(self, src, dst, src_pos, dst_pos):
        assert (src_pos, dst_pos) == ("LEFT", "RIGHT")
        items = self.lists.get(src, [])
        if not items:
            return None
        value = items.pop(0)
        self.lists.setdefault(dst, []).append(value)
        return value

    def lrem(self, key, count, value):
        items = self.lists.get(key, [])
        before = len(items)
        target = self._enc(value)
        items[:] = [v for v in items if v != target]
        return before - len(items)

    def lrange(self, key, start, stop):
        items = self.lists.get(key, [])
        return items[start:] if stop == -1 else items[start:stop + 1]

    def sadd(self, key, *values):
        self.sets.setdefault(key, set()).update(self._enc(v) for v in values)

    def srem(self, key, *values):
        for v in values:
            self.sets.get(key, set()).discard(self._enc(v))

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
        parent = self

        class _Pipe:
            def __init__(self):
                self.ops = []

            def delete(self, key):
                self.ops.append(key)
                return self

            def srem(self, key, *values):
                self.ops.append((key, values))
                return self

            def execute(self):
                for op in self.ops:
                    if isinstance(op, str):
                        parent.delete(op)
                    else:
                        parent.srem(op[0], *op[1])
                return []

        return _Pipe()


def test_redis_claim_fifo_reconcile_and_cleanup_parity():
    now = [9000.0]
    svc = JobService(RedisStateStore(_FakeRedis()), MemoryBlobStore(),
                     now=lambda: now[0], process_fn=_ok_process())
    j1, j2 = _submit(svc, b"payload-1"), _submit(svc, b"payload-2")
    assert svc.state.claim() == j1
    assert svc.state.claimed() == [j1]
    assert svc.state.claim() == j2  # FIFO preserved, never handed out twice
    for jid in (j1, j2):
        rec = svc.state.load(jid)
        rec["status"] = "processing"
        svc.state.save(jid, rec)
    assert svc.reconcile() == 2
    assert svc.get(j1)["status"] == "failed"
    assert svc.get(j2)["status"] == "failed"
    # run_next/cleanup go through the same durable-claim path.
    svc2 = JobService(RedisStateStore(_FakeRedis()), MemoryBlobStore(),
                      now=lambda: now[0], process_fn=_ok_process())
    k1 = _submit(svc2, b"payload-k")
    assert svc2.run_next()["job_id"] == k1
    now[0] += jobs_mod.RESULT_TTL_SECONDS + 1
    assert svc2.cleanup() == 1
    assert svc2.cleanup() == 0


# R1: orphan sweep must verify absence per UUID ---------------------------


def test_r1_sweep_load_failure_preserves_valid_objects():
    now = [10000.0]
    svc = _svc(now)
    valid = _submit(svc, b"payload-valid")  # stays queued: never deletable
    rec = svc.state.load(valid)
    assert rec["status"] == "queued"
    svc.blobs._mtimes[rec["input_key"]] = now[0] - jobs_mod.RESULT_TTL_SECONDS - 10
    import uuid as _uuid
    orphan = f"jobs/{_uuid.uuid4()}/input.zip"
    svc.blobs.put(orphan, b"orphan")
    svc.blobs._mtimes[orphan] = now[0] - jobs_mod.RESULT_TTL_SECONDS - 10
    orig_load = svc.state.load

    def flaky(job_id):
        if job_id == valid:
            raise ConnectionError("redis-down")
        return orig_load(job_id)

    svc.state.load = flaky
    try:
        assert svc.cleanup() == 0
        assert svc.blobs.exists(rec["input_key"])  # uncertainty keeps it
        assert not svc.blobs.exists(orphan)  # proven orphan still swept
    finally:
        svc.state.load = orig_load
    assert svc.get(valid)["status"] == "queued"


class _HiddenIndex:
    """State double whose listing omits jobs; direct load still works."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def ids(self):
        return []


def test_r1_sweep_missing_index_preserves_loadable_jobs():
    import uuid as _uuid
    now = [10100.0]
    inner = MemoryStateStore()
    svc = JobService(_HiddenIndex(inner),
                     MemoryBlobStore(now=lambda: now[0]),
                     now=lambda: now[0], process_fn=_ok_process())
    assert svc.run_next() is None  # nothing listed: nothing claimed
    valid = _submit(svc, b"payload-valid")
    rec = inner.load(valid)
    svc.blobs._mtimes[rec["input_key"]] = now[0] - jobs_mod.RESULT_TTL_SECONDS - 10
    orphan = f"jobs/{_uuid.uuid4()}/input.zip"
    svc.blobs.put(orphan, b"orphan")
    svc.blobs._mtimes[orphan] = now[0] - jobs_mod.RESULT_TTL_SECONDS - 10
    assert svc.cleanup() == 0
    assert svc.blobs.exists(rec["input_key"])
    assert not svc.blobs.exists(orphan)


# R2: sweep only owns input.zip/output.zip of valid UUIDs ------------------


def test_r2_sweep_keeps_foreign_layouts_and_claimed_keys():
    import uuid as _uuid
    now = [10200.0]
    svc = _svc(now)
    claimed_job = _submit(svc, b"payload-claimed")
    assert svc.state.claim() == claimed_job  # worker holds it, not queued
    old = now[0] - jobs_mod.RESULT_TTL_SECONDS - 10
    foreign = ["jobs/foreign-name/file.txt",
               f"jobs/{_uuid.uuid4()}/notes.txt",
               "jobs/not-a-uuid/input.zip",
               "jobs//input.zip"]
    for key in foreign:
        svc.blobs.put(key, b"foreign")
        svc.blobs._mtimes[key] = old
    orphan_uuid = str(_uuid.uuid4())
    true_orphan = f"jobs/{orphan_uuid}/input.zip"
    svc.blobs.put(true_orphan, b"orphan")
    svc.blobs._mtimes[true_orphan] = old
    assert svc.cleanup() == 0
    for key in foreign:
        assert svc.blobs.exists(key), key
    assert svc.blobs.exists(f"jobs/{claimed_job}/input.zip")
    assert not svc.blobs.exists(true_orphan)


# R3: reconcile barrier before consuming -----------------------------------


def test_r3_barrier_blocks_consume_while_claims_pending():
    from app import worker as worker_mod
    from app.jobs import PendingClaimsError
    now = [10300.0]
    svc = _svc(now)
    j1 = _submit(svc, b"payload-1")
    j2 = _submit(svc, b"payload-2")
    # Crash leaves j1 claimed+processing without a terminal state.
    assert svc.state.claim() == j1
    rec = svc.state.load(j1)
    rec["status"] = "processing"
    svc.state.save(j1, rec)
    # Redis now fails every read of j1: reconcile cannot resolve it.
    orig_load = svc.state.load

    def flaky(job_id):
        if job_id == j1:
            raise ConnectionError("redis-down")
        return orig_load(job_id)

    svc.state.load = flaky
    calls = []

    def spy(*a, **k):
        calls.append(1)
        return _ok_process()(*a, **k)

    svc.process_fn = spy
    with pytest.raises(PendingClaimsError):
        worker_mod.pump_once(svc, object())
    assert calls == []  # j2 was not consumed while j1 is pending
    assert svc.get(j2)["status"] == "queued"
    svc.state.load = orig_load
    assert worker_mod.pump_once(svc, object()) is True
    assert svc.get(j1)["status"] == "failed"
    assert svc.get(j2)["status"] == "completed"


def test_r3_reconcile_error_blocks_consume_and_retries(monkeypatch):
    from app import worker as worker_mod
    now = [10400.0]
    svc = _svc(now)
    j1 = _submit(svc, b"payload-1")
    calls = []

    def spy(*a, **k):
        calls.append(1)
        return _ok_process()(*a, **k)

    svc.process_fn = spy

    def boom():
        raise ConnectionError("redis-down")

    monkeypatch.setattr(svc.state, "claimed", boom)
    with pytest.raises(ConnectionError):
        worker_mod.pump_once(svc, object())
    assert calls == []
    assert svc.get(j1)["status"] == "queued"
    monkeypatch.undo()
    assert worker_mod.pump_once(svc, object()) is True
    assert svc.get(j1)["status"] == "completed"


# R4: submit rollback -------------------------------------------------------


class _PartialUploads(MemoryBlobStore):
    """Blob double that publishes a partial object and then fails."""

    def put(self, key, data):
        self._blobs[key] = bytes(data[:1])
        self._mtimes[key] = self._now()
        raise ConnectionError("upload-broken")

    def put_file(self, key, path):
        with open(path, "rb") as fh:
            self._blobs[key] = fh.read(1)
        self._mtimes[key] = self._now()
        raise ConnectionError("upload-broken")


def _partial_service(now):
    return JobService(MemoryStateStore(), _PartialUploads(now=lambda: now[0]),
                      now=lambda: now[0], process_fn=_ok_process())


def test_r4_published_then_failed_upload_reverts_without_accepting():
    now = [10500.0]
    svc = _partial_service(now)
    with pytest.raises(ConnectionError, match="upload-broken"):
        svc.submit(b"zip-bytes")
    assert svc.state.ids() == []
    assert svc.blobs.keys() == []
    with pytest.raises(ConnectionError, match="upload-broken"):
        svc.submit_file(__file__)
    assert svc.state.ids() == []
    assert svc.blobs.keys() == []


def test_r4_failed_upload_http_is_not_accepted():
    from fastapi.testclient import TestClient
    now = [10510.0]
    svc = _partial_service(now)
    client = TestClient(create_app(svc), raise_server_exceptions=False)
    r = client.post("/api/jobs", files={"file": ("in.zip", b"zip-bytes",
                                                 "application/zip")})
    assert r.status_code != 202
    assert svc.state.ids() == []
    assert svc.blobs.keys() == []


class _RaceClaim(MemoryStateStore):
    """State double where the worker claims between enqueue and its ack."""

    def enqueue(self, job_id):
        super().enqueue(job_id)
        assert self.claim() == job_id
        rec = self.load(job_id)
        rec["status"] = "processing"
        self.save(job_id, rec)
        raise ConnectionError("enqueue-lost-ack")


def _race_service(now, blobs=None):
    return JobService(_RaceClaim(), blobs or MemoryBlobStore(),
                      now=lambda: now[0], process_fn=_ok_process())


def test_r4_enqueue_claimed_concurrently_preserves_worker_job():
    now = [10600.0]
    for submitter in (lambda svc: svc.submit(b"zip-bytes"),
                      lambda svc: svc.submit_file(__file__)):
        svc = _race_service(now)
        with pytest.raises(ConnectionError, match="enqueue-lost-ack"):
            submitter(svc)
        job_id = svc.state.claimed()[0]
        assert svc.state.load(job_id)["status"] == "processing"
        assert svc.blobs.exists(f"jobs/{job_id}/input.zip")
        # The worker still owns it: finishing works and keeps FIFO order.
        svc.blobs.put(f"jobs/{job_id}/output.zip", b"out")
        rec = svc.state.load(job_id)
        rec.update(status="completed", finished_at=now[0])
        svc.state.save(job_id, rec)
        svc.state.release(job_id)
        assert svc.get(job_id)["status"] == "completed"


def test_r4_raced_enqueue_http_is_not_accepted():
    from fastapi.testclient import TestClient
    now = [10610.0]
    svc = _race_service(now)
    client = TestClient(create_app(svc), raise_server_exceptions=False)
    r = client.post("/api/jobs", files={"file": ("in.zip", b"zip-bytes",
                                                 "application/zip")})
    assert r.status_code != 202


# R5: missing boundaries ----------------------------------------------------


def test_r5_output_delete_failure_after_input_keeps_record():
    now = [10700.0]
    svc = _svc(now)
    job_id = _submit(svc, b"payload")
    svc.run_next()
    now[0] += jobs_mod.RESULT_TTL_SECONDS + 1
    orig_delete = svc.blobs.delete

    def flaky(key):
        if key == f"jobs/{job_id}/output.zip":
            raise ConnectionError("rustfs-down")
        return orig_delete(key)

    svc.blobs.delete = flaky
    assert svc.cleanup() == 0
    assert svc.get(job_id)["status"] == "completed"
    svc.blobs.delete = orig_delete
    assert svc.cleanup() == 1  # input already gone: still idempotent
    assert svc.cleanup() == 0


def test_r5_failed_exact_ttl_boundary_is_kept():
    from fastapi.testclient import TestClient
    now = [10800.0]
    svc = _svc(now)
    client = TestClient(create_app(svc))
    job_id = _submit(svc, b"payload")
    svc.run_next()
    rec = svc.state.load(job_id)
    rec.update(status="failed", error="boom", finished_at=now[0])
    svc.state.save(job_id, rec)
    now[0] += jobs_mod.RESULT_TTL_SECONDS
    assert svc.cleanup() == 0  # inclusive boundary: retained, never served
    assert svc.get(job_id)["status"] == "failed"
    assert client.get(f"/api/jobs/{job_id}/result").status_code == 409
    now[0] += 1
    assert svc.cleanup() == 1
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_r5_failed_save_failure_then_repeated_reconcile():
    now = [10900.0]
    svc = _svc(now)
    job_id = _submit(svc, b"payload")

    def boom(in_path, out_path, detector=None, ratio=None, margin=0.15,
             on_progress=None):
        raise RuntimeError("inference-down")

    svc.process_fn = boom
    orig_save = svc.state.save
    bad = []

    def flaky(job_id_, record):
        if record["status"] == "failed" and len(bad) < 2:
            bad.append(1)
            raise ConnectionError("redis-down")
        return orig_save(job_id_, record)

    svc.state.save = flaky
    with pytest.raises(ConnectionError):
        svc.run_next()
    assert bad == [1]
    assert svc.state.claimed() == [job_id]
    assert svc.reconcile() == 0  # still failing: claim kept, nothing fixed
    assert bad == [1, 1]
    assert svc.state.claimed() == [job_id]
    svc.state.save = orig_save
    assert svc.reconcile() == 1
    assert svc.state.claimed() == []
    body = svc.get(job_id)
    assert body["status"] == "failed" and body["error"]


# R4c: atomic queue take-back, no TOCTOU ------------------------------------


class _ClaimInsideUnqueue(MemoryStateStore):
    """The worker wins the race inside unqueue, after any prior check."""

    def __init__(self):
        super().__init__()
        self.race_next = False

    def enqueue(self, job_id):
        super().enqueue(job_id)
        if self.race_next:
            self.race_next = False
            raise ConnectionError("enqueue-lost-ack")

    def unqueue(self, job_id):
        if job_id not in self.claimed():
            assert self.claim() == job_id
            rec = self.load(job_id)
            rec["status"] = "processing"
            self.save(job_id, rec)
        return super().unqueue(job_id)


class _RedisClaimInsideUnqueue(RedisStateStore):
    """Same interleave against the Redis adapter."""

    def __init__(self, client):
        super().__init__(client)
        self.race_next = False

    def enqueue(self, job_id):
        super().enqueue(job_id)
        if self.race_next:
            self.race_next = False
            raise ConnectionError("enqueue-lost-ack")

    def unqueue(self, job_id):
        if job_id not in self.claimed():
            assert self.claim() == job_id
            rec = self.load(job_id)
            rec["status"] = "processing"
            self.save(job_id, rec)
        return super().unqueue(job_id)


def _finish_hook(state, blobs, now, job_id):
    assert state.claim() == job_id
    blobs.put(f"jobs/{job_id}/output.zip", b"result-bytes")
    rec = state.load(job_id)
    rec.update(status="completed", finished_at=now[0])
    state.save(job_id, rec)
    state.release(job_id)


class _FinishBeforeAck(MemoryStateStore):
    """Worker completes and releases before the enqueue ack is lost."""

    def __init__(self, blobs, now):
        super().__init__()
        self._hooked_blobs = blobs
        self._hooked_now = now

    def enqueue(self, job_id):
        super().enqueue(job_id)
        _finish_hook(self, self._hooked_blobs, self._hooked_now, job_id)
        raise ConnectionError("enqueue-lost-ack")


class _RedisFinishBeforeAck(RedisStateStore):
    """Same interleave against the Redis adapter."""

    def __init__(self, client, blobs, now):
        super().__init__(client)
        self._hooked_blobs = blobs
        self._hooked_now = now

    def enqueue(self, job_id):
        super().enqueue(job_id)
        _finish_hook(self, self._hooked_blobs, self._hooked_now, job_id)
        raise ConnectionError("enqueue-lost-ack")


def _r4c_services(now):
    blobs_mem = MemoryBlobStore(now=lambda: now[0])
    yield ("memory-claim", _ClaimInsideUnqueue(), MemoryBlobStore(
        now=lambda: now[0]))
    yield ("redis-claim", _RedisClaimInsideUnqueue(_FakeRedis()),
           MemoryBlobStore(now=lambda: now[0]))
    blobs_b = MemoryBlobStore(now=lambda: now[0])
    yield ("memory-finish", _FinishBeforeAck(blobs_b, now), blobs_b)
    blobs_r = MemoryBlobStore(now=lambda: now[0])
    yield ("redis-finish", _RedisFinishBeforeAck(_FakeRedis(), blobs_r, now),
           blobs_r)


def test_r4c_concurrent_claim_survives_rollback_and_finishes():
    from fastapi.testclient import TestClient
    for name, state, blobs in _r4c_services([11000.0]):
        if "finish" in name:
            continue
        now = [11000.0]
        svc = JobService(state, blobs, now=lambda: now[0],
                         process_fn=_ok_process())
        for submitter in (lambda: svc.submit(b"zip-bytes"),
                          lambda: svc.submit_file(__file__)):
            state.race_next = True
            with pytest.raises(ConnectionError, match="enqueue-lost-ack"):
                submitter()
        assert len(state.claimed()) == 2, name
        for job_id in list(state.claimed()):
            assert state.load(job_id)["status"] == "processing", name
            assert blobs.exists(f"jobs/{job_id}/input.zip"), name
        # The worker still owns both: finishing works afterwards.
        for job_id in list(state.claimed()):
            blobs.put(f"jobs/{job_id}/output.zip", b"out")
            rec = state.load(job_id)
            rec.update(status="completed", finished_at=now[0])
            state.save(job_id, rec)
            state.release(job_id)
            assert svc.get(job_id)["status"] == "completed", name
            client = TestClient(create_app(svc))
            assert client.get(f"/api/jobs/{job_id}/result").status_code == 200


def test_r4c_completed_released_before_lost_ack_is_preserved():
    from fastapi.testclient import TestClient
    for name, state, blobs in _r4c_services([11100.0]):
        if "claim" in name:
            continue
        now = [11100.0]
        svc = JobService(state, blobs, now=lambda: now[0],
                         process_fn=_ok_process())
        for submitter in (lambda: svc.submit(b"zip-bytes"),
                          lambda: svc.submit_file(__file__)):
            with pytest.raises(ConnectionError, match="enqueue-lost-ack"):
                submitter()
        assert state.claimed() == [], name
        done = [jid for jid in state.ids()
                if state.load(jid)["status"] == "completed"]
        assert len(done) == 2, name
        client = TestClient(create_app(svc))
        for job_id in done:
            assert blobs.exists(f"jobs/{job_id}/output.zip"), name
            assert client.get(
                f"/api/jobs/{job_id}/result").status_code == 200, name


def test_r4c_failed_submit_http_never_accepts_and_preserves():
    from fastapi.testclient import TestClient
    for cls in (_ClaimInsideUnqueue, _FinishBeforeAck):
        now = [11200.0]
        blobs = MemoryBlobStore(now=lambda: now[0])
        state = cls(blobs, now) if cls is _FinishBeforeAck else cls()
        if hasattr(state, "race_next"):
            state.race_next = True
        svc = JobService(state, blobs, now=lambda: now[0],
                         process_fn=_ok_process())
        client = TestClient(create_app(svc), raise_server_exceptions=False)
        r = client.post("/api/jobs", files={"file": ("in.zip", b"zip-bytes",
                                                     "application/zip")})
        assert r.status_code != 202, cls.__name__
        assert len(state.ids()) == 1, cls.__name__
        job_id = state.ids()[0]
        assert state.load(job_id)["status"] in ("processing", "completed")


def test_r4c_other_jobs_keep_fifo_around_raced_submit():
    now = [11300.0]
    svc = JobService(_ClaimInsideUnqueue(),
                     MemoryBlobStore(now=lambda: now[0]),
                     now=lambda: now[0], process_fn=_ok_process())
    svc.state.race_next = True
    with pytest.raises(ConnectionError, match="enqueue-lost-ack"):
        svc.submit(b"payload-raced")
    first = _submit(svc, b"payload-first")
    last = _submit(svc, b"payload-last")
    raced = svc.state.claimed()[0]
    order = []

    def run(in_path, out_path, detector=None, ratio=None, margin=0.15,
            on_progress=None):
        with zipfile.ZipFile(in_path) as zf:
            order.append(zf.read("a.jpg"))
        return _ok_process()(in_path, out_path, detector, ratio, margin,
                             on_progress)

    svc.process_fn = run
    assert svc.run_next()["job_id"] == first
    assert svc.run_next()["job_id"] == last
    assert order == [b"payload-first", b"payload-last"]
    assert svc.state.load(raced)["status"] == "processing"
    assert svc.blobs.exists(f"jobs/{raced}/input.zip")


# R4d: enqueue fails BEFORE inserting ----------------------------------------


class _FailBeforeEnqueue(MemoryStateStore):
    """Enqueue double failing before any queue effect, on demand."""

    def __init__(self):
        super().__init__()
        self.fail_next = False

    def enqueue(self, job_id):
        if self.fail_next:
            self.fail_next = False
            raise ConnectionError("enqueue-down")
        super().enqueue(job_id)


class _RedisFailBeforeEnqueue(RedisStateStore):
    """Same fault against the Redis adapter."""

    def __init__(self, client):
        super().__init__(client)
        self.fail_next = False

    def enqueue(self, job_id):
        if self.fail_next:
            self.fail_next = False
            raise ConnectionError("enqueue-down")
        super().enqueue(job_id)


def test_r4d_enqueue_before_insert_reverts_fully_without_leak():
    for state in (_FailBeforeEnqueue(),
                  _RedisFailBeforeEnqueue(_FakeRedis())):
        now = [12000.0]
        svc = JobService(state, MemoryBlobStore(now=lambda: now[0]),
                         now=lambda: now[0], process_fn=_ok_process())
        for submitter in (lambda: svc.submit(b"zip-bytes"),
                          lambda: svc.submit_file(__file__)):
            state.fail_next = True
            with pytest.raises(ConnectionError, match="enqueue-down"):
                submitter()
            assert svc.state.ids() == []
            assert svc.blobs.keys() == []
            assert svc.run_next() is None


def test_r4d_before_insert_http_neither_accepts_nor_leaks():
    from fastapi.testclient import TestClient
    now = [12100.0]
    svc = JobService(_FailBeforeEnqueue(),
                     MemoryBlobStore(now=lambda: now[0]),
                     now=lambda: now[0], process_fn=_ok_process())
    svc.state.fail_next = True
    client = TestClient(create_app(svc), raise_server_exceptions=False)
    r = client.post("/api/jobs", files={"file": ("in.zip", b"zip-bytes",
                                                 "application/zip")})
    assert r.status_code != 202
    assert svc.state.ids() == []
    assert svc.blobs.keys() == []


def test_r4d_revert_uncertainty_preserves_and_logs(caplog):
    now = [12200.0]

    def failing_submit(state, breakage):
        svc = JobService(state, MemoryBlobStore(now=lambda: now[0]),
                         now=lambda: now[0], process_fn=_ok_process())
        state.fail_next = True
        with caplog.at_level(logging.WARNING, logger="autocrop.jobs"):
            with pytest.raises(ConnectionError, match="enqueue-down"):
                svc.submit(b"zip-bytes")
        return svc

    # Take-back itself fails: nothing is known, objects are kept.
    state = _FailBeforeEnqueue()
    orig_unqueue = state.unqueue

    def unqueue_boom(job_id):
        raise ConnectionError("redis-down")

    state.unqueue = unqueue_boom
    svc = failing_submit(state, "unqueue")
    assert len(svc.state.ids()) == 1
    assert len(svc.blobs.keys()) == 1
    state.unqueue = orig_unqueue

    # Claim listing fails: a concurrent owner cannot be ruled out.
    state = _FailBeforeEnqueue()

    def claimed_boom():
        raise ConnectionError("redis-down")

    state.claimed = claimed_boom
    svc = failing_submit(state, "claimed")
    assert len(svc.state.ids()) == 1
    assert len(svc.blobs.keys()) == 1

    # State read fails: absence cannot be proven, objects are kept.
    state = _FailBeforeEnqueue()
    orig_load = state.load

    def load_boom(job_id):
        raise ConnectionError("redis-down")

    state.load = load_boom
    svc = failing_submit(state, "load")
    assert len(svc.state.ids()) == 1
    assert len(svc.blobs.keys()) == 1
    state.load = orig_load
    assert svc.get(svc.state.ids()[0])["status"] == "queued"


class _FlakyDeleteBlobs(MemoryBlobStore):
    """Blob double failing the first object delete, then recovering."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.failures = 1

    def delete(self, key):
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("rustfs-down")
        return super().delete(key)


def test_r4d_failed_object_delete_logged_and_swept_later(caplog):
    now = [12300.0]
    blobs = _FlakyDeleteBlobs(now=lambda: now[0])
    svc = JobService(_FailBeforeEnqueue(), blobs,
                     now=lambda: now[0], process_fn=_ok_process())
    svc.state.fail_next = True
    with caplog.at_level(logging.ERROR, logger="autocrop.jobs"):
        with pytest.raises(ConnectionError, match="enqueue-down"):
            svc.submit(b"zip-bytes")
    assert svc.state.ids() == []  # state reverted; object delete failed
    assert len(svc.blobs.keys()) == 1
    assert any("orphan sweep will retry" in r.message
               for r in caplog.records)
    blobs._mtimes[svc.blobs.keys()[0]] = now[0]
    now[0] += jobs_mod.RESULT_TTL_SECONDS + 1
    assert svc.cleanup() == 0  # no terminal state; sweep recovers the blob
    assert svc.blobs.keys() == []
