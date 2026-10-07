"""Tests for app.detector.YOLODetector (stage 02, simulated backend)."""

import pathlib
import subprocess
import sys
import types

import pytest
from PIL import Image

from app.detector import YOLODetector


# --- Fakes for the ultralytics boundary ------------------------------------


class FakeTensor:
    """Minimal torch-tensor stand-in: only .tolist() is supported."""

    def __init__(self, rows):
        self._rows = rows

    def tolist(self):
        out = []
        for row in self._rows:
            if isinstance(row, (list, tuple)):
                out.append([v for v in row])
            else:
                out.append(row)
        return out


class FakeBoxes:
    def __init__(self, xyxy=None, cls=None, conf=None):
        self.xyxy = xyxy
        self.cls = cls
        self.conf = conf


class FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


def make_yolo_class(*, results=None, error=None, names=None, task="detect",
                    load_log=None, call_log=None):
    """Build a fake ultralytics.YOLO class recording loads and predictions."""

    class FakeYOLO:
        def __init__(self, weights):
            if load_log is not None:
                load_log.append(weights)
            self.names = {0: "person"} if names is None else names
            self.task = task
            self._results = results if results is not None else [FakeResult(None)]
            self._error = error

        def predict(self, image, **kwargs):
            if call_log is not None:
                call_log.append((image, kwargs))
            if self._error is not None:
                raise self._error
            return self._results

    return FakeYOLO


@pytest.fixture
def fake_ultralytics(monkeypatch):
    """Install a fake ``ultralytics`` module; returns a configurator."""
    state = {"yolo_cls": make_yolo_class(), "module": None}

    def _install(**kwargs):
        cls = make_yolo_class(**kwargs)
        state["yolo_cls"] = cls
        mod = types.ModuleType("ultralytics")
        mod.YOLO = cls
        state["module"] = mod
        monkeypatch.setitem(sys.modules, "ultralytics", mod)
        return cls

    _install()
    return _install


def make_weights(tmp_path):
    weights = tmp_path / "yolo11n.pt"
    weights.write_bytes(b"fake-weights")
    return weights


def rgb_image(width=1000, height=800):
    return Image.new("RGB", (width, height), color=(10, 20, 30))


def person_result(boxes, classes=None, confs=None):
    n = len(boxes)
    return FakeResult(
        FakeBoxes(
            xyxy=FakeTensor([list(b) for b in boxes]),
            cls=FakeTensor([0 if classes is None else classes[i] for i in range(n)]),
            conf=FakeTensor([0.9 if confs is None else confs[i] for i in range(n)]),
        )
    )


# --- Prediction arguments and model reuse ----------------------------------


def test_predict_called_with_exact_arguments(fake_ultralytics, tmp_path):
    call_log = []
    fake_ultralytics(results=[person_result([(10.0, 10.0, 50.0, 50.0)])],
                     call_log=call_log)
    image = rgb_image()
    YOLODetector(make_weights(tmp_path), confidence=0.5).detect_people(image)
    assert len(call_log) == 1
    passed_image, kwargs = call_log[0]
    assert passed_image is image
    assert kwargs == {
        "classes": [0],
        "conf": 0.5,
        "device": "cpu",
        "imgsz": 640,
        "augment": False,
        "verbose": False,
        "save": False,
        "save_txt": False,
        "save_crop": False,
    }


def test_two_calls_reuse_single_load(fake_ultralytics, tmp_path):
    load_log, call_log = [], []
    fake_ultralytics(results=[FakeResult(None)], load_log=load_log,
                     call_log=call_log)
    detector = YOLODetector(make_weights(tmp_path))
    image = rgb_image()
    assert detector.detect_people(image) == []
    assert detector.detect_people(image) == []
    assert len(load_log) == 1
    assert len(call_log) == 2


# --- Filtering: class and confidence ---------------------------------------


def test_only_person_class_kept(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[person_result(
        [(10.0, 10.0, 50.0, 50.0), (60.0, 60.0, 90.0, 90.0), (100.0, 100.0, 150.0, 150.0)],
        classes=[0, 1, 2],
    )])
    assert YOLODetector(make_weights(tmp_path)).detect_people(rgb_image()) == [
        (10.0, 10.0, 50.0, 50.0)
    ]


def test_float_class_zero_kept(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[person_result(
        [(10.0, 10.0, 50.0, 50.0)], classes=[0.0],
    )])
    assert YOLODetector(make_weights(tmp_path)).detect_people(rgb_image()) == [
        (10.0, 10.0, 50.0, 50.0)
    ]


@pytest.mark.parametrize(
    ("conf", "kept"),
    [(0.24, False), (0.25, True), (0.9, True)],
)
def test_confidence_threshold_boundaries(fake_ultralytics, tmp_path, conf, kept):
    fake_ultralytics(results=[person_result(
        [(10.0, 10.0, 50.0, 50.0)], confs=[conf],
    )])
    result = YOLODetector(make_weights(tmp_path), confidence=0.25).detect_people(
        rgb_image()
    )
    assert result == [(10.0, 10.0, 50.0, 50.0)] if kept else result == []


def test_backend_order_preserved(fake_ultralytics, tmp_path):
    boxes = [(300.0, 300.0, 400.0, 400.0), (10.0, 10.0, 50.0, 50.0)]
    fake_ultralytics(results=[person_result(boxes)])
    assert YOLODetector(make_weights(tmp_path)).detect_people(rgb_image()) == boxes


def test_fractional_and_edge_boxes_pass_through(fake_ultralytics, tmp_path):
    boxes = [(0.5, 0.25, 999.75, 799.5), (0.0, 0.0, 1000.0, 800.0)]
    fake_ultralytics(results=[person_result(boxes)])
    assert YOLODetector(make_weights(tmp_path)).detect_people(rgb_image()) == boxes


def test_non_person_garbage_rows_are_ignored(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[person_result(
        [(-500.0, -500.0, 5000.0, 5000.0)], classes=[3], confs=[0.99],
    )])
    assert YOLODetector(make_weights(tmp_path)).detect_people(rgb_image()) == []


# --- Empty responses and plain-Python output -------------------------------


def test_none_boxes_is_empty(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[FakeResult(None)])
    assert YOLODetector(make_weights(tmp_path)).detect_people(rgb_image()) == []


def test_zero_rows_is_empty(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[FakeResult(
        FakeBoxes(xyxy=FakeTensor([]), cls=FakeTensor([]), conf=FakeTensor([]))
    )])
    assert YOLODetector(make_weights(tmp_path)).detect_people(rgb_image()) == []


def test_plain_lists_accepted_and_tensors_converted(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[FakeResult(
        FakeBoxes(
            xyxy=[[10.0, 10.0, 50.0, 50.0]],
            cls=[0],
            conf=[0.8],
        )
    )])
    (box,) = YOLODetector(make_weights(tmp_path)).detect_people(rgb_image())
    assert box == (10.0, 10.0, 50.0, 50.0)
    assert type(box) is tuple
    assert all(type(v) is float for v in box)
    assert not hasattr(box, "tolist")


def test_tensor_output_becomes_plain_floats(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[person_result([(10, 20, 50, 60)])])
    (box,) = YOLODetector(make_weights(tmp_path)).detect_people(rgb_image())
    assert box == (10.0, 20.0, 50.0, 60.0)
    assert all(type(v) is float for v in box)


# --- Image validation -------------------------------------------------------


@pytest.mark.parametrize("mode", ["L", "RGBA", "CMYK", "P"])
def test_non_rgb_image_rejected(fake_ultralytics, tmp_path, mode):
    call_log = []
    fake_ultralytics(results=[FakeResult(None)], call_log=call_log)
    detector = YOLODetector(make_weights(tmp_path))
    with pytest.raises(ValueError):
        detector.detect_people(Image.new(mode, (100, 80)))
    assert call_log == []


@pytest.mark.parametrize("bad", [None, "image.jpg", b"bytes", 123, ["RGB"]])
def test_wrong_image_type_rejected(fake_ultralytics, tmp_path, bad):
    call_log = []
    fake_ultralytics(results=[FakeResult(None)], call_log=call_log)
    detector = YOLODetector(make_weights(tmp_path))
    with pytest.raises(ValueError):
        detector.detect_people(bad)
    assert call_log == []


def test_zero_dimension_image_rejected_without_predict(fake_ultralytics, tmp_path):
    from unittest.mock import MagicMock

    call_log = []
    fake_ultralytics(results=[FakeResult(None)], call_log=call_log)
    detector = YOLODetector(make_weights(tmp_path))
    image = MagicMock(spec=Image.Image)
    image.mode = "RGB"
    image.width = 0
    image.height = 100
    with pytest.raises(ValueError):
        detector.detect_people(image)
    assert call_log == []


def test_image_not_mutated(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[person_result([(10.0, 10.0, 50.0, 50.0)])])
    image = rgb_image()
    before = (image.mode, image.size, image.tobytes())
    YOLODetector(make_weights(tmp_path)).detect_people(image)
    assert (image.mode, image.size, image.tobytes()) == before


# --- Constructor validation -------------------------------------------------


@pytest.mark.parametrize(
    "confidence",
    [0, -0.1, 1.5, 2, float("nan"), float("inf"), True, False,
     "0.5", None, 10**400],
)
def test_invalid_confidence_rejected(fake_ultralytics, tmp_path, confidence):
    with pytest.raises(ValueError):
        YOLODetector(make_weights(tmp_path), confidence=confidence)


def test_yolo_not_instantiated_on_invalid_confidence(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    mod = types.ModuleType("ultralytics")
    mod.YOLO = MagicMock()
    monkeypatch.setitem(sys.modules, "ultralytics", mod)
    with pytest.raises(ValueError):
        YOLODetector(make_weights(tmp_path), confidence=0.0)
    mod.YOLO.assert_not_called()


def test_missing_weights_raise_file_not_found(fake_ultralytics, tmp_path):
    with pytest.raises(FileNotFoundError):
        YOLODetector(tmp_path / "missing.pt")


def test_directory_weights_raise_value_error(fake_ultralytics, tmp_path):
    with pytest.raises(ValueError):
        YOLODetector(tmp_path)


def test_yolo_not_instantiated_on_bad_weights(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    mod = types.ModuleType("ultralytics")
    mod.YOLO = MagicMock()
    monkeypatch.setitem(sys.modules, "ultralytics", mod)
    with pytest.raises(FileNotFoundError):
        YOLODetector(tmp_path / "missing.pt")
    mod.YOLO.assert_not_called()


def test_incompatible_class_map_rejected(fake_ultralytics, tmp_path):
    fake_ultralytics(names={0: "car", 1: "person"})
    with pytest.raises(ValueError):
        YOLODetector(make_weights(tmp_path))


def test_missing_person_class_rejected(fake_ultralytics, tmp_path):
    fake_ultralytics(names={1: "bicycle", 2: "car"})
    with pytest.raises(ValueError):
        YOLODetector(make_weights(tmp_path))


def test_non_detection_task_rejected(fake_ultralytics, tmp_path):
    fake_ultralytics(task="segment")
    with pytest.raises(ValueError):
        YOLODetector(make_weights(tmp_path))


def test_load_errors_propagate(tmp_path, monkeypatch):
    class BrokenYOLO:
        def __init__(self, weights):
            raise RuntimeError("load boom")

    mod = types.ModuleType("ultralytics")
    mod.YOLO = BrokenYOLO
    monkeypatch.setitem(sys.modules, "ultralytics", mod)
    with pytest.raises(RuntimeError, match="load boom"):
        YOLODetector(make_weights(tmp_path))


def test_inference_errors_are_not_empty(fake_ultralytics, tmp_path):
    fake_ultralytics(error=RuntimeError("infer boom"))
    detector = YOLODetector(make_weights(tmp_path))
    with pytest.raises(RuntimeError, match="infer boom"):
        detector.detect_people(rgb_image())


# --- Malformed backend responses -------------------------------------------


def test_no_results_is_runtime_error(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[])
    with pytest.raises(RuntimeError, match="result"):
        YOLODetector(make_weights(tmp_path)).detect_people(rgb_image())


def test_two_results_is_runtime_error(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[FakeResult(None), FakeResult(None)])
    with pytest.raises(RuntimeError, match="result"):
        YOLODetector(make_weights(tmp_path)).detect_people(rgb_image())


def test_misaligned_rows_is_runtime_error(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[FakeResult(FakeBoxes(
        xyxy=FakeTensor([[10.0, 10.0, 50.0, 50.0], [60.0, 60.0, 90.0, 90.0]]),
        cls=FakeTensor([0]),
        conf=FakeTensor([0.9, 0.8]),
    ))])
    with pytest.raises(RuntimeError, match="misaligned"):
        YOLODetector(make_weights(tmp_path)).detect_people(rgb_image())


def test_misaligned_conf_is_runtime_error(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[FakeResult(FakeBoxes(
        xyxy=FakeTensor([[10.0, 10.0, 50.0, 50.0]]),
        cls=FakeTensor([0]),
        conf=FakeTensor([0.9, 0.8]),
    ))])
    with pytest.raises(RuntimeError, match="misaligned"):
        YOLODetector(make_weights(tmp_path)).detect_people(rgb_image())


@pytest.mark.parametrize(
    "box",
    [
        (-1.0, 10.0, 50.0, 50.0),  # negative
        (10.0, 10.0, 5000.0, 50.0),  # past right edge
        (10.0, 10.0, 50.0, 900.0),  # past bottom edge
        (50.0, 10.0, 10.0, 50.0),  # inverted
        (float("nan"), 10.0, 50.0, 50.0),  # non-finite
        (10.0, float("inf"), 50.0, 50.0),
    ],
)
def test_invalid_retained_box_is_runtime_error(fake_ultralytics, tmp_path, box):
    fake_ultralytics(results=[person_result([box])])
    with pytest.raises(RuntimeError, match="box"):
        YOLODetector(make_weights(tmp_path)).detect_people(rgb_image())


@pytest.mark.parametrize("conf", [float("nan"), float("inf"), float("-inf")])
def test_invalid_retained_confidence_is_runtime_error(
    fake_ultralytics, tmp_path, conf
):
    fake_ultralytics(results=[person_result(
        [(10.0, 10.0, 50.0, 50.0)], confs=[conf],
    )])
    with pytest.raises(RuntimeError, match="confidence"):
        YOLODetector(make_weights(tmp_path)).detect_people(rgb_image())


def test_huge_int_box_is_runtime_error(fake_ultralytics, tmp_path):
    huge = 10**400
    fake_ultralytics(results=[person_result(
        [(huge, 0, huge + 10, 10)], confs=[0.9],
    )])
    with pytest.raises(RuntimeError, match="box"):
        YOLODetector(make_weights(tmp_path)).detect_people(rgb_image(64, 64))


def test_huge_int_confidence_is_runtime_error(fake_ultralytics, tmp_path):
    fake_ultralytics(results=[person_result(
        [(10.0, 10.0, 50.0, 50.0)], confs=[10**400],
    )])
    with pytest.raises(RuntimeError, match="confidence"):
        YOLODetector(make_weights(tmp_path)).detect_people(rgb_image(64, 64))


# --- Import hygiene ---------------------------------------------------------


def test_importing_modules_does_not_load_ultralytics():
    code = (
        "import sys; import app.detector; import app.subject; "
        "print('ultralytics' in sys.modules, 'torch' in sys.modules)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=pathlib.Path(__file__).resolve().parent.parent,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "False False"


# --- Union with selection and crop math (no real model) ---------------------


def test_union_select_and_crop_centered(fake_ultralytics, tmp_path):
    from app.crop import calculate_crop
    from app.subject import select_subject

    fake_ultralytics(results=[person_result([(400, 300, 600, 500)])])
    image = rgb_image(1000, 800)
    detected = YOLODetector(make_weights(tmp_path)).detect_people(image)
    subject = select_subject(detected)
    assert subject == (400.0, 300.0, 600.0, 500.0)
    assert calculate_crop(1000, 800, subject, (1, 1), 0.15) == (370, 270, 630, 530)


def test_union_winner_reaches_crop_intact(fake_ultralytics, tmp_path):
    from app.crop import calculate_crop
    from app.subject import select_subject

    boxes = [(10.0, 10.0, 60.0, 60.0), (400.0, 300.0, 600.0, 500.0)]
    fake_ultralytics(results=[person_result(boxes)])
    image = rgb_image(1000, 800)
    detected = YOLODetector(make_weights(tmp_path)).detect_people(image)
    subject = select_subject(detected)
    assert subject == (400.0, 300.0, 600.0, 500.0)
    assert calculate_crop(1000, 800, subject, (1, 1), 0.15) == (370, 270, 630, 530)


def test_union_empty_never_invents_a_box(fake_ultralytics, tmp_path):
    from app.subject import select_subject

    fake_ultralytics(results=[FakeResult(None)])
    detected = YOLODetector(make_weights(tmp_path)).detect_people(rgb_image())
    assert detected == []
    assert select_subject(detected) is None


def test_union_impossible_crop_is_none_not_absence(fake_ultralytics, tmp_path):
    from app.crop import calculate_crop
    from app.subject import select_subject

    fake_ultralytics(results=[person_result([(100, 50, 500, 950)])])
    image = rgb_image(600, 1000)
    detected = YOLODetector(make_weights(tmp_path)).detect_people(image)
    subject = select_subject(detected)
    assert subject == (100.0, 50.0, 500.0, 950.0)
    assert calculate_crop(600, 1000, subject, (3, 2), 0.15) is None
