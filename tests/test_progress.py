"""Tests for V2-02 per-photo progress (contract first)."""

from __future__ import annotations

import hashlib
import inspect
import io
import pathlib
import zipfile

import pytest
from PIL import Image

import app.archive as archive
from app.archive import process_archive
from app.processor import process_folder


class Stub:
    def __init__(self, by_size=None, default=()):
        self.by_size = dict(by_size or {})
        self.default = list(default)
        self.calls = []

    def detect_people(self, image):
        self.calls.append(tuple(image.size))
        return list(self.by_size.get(tuple(image.size), self.default))


class Boom:
    def detect_people(self, image):
        raise RuntimeError("boom-processing")


def make_jpg_bytes(width=800, height=600, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "JPEG")
    return buf.getvalue()


def write_zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).digest()


def zip_map(path):
    with zipfile.ZipFile(path) as zf:
        return {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}


def two_photo_zip(path):
    # a.jpg saved, b.jpg review; note.txt must be ignored (not counted).
    stub = Stub(by_size={(800, 600): [(100, 100, 300, 300)], (500, 500): []})
    img_a = make_jpg_bytes(800, 600)
    img_b = make_jpg_bytes(500, 500, color=(10, 200, 10))
    write_zip(path, {"b.jpg": img_b, "a.jpg": img_a, "note.txt": b"hi"})
    return stub, img_a, img_b


def check_event(ev, current, processed, total, saved, review):
    assert set(ev.keys()) == {"current", "processed", "total", "saved", "review"}
    assert ev["current"] == current
    assert ev["processed"] == processed
    assert ev["total"] == total
    assert ev["saved"] == saved
    assert ev["review"] == review
    assert current is None or isinstance(current, str)
    for k in ("processed", "total", "saved", "review"):
        assert isinstance(ev[k], int) and ev[k] >= 0
    assert ev["processed"] == ev["saved"] + ev["review"]
    assert ev["processed"] <= ev["total"]


def test_f1_sequence_order_and_counters(tmp_path):
    src = tmp_path / "in.zip"
    stub, _, _ = two_photo_zip(src)
    out = tmp_path / "out.zip"
    events = []
    summary = process_archive(src, out, stub, None, 0.15, lambda e: events.append(e))
    assert summary == {"processed": 2, "saved": 1, "review": 1, "skipped": 0}
    assert len(events) == 2 * 2 + 2
    check_event(events[0], None, 0, 2, 0, 0)
    check_event(events[1], "a.jpg", 0, 2, 0, 0)
    check_event(events[2], "a.jpg", 1, 2, 1, 0)
    check_event(events[3], "b.jpg", 1, 2, 1, 0)
    check_event(events[4], "b.jpg", 2, 2, 1, 1)
    check_event(events[5], None, 2, 2, 1, 1)
    # Independent dicts: mutating one must not affect the rest.
    assert len({id(e) for e in events}) == len(events)
    events[0]["saved"] = 999
    assert events[5]["saved"] == 1


def test_f2_parity_with_and_without_callback(tmp_path):
    src = tmp_path / "in.zip"
    stub1, _, _ = two_photo_zip(src)
    before = sha(src)
    out1 = tmp_path / "o1.zip"
    summary1 = process_archive(src, out1, stub1, None, 0.15)
    stub2, _, _ = two_photo_zip(src)
    out2 = tmp_path / "o2.zip"
    events = []
    summary2 = process_archive(src, out2, stub2, None, 0.15, lambda e: events.append(e))
    assert summary2 == summary1
    assert stub2.calls == stub1.calls
    assert zip_map(out2) == zip_map(out1)
    assert sha(src) == before
    assert len(events) == 6


def test_signatures_compatible():
    sig = inspect.signature(process_archive)
    names = list(sig.parameters.values())
    assert [p.name for p in names] == [
        "input_zip", "output_zip", "detector", "ratio", "margin", "on_progress"]
    assert names[3].default is None
    assert names[4].default == 0.15
    assert names[5].default is None
    fsig = inspect.signature(process_folder)
    fnames = list(fsig.parameters.values())
    assert [p.name for p in fnames][:5] == [
        "input_dir", "output_dir", "detector", "ratio", "margin"]
    assert fnames[-1].default is None
    # V1 call without callback keeps summary/files/messages.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        src = d / "in"
        src.mkdir()
        Image.new("RGB", (400, 400), (9, 9, 9)).save(src / "a.jpg", "JPEG")
        s1 = process_folder(src, d / "o1", Stub(default=[(50, 50, 200, 200)]), None, 0.15)
        s2 = process_folder(src, d / "o2", Stub(default=[(50, 50, 200, 200)]), None, 0.15, None)
        assert s1 == s2 == {"processed": 1, "saved": 1, "review": 0, "skipped": 0}


def test_reuses_engine_single_pass(tmp_path, monkeypatch):
    src = tmp_path / "in.zip"
    stub, _, _ = two_photo_zip(src)
    out = tmp_path / "out.zip"
    real = archive.process_folder
    calls = []

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(archive, "process_folder", counting)
    process_archive(src, out, stub, None, 0.15, lambda e: None)
    assert len(calls) == 1
    assert len(stub.calls) == 2


def test_f3_invalid_zip_emits_nothing(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip" * 10)
    out = tmp_path / "out.zip"
    events = []
    with pytest.raises(ValueError, match="invalid zip"):
        process_archive(bad, out, Stub(), None, 0.15, lambda e: events.append(e))
    assert events == []
    assert not out.exists()


def test_f3_unreadable_member_emits_nothing(tmp_path):
    src = tmp_path / "in.zip"
    payload = make_jpg_bytes()
    with zipfile.ZipFile(src, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("a.jpg", payload)
    raw = bytearray(src.read_bytes())
    i = raw.find(payload[:16])
    assert i > 0
    raw[i + 4] ^= 0xFF
    src.write_bytes(raw)
    out = tmp_path / "out.zip"
    events = []
    with pytest.raises(ValueError, match="cannot read entry"):
        process_archive(src, out, Stub(), None, 0.15, lambda e: events.append(e))
    assert events == []
    assert not out.exists()


def test_f3_detector_failure_keeps_events_no_partial(tmp_path):
    src = tmp_path / "in.zip"
    write_zip(src, {"a.jpg": make_jpg_bytes(800, 600), "b.jpg": make_jpg_bytes(640, 480)})
    out = tmp_path / "out.zip"
    events = []
    with pytest.raises(RuntimeError, match="boom-processing"):
        process_archive(src, out, Boom(), None, 0.15, lambda e: events.append(e))
    assert len(events) == 2  # initial + before first photo
    check_event(events[0], None, 0, 2, 0, 0)
    check_event(events[1], "a.jpg", 0, 2, 0, 0)
    assert not out.exists()


def test_f3_callback_failure_before_final_no_partial(tmp_path):
    src = tmp_path / "in.zip"
    stub, _, _ = two_photo_zip(src)
    out = tmp_path / "out.zip"

    def bad(ev):
        events.append(dict(ev))
        if len(events) == 3:
            raise RuntimeError("cb-boom")

    events = []
    with pytest.raises(RuntimeError, match="cb-boom"):
        process_archive(src, out, stub, None, 0.15, bad)
    assert len(events) == 3
    assert not out.exists()


def test_f3_callback_failure_on_first_before_photo_no_detect_no_output(tmp_path):
    # H1: el callback falla en el evento pre-foto de la primera foto.
    src = tmp_path / "in.zip"
    stub, _, _ = two_photo_zip(src)
    out = tmp_path / "out.zip"
    events = []

    def bad(ev):
        events.append(dict(ev))
        if ev["current"] == "a.jpg" and ev["processed"] == 0:
            raise RuntimeError("cb-before-first")

    with pytest.raises(RuntimeError, match="cb-before-first"):
        process_archive(src, out, stub, None, 0.15, bad)
    assert len(events) == 2
    check_event(events[0], None, 0, 2, 0, 0)
    check_event(events[1], "a.jpg", 0, 2, 0, 0)
    assert stub.calls == []
    assert not out.exists()


def test_f4_final_after_publish_and_failure_keeps_zip(tmp_path):
    src = tmp_path / "in.zip"
    stub1, _, _ = two_photo_zip(src)
    ref = tmp_path / "ref.zip"
    process_archive(src, ref, stub1, None, 0.15)
    expected = zip_map(ref)

    stub2, _, _ = two_photo_zip(src)
    out = tmp_path / "out.zip"
    seen = []

    def bad_final(ev):
        seen.append(dict(ev))
        if ev["current"] is None and ev["processed"] == ev["total"] == 2 and len(seen) == 6:
            assert out.exists()  # final arrives only after publish
            raise RuntimeError("final-boom")

    with pytest.raises(RuntimeError, match="final-boom"):
        process_archive(src, out, stub2, None, 0.15, bad_final)
    assert len(seen) == 6
    assert out.exists()
    assert zip_map(out) == expected


def test_stdlib_only_no_web_deps():
    for f in ("app/archive.py", "app/processor.py"):
        source = pathlib.Path(f).read_text(encoding="utf-8")
        for banned in ("fastapi", "redis", "boto3", "requests", "httpx", "flask"):
            assert banned not in source
