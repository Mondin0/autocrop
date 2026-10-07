"""YOLO person detector adapter (stage 02).

Loads a local Ultralytics detection model once per instance and runs CPU
inference on an already-loaded RGB Pillow image. Only class 0 (person)
detections at or above the confidence threshold are returned, in backend
order, as plain float ``(left, top, right, bottom)`` tuples.
"""

from __future__ import annotations

import math
import pathlib

from PIL import Image


def _validate_confidence(confidence: float) -> float:
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError(f"invalid confidence: {confidence!r}")
    if isinstance(confidence, float) and not math.isfinite(confidence):
        raise ValueError(f"invalid confidence: {confidence!r}")
    if not 0 < confidence <= 1:
        raise ValueError(f"invalid confidence: {confidence!r}")
    return float(confidence)


def _as_rows(value: object) -> list:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()  # type: ignore[union-attr]
    return list(value)  # type: ignore[arg-type]


def _checked_box(raw_box: object, width: int, height: int) -> tuple[float, ...]:
    try:
        coords = tuple(raw_box)  # type: ignore[arg-type]
    except TypeError as exc:
        raise RuntimeError(f"invalid retained box: {raw_box!r}") from exc
    if len(coords) != 4:
        raise RuntimeError(f"invalid retained box: {raw_box!r}")
    clean = []
    for value in coords:
        if isinstance(value, bool):
            raise RuntimeError(f"invalid retained box: {raw_box!r}")
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError(f"invalid retained box: {raw_box!r}") from exc
        if not math.isfinite(number):
            raise RuntimeError(f"invalid retained box: {raw_box!r}")
        clean.append(number)
    left, top, right, bottom = clean
    if not 0 <= left < right <= width or not 0 <= top < bottom <= height:
        raise RuntimeError(
            f"invalid retained box {(left, top, right, bottom)!r}"
            f" for image {width}x{height}"
        )
    return (left, top, right, bottom)


class YOLODetector:
    """Detect people in an RGB image with a YOLO detection model."""

    def __init__(self, weights: pathlib.Path, confidence: float = 0.25) -> None:
        """Load the model from a local ``.pt`` file.

        Raises ``ValueError`` for an invalid threshold, a non-path ``weights``
        or a directory, or a model whose task is not detection / whose class
        map lacks ``0: person``. Raises ``FileNotFoundError`` when the weights
        file does not exist. Other load errors propagate untouched.
        """
        threshold = _validate_confidence(confidence)
        if isinstance(weights, str):
            weights = pathlib.Path(weights)
        if not isinstance(weights, pathlib.Path):
            raise ValueError(f"invalid weights path: {weights!r}")
        if weights.is_dir():
            raise ValueError(f"weights is a directory: {weights}")
        if not weights.is_file():
            raise FileNotFoundError(f"weights not found: {weights}")
        from ultralytics import YOLO

        model = YOLO(str(weights))
        task = getattr(model, "task", None)
        if task is not None and task != "detect":
            raise ValueError(f"model task is not detection: {task!r}")
        names = getattr(model, "names", None)
        if not isinstance(names, dict) or names.get(0) != "person":
            raise ValueError(f"model has no 0: person class map: {names!r}")
        self._model = model
        self._confidence = threshold

    def detect_people(
        self, image: Image.Image
    ) -> list[tuple[float, float, float, float]]:
        """Return person boxes as float ``(left, top, right, bottom)`` tuples.

        ``image`` must be an RGB Pillow image with positive dimensions;
        anything else raises ``ValueError`` before any inference. An image
        without detections returns ``[]``. Structurally invalid backend
        responses (result count other than one, misaligned rows) or an
        invalid retained person box/confidence raise ``RuntimeError``.
        Inference errors propagate; the image is never mutated or saved.
        """
        if not isinstance(image, Image.Image):
            raise ValueError(f"image must be a Pillow image, got {type(image).__name__}")
        if image.mode != "RGB":
            raise ValueError(f"image must be RGB, got mode {image.mode!r}")
        width, height = image.width, image.height
        if width <= 0 or height <= 0:
            raise ValueError(f"image has non-positive dimensions: {width}x{height}")
        results = self._model.predict(
            image,
            classes=[0],
            conf=self._confidence,
            device="cpu",
            imgsz=640,
            augment=False,
            verbose=False,
            save=False,
            save_txt=False,
            save_crop=False,
        )
        if not isinstance(results, list) or len(results) != 1:
            count = len(results) if isinstance(results, list) else "non-list"
            raise RuntimeError(f"expected exactly one result, got {count}")
        boxes = getattr(results[0], "boxes", None)
        if boxes is None:
            return []
        try:
            xyxy = _as_rows(getattr(boxes, "xyxy", None))
            classes = _as_rows(getattr(boxes, "cls", None))
            confidences = _as_rows(getattr(boxes, "conf", None))
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"misaligned backend response: {exc}") from exc
        if not len(xyxy) == len(classes) == len(confidences):
            raise RuntimeError(
                "misaligned backend response:"
                f" {len(xyxy)} boxes, {len(classes)} classes,"
                f" {len(confidences)} confidences"
            )
        people = []
        for raw_box, raw_class, raw_conf in zip(xyxy, classes, confidences):
            try:
                class_id = float(raw_class)  # type: ignore[arg-type]
            except (TypeError, ValueError, OverflowError) as exc:
                raise RuntimeError(
                    f"invalid backend class: {raw_class!r}"
                ) from exc
            if class_id != 0:
                continue
            try:
                conf_value = float(raw_conf)  # type: ignore[arg-type]
            except (TypeError, ValueError, OverflowError) as exc:
                raise RuntimeError(
                    f"invalid retained confidence: {raw_conf!r}"
                ) from exc
            if isinstance(raw_conf, bool) or not math.isfinite(conf_value):
                raise RuntimeError(f"invalid retained confidence: {raw_conf!r}")
            if conf_value < self._confidence:
                continue
            people.append(_checked_box(raw_box, width, height))
        return people
