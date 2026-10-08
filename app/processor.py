"""Image processing pipeline (stage 03).

Opens JPEGs, applies EXIF orientation, detects people with a duck-typed
detector, selects the largest-area subject, computes the crop and saves it.
Photos without a person, without a valid crop, or unreadable are copied
unchanged to ``review/`` with a logged reason; originals are never modified.
"""

from __future__ import annotations

import math
import pathlib
import shutil

from PIL import Image, ImageOps

from app.crop import calculate_crop
from app.subject import select_subject

_JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})
_REVIEW_LOG = "review.log"


def default_ratio(width: int, height: int) -> tuple[int, int]:
    """Return the automatic aspect ratio: 3:2, 2:3, or 1:1 when square."""
    for value in (width, height):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"invalid dimension: {value!r}")
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid dimensions: {width!r}x{height!r}")
    if width > height:
        return (3, 2)
    if height > width:
        return (2, 3)
    return (1, 1)


def _check_ratio(ratio: tuple[int, int] | None) -> None:
    if ratio is None:
        return
    if not isinstance(ratio, tuple) or len(ratio) != 2:
        raise ValueError(f"invalid ratio: {ratio!r}")
    width, height = ratio
    if isinstance(width, bool) or isinstance(height, bool):
        raise ValueError(f"invalid ratio: {ratio!r}")
    if not isinstance(width, int) or not isinstance(height, int):
        raise ValueError(f"invalid ratio: {ratio!r}")
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid ratio: {ratio!r}")


def _check_margin(margin: float) -> None:
    if isinstance(margin, bool) or not isinstance(margin, (int, float)):
        raise ValueError(f"invalid margin: {margin!r}")
    if margin < 0:
        raise ValueError(f"invalid margin: {margin!r}")
    if isinstance(margin, float) and not math.isfinite(margin):
        raise ValueError(f"invalid margin: {margin!r}")


def _check_detector(detector: object) -> None:
    if not callable(getattr(detector, "detect_people", None)):
        raise ValueError(f"detector has no detect_people method: {detector!r}")


def _check_dir_pair(*paths: pathlib.Path) -> None:
    for path in paths:
        if not isinstance(path, pathlib.Path):
            raise ValueError(f"path must be a pathlib.Path: {path!r}")


def validate_folder_paths(input_dir: pathlib.Path, output_dir: pathlib.Path) -> None:
    """Reject a folder destination that resolves to the input folder."""
    if input_dir.resolve() == output_dir.resolve():
        raise FileExistsError(
            "input and output resolve to the same directory: "
            f"{input_dir}")


def _reject_original_destination(
    image_path: pathlib.Path, *destinations: pathlib.Path
) -> None:
    source = image_path.resolve()
    for destination in destinations:
        if destination.resolve() == source or (
            destination.exists() and destination.samefile(image_path)
        ):
            raise FileExistsError(
                f"output would overwrite original image: {image_path}")


def _reject_batch_destinations(
    entries: list[pathlib.Path],
    output_dir: pathlib.Path,
    review_dir: pathlib.Path,
    log_path: pathlib.Path,
) -> None:
    """Reject batch destinations aliasing any original before any write."""
    by_resolved: dict[pathlib.Path, pathlib.Path] = {}
    by_stat: dict[tuple[int, int], pathlib.Path] = {}
    for source in entries:
        by_resolved.setdefault(source.resolve(), source)
        try:
            stat = source.stat()
        except OSError:
            continue
        by_stat.setdefault((stat.st_dev, stat.st_ino), source)

    def check(destination: pathlib.Path) -> None:
        hit = by_resolved.get(destination.resolve())
        if hit is None:
            try:
                if destination.exists():
                    stat = destination.stat()
                    hit = by_stat.get((stat.st_dev, stat.st_ino))
            except OSError:
                hit = None
        if hit is not None:
            raise FileExistsError(
                f"output would overwrite original image: {hit}")

    for source in entries:
        check(output_dir / source.name)
        check(review_dir / source.name)
    check(log_path)


def _execute(
    image_path: pathlib.Path,
    output_dir: pathlib.Path,
    review_dir: pathlib.Path,
    detector: object,
    ratio: tuple[int, int] | None,
    margin: float,
) -> tuple[str, str, dict]:
    """Run the full pipeline for one file; return (status, detail, info)."""
    name = image_path.name
    try:
        with Image.open(image_path) as handle:
            image = ImageOps.exif_transpose(handle).convert("RGB")
            image.load()
    except Exception:
        shutil.copy2(image_path, review_dir / name)
        return ("review", "unreadable",
                {"boxes": [], "subject": None, "crop": None})
    boxes = detector.detect_people(image)  # type: ignore[union-attr]
    subject = select_subject(boxes)
    if subject is None:
        shutil.copy2(image_path, review_dir / name)
        return ("review", "no_person",
                {"boxes": list(boxes), "subject": None, "crop": None})
    effective = ratio if ratio is not None else default_ratio(*image.size)
    crop = calculate_crop(image.width, image.height, subject, effective, margin)
    if crop is None:
        shutil.copy2(image_path, review_dir / name)
        return ("review", "no_valid_crop",
                {"boxes": list(boxes), "subject": subject, "crop": None})
    destination = output_dir / name
    image.crop(crop).save(destination, format="JPEG", quality=95)
    return ("saved", str(destination),
            {"boxes": list(boxes), "subject": subject, "crop": crop})


def process_image(
    image_path: pathlib.Path,
    output_dir: pathlib.Path,
    review_dir: pathlib.Path,
    detector: object,
    ratio: tuple[int, int] | None,
    margin: float,
) -> tuple[str, str]:
    """Process one image; return ``("saved", path)`` or ``("review", reason)``."""
    _check_detector(detector)
    _check_dir_pair(image_path, output_dir, review_dir)
    _check_ratio(ratio)
    _check_margin(margin)
    _reject_original_destination(
        image_path, output_dir / image_path.name, review_dir / image_path.name)
    output_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    status, detail, _info = _execute(
        image_path, output_dir, review_dir, detector, ratio, margin)
    return (status, detail)


def process_folder(
    input_dir: pathlib.Path,
    output_dir: pathlib.Path,
    detector: object,
    ratio: tuple[int, int] | None,
    margin: float,
) -> dict[str, int]:
    """Process top-level JPEGs of ``input_dir``; never fail on one bad photo."""
    _check_detector(detector)
    _check_dir_pair(input_dir, output_dir)
    _check_ratio(ratio)
    _check_margin(margin)
    if not input_dir.exists():
        raise FileNotFoundError(f"input directory not found: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"input is not a directory: {input_dir}")
    validate_folder_paths(input_dir, output_dir)
    review_dir = output_dir / "review"
    log_path = output_dir / _REVIEW_LOG
    entries = sorted(input_dir.iterdir(), key=lambda p: p.name)
    batch = [entry for entry in entries
             if entry.is_file() and entry.suffix.lower() in _JPEG_SUFFIXES]
    _reject_batch_destinations(batch, output_dir, review_dir, log_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    summary = {"processed": 0, "saved": 0, "review": 0, "skipped": 0}
    log_lines = []
    for entry in entries:
        if entry.is_dir() or not entry.is_file():
            continue
        if entry.suffix.lower() not in _JPEG_SUFFIXES:
            print(f"Skipped {entry.name}: unsupported extension")
            summary["skipped"] += 1
            continue
        summary["processed"] += 1
        print(f"Processing {entry.name}")
        status, detail, info = _execute(
            entry, output_dir, review_dir, detector, ratio, margin)
        print(f"Detected {len(info['boxes'])} person(s)")
        if info["subject"] is not None:
            print(f"Selected subject bbox: {info['subject']!r}")
        if info["crop"] is not None:
            print(f"Crop: {info['crop']!r}")
        if status == "saved":
            print(f"Saved {detail}")
            summary["saved"] += 1
        else:
            print(f"Review ({entry.name}: {detail})")
            summary["review"] += 1
            log_lines.append(f"{entry.name}: {detail}\n")
    (output_dir / _REVIEW_LOG).write_text("".join(log_lines), encoding="utf-8")
    return summary
