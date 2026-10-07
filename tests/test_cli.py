"""Tests for app.cli (stage 03, build_detector is stubbed, no YOLO)."""

import pathlib

import pytest
from PIL import Image

import app.cli as cli


class Stub:
    def __init__(self, boxes):
        self.boxes = list(boxes)

    def detect_people(self, image):
        return list(self.boxes)


def make_jpg(path, width=800, height=600):
    Image.new("RGB", (width, height), (200, 30, 30)).save(path, "JPEG")
    return path


def run_main(monkeypatch, args, stub):
    monkeypatch.setattr(cli, "build_detector", lambda: stub)
    return cli.main(args)


# --- build_detector: construction contract ------------------------------------


def test_build_detector_uses_expected_weights_and_confidence(monkeypatch):
    seen = {}

    class FakeYOLO:
        def __init__(self, weights, confidence=0.25):
            seen["weights"] = weights
            seen["confidence"] = confidence

    monkeypatch.setattr(cli, "YOLODetector", FakeYOLO)
    cli.build_detector()
    assert seen["weights"] == pathlib.Path("yolo11n.pt")
    assert seen["confidence"] == 0.25


# --- main success paths --------------------------------------------------------


def test_main_saved_and_summary_line(tmp_path, monkeypatch, capsys):
    src = tmp_path / "in"
    src.mkdir()
    make_jpg(src / "a.jpg", 1000, 800)
    out = tmp_path / "out"
    code = run_main(monkeypatch, ["--input", str(src), "--output", str(out),
                                  "--ratio", "1:1", "--margin", "0.15"],
                    Stub([(400, 300, 600, 500)]))
    assert code == 0
    assert (out / "a.jpg").is_file()
    printed = capsys.readouterr().out
    assert "Processing a.jpg" in printed
    assert "Detected 1 person(s)" in printed
    assert "Selected subject bbox" in printed
    assert "Crop:" in printed
    assert "Saved" in printed
    assert "Done: 1 processed, 1 saved, 0 review, 0 skipped" in printed


def test_main_default_ratio_and_margin(tmp_path, monkeypatch, capsys):
    src = tmp_path / "in"
    src.mkdir()
    make_jpg(src / "a.jpg", 800, 600)
    out = tmp_path / "out"
    seen = {}
    real_folder = cli.process_folder

    def spy(input_dir, output_dir, detector, ratio, margin):
        seen["ratio"] = ratio
        seen["margin"] = margin
        return real_folder(input_dir, output_dir, detector, ratio, margin)

    monkeypatch.setattr(cli, "process_folder", spy)
    code = run_main(monkeypatch, ["--input", str(src), "--output", str(out)],
                    Stub([(100, 100, 300, 300)]))
    assert code == 0
    assert seen == {"ratio": None, "margin": 0.15}
    with Image.open(out / "a.jpg") as im:
        w, h = im.size
    assert w * 2 == h * 3  # auto 3:2 on horizontal


def test_main_explicit_ratio_forwarded(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    make_jpg(src / "a.jpg", 800, 600)
    seen = {}

    def spy(input_dir, output_dir, detector, ratio, margin):
        seen["ratio"] = ratio
        return {"processed": 0, "saved": 0, "review": 0, "skipped": 0}

    monkeypatch.setattr(cli, "process_folder", spy)
    code = run_main(monkeypatch, ["--input", str(src), "--output",
                                  str(tmp_path / "o"), "--ratio", "3:2"],
                    Stub([]))
    assert code == 0
    assert seen["ratio"] == (3, 2)


def test_main_all_review_still_zero(tmp_path, monkeypatch, capsys):
    src = tmp_path / "in"
    src.mkdir()
    make_jpg(src / "e.jpg", 500, 500)
    out = tmp_path / "out"
    code = run_main(monkeypatch, ["--input", str(src), "--output", str(out)],
                    Stub([]))
    assert code == 0
    printed = capsys.readouterr().out
    assert "Review (e.jpg: no_person)" in printed
    assert "Done: 1 processed, 0 saved, 1 review, 0 skipped" in printed


def test_main_creates_missing_output(tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    make_jpg(src / "a.jpg", 800, 600)
    out = tmp_path / "new" / "out"
    code = run_main(monkeypatch, ["--input", str(src), "--output", str(out)],
                    Stub([(100, 100, 300, 300)]))
    assert code == 0
    assert (out / "a.jpg").is_file()


# --- argument errors ------------------------------------------------------------


@pytest.mark.parametrize("ratio", ["3x2", "0:2", "3:0", "3:", "ab", "3:2:1", "-1:2"])
def test_main_bad_ratio_exits_2(tmp_path, monkeypatch, ratio):
    src = tmp_path / "in"
    src.mkdir()
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch, ["--input", str(src), "--output",
                               str(tmp_path / "o"), "--ratio", ratio], Stub([]))
    assert exc.value.code == 2


@pytest.mark.parametrize("margin", ["-1", "nan", "inf", "-inf", "abc"])
def test_main_bad_margin_exits_2(tmp_path, monkeypatch, margin):
    src = tmp_path / "in"
    src.mkdir()
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch, ["--input", str(src), "--output",
                               str(tmp_path / "o"), "--margin", margin], Stub([]))
    assert exc.value.code == 2


def test_main_missing_input_dir_nonzero_and_no_output(tmp_path, monkeypatch):
    out = tmp_path / "out"
    code = run_main(monkeypatch, ["--input", str(tmp_path / "nope"),
                                  "--output", str(out)], Stub([]))
    assert code != 0
    assert not out.exists()


def test_main_file_as_input_nonzero(tmp_path, monkeypatch):
    f = tmp_path / "f.jpg"
    make_jpg(f, 100, 100)
    out = tmp_path / "out"
    code = run_main(monkeypatch, ["--input", str(f), "--output", str(out)],
                    Stub([]))
    assert code != 0
    assert not out.exists()


def test_main_missing_required_args(monkeypatch):
    monkeypatch.setattr(cli, "build_detector", lambda: Stub([]))
    with pytest.raises(SystemExit) as exc:
        cli.main(["--input", "somewhere"])
    assert exc.value.code == 2
