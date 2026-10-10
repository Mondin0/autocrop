"""Tests for app.archive.process_archive (stage V2-01, contract first)."""

from __future__ import annotations

import hashlib
import inspect
import io
import pathlib
import zipfile

import pytest
from PIL import Image

from app.archive import process_archive
from app.processor import process_folder


# --- Helpers -----------------------------------------------------------------


class Stub:
    """Detector stand-in keyed by image size: {(w, h): [boxes]}."""

    def __init__(self, by_size=None, default=()):
        self.by_size = dict(by_size or {})
        self.default = list(default)
        self.calls = []

    def detect_people(self, image):
        self.calls.append(tuple(image.size))
        return list(self.by_size.get(tuple(image.size), self.default))


class Boom:
    """Detector that always fails: proves validation runs before processing."""

    def detect_people(self, image):
        raise RuntimeError("boom-processing")


def one_box_stub(box):
    class OneBox:
        def detect_people(self, image):
            return [box]

    return OneBox()


def make_jpg_bytes(width=800, height=600, color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, "JPEG")
    return buf.getvalue()


def write_zip(path, entries):
    """Write a ZIP; entries maps arcname -> bytes."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).digest()


def zip_names(path):
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


def zip_bytes(path, name):
    with zipfile.ZipFile(path) as zf:
        return zf.read(name)



def check_rejected(input_zip, output_zip, detector, ratio, margin,
                   exc_type, match):
    """Require the pertinent validation error; detection must never run."""
    with pytest.raises(exc_type, match=match) as excinfo:
        process_archive(input_zip, output_zip, detector, ratio, margin)
    assert not isinstance(excinfo.value, NotImplementedError)
    calls = getattr(detector, "calls", None)
    if calls is not None:
        assert calls == []

# --- F1: parity with process_folder ------------------------------------------


def test_valid_zip_matches_process_folder(tmp_path):
    img_a = make_jpg_bytes(800, 600)
    img_b = make_jpg_bytes(640, 480, color=(30, 30, 200))
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.jpg").write_bytes(img_a)
    (src_dir / "b.jpg").write_bytes(img_b)
    stub = Stub(by_size={(800, 600): [(100, 100, 300, 300)],
                         (640, 480): [(50, 50, 200, 250)]})
    expected_dir = tmp_path / "expected"
    expected = process_folder(src_dir, expected_dir, stub, None, 0.15)

    input_zip = tmp_path / "in.zip"
    write_zip(input_zip, {"a.jpg": img_a, "b.jpg": img_b,
                          "note.txt": b"hello"})
    output_zip = tmp_path / "out.zip"
    stub2 = Stub(by_size={(800, 600): [(100, 100, 300, 300)],
                          (640, 480): [(50, 50, 200, 250)]})
    summary = process_archive(input_zip, output_zip, stub2, None, 0.15)
    assert summary == expected

    expected_files = {}
    for p in expected_dir.rglob("*"):
        if p.is_file():
            expected_files[p.relative_to(expected_dir).as_posix()] = p.read_bytes()
    with zipfile.ZipFile(output_zip) as zf:
        got = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    assert got == expected_files


def test_signature_matches_contract():
    sig = inspect.signature(process_archive)
    params = list(sig.parameters.values())
    assert [p.name for p in params] == [
        "input_zip", "output_zip", "detector", "ratio", "margin"]
    assert params[3].default is None
    assert params[4].default == 0.15


# --- F2: output contents and originals intact --------------------------------


def test_output_includes_review_and_preserves_input(tmp_path):
    saved = make_jpg_bytes(800, 600)
    empty = make_jpg_bytes(500, 500, color=(10, 200, 10))
    stub = Stub(by_size={(800, 600): [(100, 100, 300, 300)],
                         (500, 500): []})
    input_zip = tmp_path / "in.zip"
    write_zip(input_zip, {"s.jpg": saved, "e.jpg": empty})
    before = sha(input_zip)
    output_zip = tmp_path / "out.zip"
    summary = process_archive(input_zip, output_zip, stub, None, 0.15)
    assert summary == {"processed": 2, "saved": 1, "review": 1, "skipped": 0}
    assert sha(input_zip) == before
    names = zip_names(output_zip)
    assert "s.jpg" in names
    assert "review/" in names
    assert "review/e.jpg" in names
    assert "review.log" in names
    assert zip_bytes(output_zip, "review/e.jpg") == empty
    assert names == sorted(names)


# --- F3: rejections leave no partial output ----------------------------------


def test_rejects_corrupt_zip(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip at all" * 10)
    out = tmp_path / "out.zip"
    check_rejected(bad, out, Stub(), None, 0.15, ValueError, "invalid zip")
    assert not out.exists()


def test_rejects_zip_without_jpeg(tmp_path):
    input_zip = tmp_path / "in.zip"
    write_zip(input_zip, {"note.txt": b"hi", "img.png": b"\x89PNG"})
    out = tmp_path / "out.zip"
    check_rejected(input_zip, out, Stub(), None, 0.15, ValueError, "no JPEG")
    assert not out.exists()


def test_rejects_nested_jpeg(tmp_path):
    input_zip = tmp_path / "in.zip"
    write_zip(input_zip, {"a.jpg": make_jpg_bytes(),
                          "sub/nested.jpg": make_jpg_bytes()})
    out = tmp_path / "out.zip"
    # Boom proves validation wins: any processing attempt would raise
    # RuntimeError instead of the expected validation ValueError.
    check_rejected(input_zip, out, Boom(), None, 0.15,
                   ValueError, "unsafe entry name")
    assert not out.exists()


@pytest.mark.parametrize("name", [
    "../evil.jpg", "/abs.jpg", "sub/a.jpg", "..\\evil.jpg", "a\\b.jpg",
    "", "a/../b.jpg",
])
def test_rejects_dangerous_names(tmp_path, name):
    input_zip = tmp_path / "in.zip"
    entries = {"ok.jpg": make_jpg_bytes()}
    # writestr refuses "" so build it raw when needed
    with zipfile.ZipFile(input_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ok.jpg", entries["ok.jpg"])
        if name != "":
            zf.writestr(name or "x", make_jpg_bytes())
    # Empty-name ZIPs cannot be built portably; assert contract separately.
    if name == "":
        pytest.skip("empty arcname not storable with zipfile")
    out = tmp_path / "out.zip"
    check_rejected(input_zip, out, Boom(), None, 0.15,
                   ValueError, "unsafe entry name")
    assert not out.exists()


def test_rejects_case_insensitive_duplicates(tmp_path):
    input_zip = tmp_path / "in.zip"
    write_zip(input_zip, {"A.JPG": make_jpg_bytes(),
                          "a.jpg": make_jpg_bytes(640, 480)})
    out = tmp_path / "out.zip"
    check_rejected(input_zip, out, Boom(), None, 0.15,
                   ValueError, "duplicate name")
    assert not out.exists()


def test_rejects_symlink_entry(tmp_path):
    input_zip = tmp_path / "in.zip"
    info = zipfile.ZipInfo("link.jpg")
    info.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(input_zip, "w") as zf:
        zf.writestr(info, make_jpg_bytes())
        zf.writestr("ok.jpg", make_jpg_bytes())
    out = tmp_path / "out.zip"
    check_rejected(input_zip, out, Boom(), None, 0.15,
                   ValueError, "symlink entry")
    assert not out.exists()


def test_rejects_encrypted_entry(tmp_path):
    # stdlib clears the encrypted bit on write, so set it by patching
    # the raw headers for secret.jpg (local + central directory).
    input_zip = tmp_path / "in.zip"
    with zipfile.ZipFile(input_zip, "w") as zf:
        zf.writestr("secret.jpg", make_jpg_bytes())
        zf.writestr("ok.jpg", make_jpg_bytes())
    raw = bytearray(input_zip.read_bytes())
    for sig in (b"PK\x03\x04", b"PK\x01\x02"):
        start = 0
        while True:
            i = raw.find(sig, start)
            if i < 0:
                break
            raw[i + 8] |= 0x01
            start = i + 4
    input_zip.write_bytes(raw)
    with zipfile.ZipFile(input_zip) as zf:
        assert any(i.flag_bits & 0x1 for i in zf.infolist())
    out = tmp_path / "out.zip"
    check_rejected(input_zip, out, Boom(), None, 0.15,
                   ValueError, "encrypted entry")
    assert not out.exists()


def test_rejects_existing_output(tmp_path):
    input_zip = tmp_path / "in.zip"
    write_zip(input_zip, {"a.jpg": make_jpg_bytes()})
    before = sha(input_zip)
    out = tmp_path / "out.zip"
    out.write_bytes(b"old")
    check_rejected(input_zip, out, Stub(), None, 0.15,
                   FileExistsError, "already exists")
    assert out.read_bytes() == b"old"
    assert sha(input_zip) == before


def test_concurrent_output_creation_never_overwrites(tmp_path, monkeypatch):
    import app.archive as archive

    input_zip = tmp_path / "in.zip"
    write_zip(input_zip, {"a.jpg": make_jpg_bytes()})
    out = tmp_path / "out.zip"
    rival = b"rival-bytes"
    real_process_folder = archive.process_folder

    def racing_process_folder(*args, **kwargs):
        out.write_bytes(rival)  # another process wins mid-flight
        return real_process_folder(*args, **kwargs)

    monkeypatch.setattr(archive, "process_folder", racing_process_folder)
    stub = Stub(default=[(100, 100, 300, 300)])
    with pytest.raises(FileExistsError, match="already exists"):
        process_archive(input_zip, out, stub, None, 0.15)
    assert out.read_bytes() == rival


def test_rejects_declared_uncompressed_limit(tmp_path, monkeypatch):
    import app.archive as archive

    input_zip = tmp_path / "in.zip"
    write_zip(input_zip, {"a.jpg": make_jpg_bytes()})
    monkeypatch.setattr(archive, "MAX_TOTAL_UNCOMPRESSED", 10)
    out = tmp_path / "out.zip"
    check_rejected(input_zip, out, Stub(), None, 0.15,
                   ValueError, "2 GiB")
    assert not out.exists()


def test_rejects_compressed_limit(tmp_path, monkeypatch):
    import app.archive as archive

    input_zip = tmp_path / "in.zip"
    write_zip(input_zip, {"a.jpg": make_jpg_bytes()})
    monkeypatch.setattr(archive, "MAX_INPUT_BYTES", 10)
    out = tmp_path / "out.zip"
    check_rejected(input_zip, out, Stub(), None, 0.15,
                   ValueError, "500 MiB")
    assert not out.exists()


def test_rejects_too_many_entries(tmp_path, monkeypatch):
    import app.archive as archive

    input_zip = tmp_path / "in.zip"
    write_zip(input_zip, {"a.jpg": make_jpg_bytes(),
                          "b.jpg": make_jpg_bytes(640, 480)})
    monkeypatch.setattr(archive, "MAX_ENTRIES", 1)
    out = tmp_path / "out.zip"
    check_rejected(input_zip, out, Stub(), None, 0.15,
                   ValueError, "too many entries")
    assert not out.exists()


# --- F4: review preserved, detector failure propagates -----------------------


def test_detector_failure_leaves_no_partial(tmp_path):
    class Boom:
        def detect_people(self, image):
            raise RuntimeError("model exploded")

    input_zip = tmp_path / "in.zip"
    write_zip(input_zip, {"a.jpg": make_jpg_bytes()})
    out = tmp_path / "out.zip"
    with pytest.raises(RuntimeError) as excinfo:
        process_archive(input_zip, out, Boom(), None, 0.15)
    assert str(excinfo.value) == "model exploded"
    assert not out.exists()


def test_unreadable_member_rejected(tmp_path):
    # STORED data appears verbatim; flipping one byte breaks the CRC check.
    input_zip = tmp_path / "in.zip"
    payload = make_jpg_bytes()
    with zipfile.ZipFile(input_zip, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("a.jpg", payload)
    raw = bytearray(input_zip.read_bytes())
    i = raw.find(payload[:16])
    assert i > 0
    raw[i + 4] ^= 0xFF
    input_zip.write_bytes(raw)
    out = tmp_path / "out.zip"
    check_rejected(input_zip, out, Stub(), None, 0.15,
                   ValueError, "cannot read entry")
    assert not out.exists()


def test_stdlib_only_no_web_deps():
    source = pathlib.Path("app/archive.py").read_text(encoding="utf-8")
    for banned in ("fastapi", "redis", "boto3", "requests", "httpx", "flask"):
        assert banned not in source
