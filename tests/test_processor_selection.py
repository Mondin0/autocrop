"""Integration tests for V2-12 selection in the shared processor (synthetic).

Covers the automatic group ratio, explicit ratio precedence, identical review
copies with the new reason, counters, ZIP output and overwrite protection.
"""

import hashlib
import zipfile

import pytest
from PIL import Image

from app.archive import process_archive
from app.processor import default_ratio, process_folder, process_image

FORMATION = [(100, 400, 160, 550), (180, 405, 240, 555), (260, 402, 320, 552)]
AMBIGUOUS = [(100, 250, 300, 650), (700, 250, 900, 650)]


class Stub:
    """Detector stand-in keyed by image size: {(w, h): [boxes]}."""

    def __init__(self, by_size=None, default=()):
        self.by_size = dict(by_size or {})
        self.default = list(default)
        self.calls = []

    def detect_people(self, image):
        self.calls.append(image.size)
        return list(self.by_size.get(tuple(image.size), self.default))


def make_jpg(path, width=1200, height=800, color=(180, 60, 60)):
    Image.new("RGB", (width, height), color).save(path, "JPEG")
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).digest()


def test_group_photo_uses_automatic_three_two(tmp_path):
    src = make_jpg(tmp_path / "team.jpg")
    out = tmp_path / "out"
    status, _ = process_image(
        src, out, out / "review", Stub(default=FORMATION), None, 0.15)
    assert status == "saved"
    with Image.open(out / "team.jpg") as im:
        width, height = im.size
    assert width * 2 == height * 3


def test_individual_keeps_orientation_based_ratio(tmp_path):
    src = make_jpg(tmp_path / "portrait.jpg", 600, 1000)
    out = tmp_path / "out"
    status, _ = process_image(
        src, out, out / "review",
        Stub(default=[(200, 300, 400, 700)]), None, 0.15)
    assert status == "saved"
    with Image.open(out / "portrait.jpg") as im:
        width, height = im.size
    assert width * 3 == height * 2


def test_explicit_ratio_overrides_group_automatic(tmp_path):
    src = make_jpg(tmp_path / "team.jpg")
    out = tmp_path / "out"
    status, _ = process_image(
        src, out, out / "review", Stub(default=FORMATION), (1, 1), 0.15)
    assert status == "saved"
    with Image.open(out / "team.jpg") as im:
        assert im.size[0] == im.size[1]


def test_group_in_vertical_image_uses_landscape_three_two(tmp_path):
    formation = [(200, 300, 260, 800), (280, 305, 340, 805),
                 (360, 302, 420, 802)]
    src = make_jpg(tmp_path / "tall.jpg", 800, 1200)
    out = tmp_path / "out"
    status, _ = process_image(
        src, out, out / "review", Stub(default=formation), None, 0.15)
    assert status == "saved"
    assert default_ratio(800, 1200) == (2, 3)
    with Image.open(out / "tall.jpg") as im:
        width, height = im.size
    assert width > height
    assert width * 2 == height * 3


def test_ambiguous_photo_is_copied_identical_and_logged(tmp_path):
    src_dir = tmp_path / "in"
    src_dir.mkdir()
    photo = make_jpg(src_dir / "doubt.jpg", 1000, 700)
    out = tmp_path / "out"
    summary = process_folder(
        src_dir, out, Stub(default=AMBIGUOUS), None, 0.15)
    assert summary == {"processed": 1, "saved": 0, "review": 1, "skipped": 0}
    assert sha(out / "review" / "doubt.jpg") == sha(photo)
    assert not (out / "doubt.jpg").exists()
    assert (out / "review.log").read_text() == "doubt.jpg: ambiguous_subject\n"


def test_no_person_still_reviewed(tmp_path):
    src = make_jpg(tmp_path / "empty.jpg")
    out = tmp_path / "out"
    status, detail = process_image(
        src, out, out / "review", Stub(), None, 0.15)
    assert (status, detail) == ("review", "no_person")


def test_group_that_cannot_fit_is_no_valid_crop(tmp_path):
    formation = [(10, 600, 120, 900), (130, 610, 240, 910),
                 (250, 605, 360, 905)]
    src = make_jpg(tmp_path / "tall.jpg", 400, 1000)
    out = tmp_path / "out"
    status, detail = process_image(
        src, out, out / "review", Stub(default=formation), None, 0.15)
    assert (status, detail) == ("review", "no_valid_crop")
    assert sha(out / "review" / "tall.jpg") == sha(src)


def test_archive_keeps_interfaces_and_reports_new_reason(tmp_path):
    in_dir = tmp_path / "photos"
    in_dir.mkdir()
    make_jpg(in_dir / "team.jpg", 1200, 800)
    make_jpg(in_dir / "doubt.jpg", 1000, 700)
    stub = Stub(by_size={(1200, 800): FORMATION, (1000, 700): AMBIGUOUS})
    input_zip = tmp_path / "in.zip"
    with zipfile.ZipFile(input_zip, "w") as zf:
        zf.write(in_dir / "team.jpg", "team.jpg")
        zf.write(in_dir / "doubt.jpg", "doubt.jpg")
    output_zip = tmp_path / "out.zip"
    summary = process_archive(input_zip, output_zip, stub, None, 0.15)
    assert summary == {"processed": 2, "saved": 1, "review": 1, "skipped": 0}
    with zipfile.ZipFile(output_zip) as zf:
        names = set(zf.namelist())
        assert {"team.jpg", "team-crop.jpg", "doubt.jpg"} <= names
        assert not any(name.startswith("review/") for name in names)
        assert "review.log" not in names
        assert not any(name.startswith("review/team") for name in names)
        assert b"ambiguous_subject" in zf.read("reporte.html")
        with zf.open("team-crop.jpg") as handle, Image.open(handle) as crop:
            width, height = crop.size
    assert width * 2 == height * 3
    assert not output_zip.with_suffix(".tmp").exists()


def test_overwrite_protection_survives_new_selection(tmp_path):
    import os
    src_dir = tmp_path / "in"
    src_dir.mkdir()
    photo = make_jpg(src_dir / "team.jpg")
    out = tmp_path / "out"
    out.mkdir()
    os.link(photo, out / "team.jpg")
    before = sha(photo)
    stub = Stub(default=FORMATION)
    with pytest.raises(FileExistsError):
        process_folder(src_dir, out, stub, None, 0.15)
    assert sha(photo) == before
    assert stub.calls == []


class Exploding:
    """Detector that fails; detection errors must never become review."""

    def __init__(self, error):
        self.error = error
        self.calls = 0

    def detect_people(self, image):
        self.calls += 1
        raise self.error


@pytest.mark.parametrize(
    "error", [RuntimeError("backend down"), ValueError("bad detection")])
def test_detector_error_propagates_without_review(tmp_path, error):
    src = make_jpg(tmp_path / "a.jpg")
    before = sha(src)
    out = tmp_path / "out"
    stub = Exploding(error)
    with pytest.raises(type(error), match=str(error)):
        process_image(src, out, out / "review", stub, None, 0.15)
    assert stub.calls == 1
    assert sha(src) == before
    assert list((out / "review").iterdir()) == []
    assert not (out / "a.jpg").exists()


def test_detection_outside_image_is_an_error_not_ambiguity(tmp_path):
    src = make_jpg(tmp_path / "a.jpg")
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        process_image(
            src, out, out / "review",
            Stub(default=[(0, 0, 2000, 900)]), None, 0.15)
    assert list((out / "review").iterdir()) == []
    assert not (out / "a.jpg").exists()


def test_crop_error_propagates_instead_of_review(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("crop failure")

    monkeypatch.setattr("app.processor.calculate_crop", boom)
    src = make_jpg(tmp_path / "a.jpg")
    before = sha(src)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="crop failure"):
        process_image(
            src, out, out / "review",
            Stub(default=[(100, 100, 300, 300)]), None, 0.15)
    assert sha(src) == before
    assert list((out / "review").iterdir()) == []
    assert not (out / "a.jpg").exists()
