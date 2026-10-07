"""Tests for app.processor (stage 03, contract first, stub detector only)."""

import hashlib
import math

import pytest
from PIL import Image

from app.crop import calculate_crop
from app.processor import default_ratio, process_folder, process_image


# --- Helpers -----------------------------------------------------------------


class Stub:
    """Detector stand-in keyed by image size: {(w, h): [boxes]}."""

    def __init__(self, by_size=None, default=()):
        self.by_size = dict(by_size or {})
        self.default = list(default)
        self.calls = []

    def detect_people(self, image):
        self.calls.append((image.mode, image.size))
        return list(self.by_size.get(tuple(image.size), self.default))


def one_box_stub(box):
    class OneBox:
        def detect_people(self, image):
            return [box]

    return OneBox()


def make_jpg(path, width=800, height=600, color=(200, 30, 30)):
    Image.new("RGB", (width, height), color).save(path, "JPEG")
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).digest()


# --- default_ratio: F3 --------------------------------------------------------


def test_default_ratio_horizontal():
    assert default_ratio(800, 600) == (3, 2)


def test_default_ratio_vertical():
    assert default_ratio(600, 800) == (2, 3)


def test_default_ratio_square():
    assert default_ratio(500, 500) == (1, 1)


@pytest.mark.parametrize(
    "dims",
    [(0, 5), (-1, 5), (5, 0), (True, 5), (5, False), (1.5, 2), ("800", 600),
     (800, None), (None, None)],
)
def test_default_ratio_invalid(dims):
    with pytest.raises(ValueError):
        default_ratio(*dims)


# --- process_image saved path: F1 --------------------------------------------


def test_saved_known_vector_matches_crop_math(tmp_path):
    src = make_jpg(tmp_path / "a.jpg", 1000, 800)
    out, review = tmp_path / "out", tmp_path / "out" / "review"
    status, detail = process_image(
        src, out, review, one_box_stub((400, 300, 600, 500)), (1, 1), 0.15
    )
    assert status == "saved"
    saved = out / "a.jpg"
    assert detail == str(saved)
    with Image.open(saved) as im:
        assert im.size == (260, 260)
        assert im.format == "JPEG"
    assert calculate_crop(1000, 800, (400, 300, 600, 500), (1, 1), 0.15) == (
        370, 270, 630, 530)


def test_saved_original_intact_and_overwrites(tmp_path):
    src = make_jpg(tmp_path / "a.jpg", 1000, 800)
    before = sha(src)
    out, review = tmp_path / "out", tmp_path / "out" / "review"
    stub = one_box_stub((400, 300, 600, 500))
    assert process_image(src, out, review, stub, (1, 1), 0.15)[0] == "saved"
    assert sha(src) == before
    assert process_image(src, out, review, stub, (1, 1), 0.15)[0] == "saved"
    assert sha(src) == before
    assert len(list(out.glob("*.jpg"))) == 1


def test_saved_creates_missing_dirs(tmp_path):
    src = make_jpg(tmp_path / "a.jpg", 800, 600)
    out = tmp_path / "new" / "out"
    status, _ = process_image(
        src, out, out / "review", one_box_stub((100, 100, 300, 300)), None, 0.15)
    assert status == "saved"
    assert (out / "a.jpg").is_file()


def test_explicit_ratio_not_inverted_on_vertical(tmp_path):
    src = make_jpg(tmp_path / "v.jpg", 600, 1000)
    out = tmp_path / "out"
    status, _ = process_image(
        src, out, out / "review", one_box_stub((250, 400, 350, 600)), (3, 2), 0.15)
    assert status == "saved"
    with Image.open(out / "v.jpg") as im:
        assert im.size == (390, 260)


def test_auto_ratio_horizontal_vertical_square(tmp_path):
    cases = [((800, 600), (3, 2)), ((600, 800), (2, 3)), ((500, 500), (1, 1))]
    for (w, h), expected in cases:
        src = make_jpg(tmp_path / f"i{w}x{h}.jpg", w, h)
        out = tmp_path / f"out{w}x{h}"
        box = (w // 4, h // 4, 3 * w // 4, 3 * h // 4)
        status, _ = process_image(
            src, out, out / "review", one_box_stub(box), None, 0.15)
        assert status == "saved"
        with Image.open(out / src.name) as im:
            cw, ch = im.size
        assert cw * expected[1] == ch * expected[0]


# --- review paths: F2, F4 -----------------------------------------------------


def test_no_person_copies_identical(tmp_path):
    src = make_jpg(tmp_path / "e.jpg", 500, 500)
    out = tmp_path / "out"
    status, detail = process_image(src, out, out / "review", Stub(), None, 0.15)
    assert (status, detail) == ("review", "no_person")
    copied = out / "review" / "e.jpg"
    assert copied.is_file() and sha(copied) == sha(src)
    assert not (out / "e.jpg").exists()


def test_no_valid_crop_copies_identical(tmp_path):
    src = make_jpg(tmp_path / "t.jpg", 600, 1000)
    out = tmp_path / "out"
    status, detail = process_image(
        src, out, out / "review",
        one_box_stub((100, 50, 500, 950)), (3, 2), 0.15)
    assert calculate_crop(600, 1000, (100, 50, 500, 950), (3, 2), 0.15) is None
    assert (status, detail) == ("review", "no_valid_crop")
    assert sha(out / "review" / "t.jpg") == sha(src)


def test_corrupt_jpeg_is_unreadable(tmp_path):
    src = tmp_path / "bad.jpg"
    src.write_bytes(b"this is not a jpeg image at all" * 10)
    out = tmp_path / "out"
    status, detail = process_image(src, out, out / "review", Stub(), None, 0.15)
    assert (status, detail) == ("review", "unreadable")
    assert sha(out / "review" / "bad.jpg") == sha(src)


def test_exif_orientation_6_uses_oriented_coords(tmp_path):
    stored = Image.new("RGB", (100, 200), (30, 120, 200))
    exif = Image.Exif()
    exif[274] = 6
    src = tmp_path / "rot.jpg"
    stored.save(src, "JPEG", exif=exif)
    out = tmp_path / "out"
    # Valid only in the oriented 200x100 space; invalid (right > 100) if
    # EXIF were ignored on the stored 100x200 layout.
    status, _ = process_image(
        src, out, out / "review", one_box_stub((50, 10, 150, 90)), None, 0.15)
    assert status == "saved"
    with Image.open(out / "rot.jpg") as im:
        assert im.size == (150, 100)


# --- validation: F5 -----------------------------------------------------------


@pytest.mark.parametrize("ratio", [(0, 2), (3, 0), (True, 2), (3, False),
                                   (1.5, 2), "3:2", (3,), (3, 2, 1), [3, 2]])
def test_process_image_bad_ratio(tmp_path, ratio):
    src = make_jpg(tmp_path / "a.jpg", 100, 100)
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        process_image(src, out, out / "review", Stub(), ratio, 0.15)
    assert not out.exists()


@pytest.mark.parametrize("margin", [-0.1, -1, float("nan"), float("inf"),
                                    float("-inf"), True, False, "0.15", None])
def test_process_image_bad_margin(tmp_path, margin):
    src = make_jpg(tmp_path / "a.jpg", 100, 100)
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        process_image(src, out, out / "review", Stub(), None, margin)
    assert not out.exists()


def test_process_image_detector_without_method(tmp_path):
    src = make_jpg(tmp_path / "a.jpg", 100, 100)
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        process_image(src, out, out / "review", object(), None, 0.15)
    assert not out.exists()


def test_process_image_non_path_routes(tmp_path):
    src = make_jpg(tmp_path / "a.jpg", 100, 100)
    with pytest.raises(ValueError):
        process_image(str(src), tmp_path / "o", tmp_path / "r", Stub(), None, 0.15)
    with pytest.raises(ValueError):
        process_image(src, str(tmp_path / "o"), tmp_path / "r", Stub(), None, 0.15)


def test_zero_margin_is_valid(tmp_path):
    src = make_jpg(tmp_path / "a.jpg", 800, 600)
    out = tmp_path / "out"
    status, _ = process_image(
        src, out, out / "review", one_box_stub((100, 100, 300, 300)), None, 0)
    assert status == "saved"


# --- process_folder: F4, F5; T4 -----------------------------------------------


def make_mixed(input_dir):
    make_jpg(input_dir / "a_saved.jpg", 800, 600)
    make_jpg(input_dir / "b_saved.jpg", 640, 480)
    make_jpg(input_dir / "c_empty.jpg", 500, 500)
    (input_dir / "d_bad.jpg").write_bytes(b"corrupt" * 100)
    (input_dir / "e_note.txt").write_text("hello")
    (input_dir / "f_img.png").write_bytes(b"\x89PNG not really" * 10)
    return Stub(by_size={(800, 600): [(100, 100, 300, 300)],
                         (640, 480): [(50, 50, 200, 250)],
                         (500, 500): []})


def test_folder_mixed_summary_log_and_copies(tmp_path, capsys):
    src = tmp_path / "in"
    src.mkdir()
    stub = make_mixed(src)
    out = tmp_path / "out"
    summary = process_folder(src, out, stub, None, 0.15)
    assert summary == {"processed": 4, "saved": 2, "review": 2, "skipped": 2}
    assert (out / "a_saved.jpg").is_file()
    assert (out / "b_saved.jpg").is_file()
    assert sha(out / "review" / "c_empty.jpg") == sha(src / "c_empty.jpg")
    assert sha(out / "review" / "d_bad.jpg") == sha(src / "d_bad.jpg")
    assert sorted(p.name for p in (out / "review").iterdir()) == [
        "c_empty.jpg", "d_bad.jpg"]
    log = (out / "review.log").read_text()
    assert log == "c_empty.jpg: no_person\nd_bad.jpg: unreadable\n"
    printed = capsys.readouterr().out
    assert "Skipped e_note.txt" in printed and "Skipped f_img.png" in printed
    assert "Processing a_saved.jpg" in printed


def test_folder_creates_output_and_review_inside(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    make_jpg(src / "a.jpg", 400, 400)
    out = tmp_path / "deep" / "out"
    summary = process_folder(
        src, out, Stub(default=[(50, 50, 200, 200)]), (1, 1), 0.15)
    assert summary["saved"] == 1
    assert (out / "review").is_dir()


def test_folder_sorted_deterministic_order(tmp_path, capsys):
    src = tmp_path / "in"
    src.mkdir()
    make_jpg(src / "z.jpg", 400, 400)
    make_jpg(src / "a.jpg", 400, 400)
    process_folder(src, tmp_path / "out",
                   Stub(default=[(50, 50, 200, 200)]), (1, 1), 0.15)
    printed = capsys.readouterr().out
    assert printed.index("Processing a.jpg") < printed.index("Processing z.jpg")


def test_folder_uppercase_and_jpeg_extensions(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    make_jpg(src / "UP.JPG", 400, 400)
    make_jpg(src / "doc.JPEG", 400, 400)
    (src / "skip.txt").write_text("x")
    summary = process_folder(src, tmp_path / "out",
                             Stub(default=[(50, 50, 200, 200)]), (1, 1), 0.15)
    assert summary == {"processed": 2, "saved": 2, "review": 0, "skipped": 1}


def test_folder_ignores_subdirectories(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    (src / "sub").mkdir()
    make_jpg(src / "sub" / "nested.jpg", 400, 400)
    make_jpg(src / "top.jpg", 400, 400)
    summary = process_folder(src, tmp_path / "out",
                             Stub(default=[(50, 50, 200, 200)]), (1, 1), 0.15)
    assert summary == {"processed": 1, "saved": 1, "review": 0, "skipped": 0}


def test_folder_idempotent_overwrites(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    stub = make_mixed(src)
    out = tmp_path / "out"
    first = process_folder(src, out, stub, None, 0.15)
    second = process_folder(src, out, stub, None, 0.15)
    assert first == second == {"processed": 4, "saved": 2, "review": 2,
                               "skipped": 2}
    assert (out / "review.log").read_text() == (
        "c_empty.jpg: no_person\nd_bad.jpg: unreadable\n")


def test_folder_never_touches_originals(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    stub = make_mixed(src)
    before = {p.name: sha(p) for p in src.iterdir() if p.is_file()}
    process_folder(src, tmp_path / "out", stub, None, 0.15)
    after = {p.name: sha(p) for p in src.iterdir() if p.is_file()}
    assert before == after


def test_folder_missing_input_raises(tmp_path):
    with pytest.raises(OSError):
        process_folder(tmp_path / "nope", tmp_path / "out", Stub(), None, 0.15)
    assert not (tmp_path / "out").exists()


def test_folder_file_as_input_raises(tmp_path):
    f = tmp_path / "f.jpg"
    make_jpg(f, 100, 100)
    with pytest.raises(OSError):
        process_folder(f, tmp_path / "out", Stub(), None, 0.15)


def test_folder_bad_detector_or_options_raise_before_writing(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    make_jpg(src / "a.jpg", 100, 100)
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        process_folder(src, out, object(), None, 0.15)
    with pytest.raises(ValueError):
        process_folder(src, out, Stub(), (0, 2), 0.15)
    with pytest.raises(ValueError):
        process_folder(src, out, Stub(), None, math.nan)
    assert not out.exists()


def test_folder_no_valid_crop_review_line(tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    make_jpg(src / "tall.jpg", 600, 1000)
    summary = process_folder(src, tmp_path / "out",
                             one_box_stub((100, 50, 500, 950)), (3, 2), 0.15)
    assert summary == {"processed": 1, "saved": 0, "review": 1, "skipped": 0}
    assert (tmp_path / "out" / "review.log").read_text() == (
        "tall.jpg: no_valid_crop\n")
