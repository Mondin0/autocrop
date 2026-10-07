"""Command-line interface (stage 03).

Thin layer: parse arguments, build the detector once, run ``process_folder``.
"""

from __future__ import annotations

import argparse
import math
import pathlib
import sys

from app.detector import YOLODetector
from app.processor import process_folder


def build_detector() -> YOLODetector:
    """Build the production detector: ``yolo11n.pt`` with confidence 0.25."""
    return YOLODetector(pathlib.Path("yolo11n.pt"), 0.25)


def _parse_ratio(text: str) -> tuple[int, int]:
    try:
        width_text, height_text = text.split(":")
        width, height = int(width_text), int(height_text)
    except (ValueError, AttributeError) as exc:
        raise argparse.ArgumentTypeError(f"invalid ratio: {text!r}") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError(f"invalid ratio: {text!r}")
    return (width, height)


def _parse_margin(text: str) -> float:
    try:
        value = float(text)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError(f"invalid margin: {text!r}") from exc
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(f"invalid margin: {text!r}")
    return value


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return the exit code."""
    parser = argparse.ArgumentParser(
        description="Crop sports photos around the main subject.")
    parser.add_argument("--input", required=True, help="folder with JPEGs")
    parser.add_argument("--output", required=True, help="output folder")
    parser.add_argument("--ratio", type=_parse_ratio, default=None,
                        help="aspect ratio W:H, e.g. 3:2 (default: automatic)")
    parser.add_argument("--margin", type=_parse_margin, default=0.15,
                        help="margin around the subject (default: 0.15)")
    args = parser.parse_args(argv)
    input_dir = pathlib.Path(args.input)
    output_dir = pathlib.Path(args.output)
    if not input_dir.is_dir():
        print(f"error: input directory not found: {input_dir}",
              file=sys.stderr)
        return 1
    detector = build_detector()
    try:
        summary = process_folder(
            input_dir, output_dir, detector, args.ratio, args.margin)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Done: {summary['processed']} processed, {summary['saved']} saved, "
          f"{summary['review']} review, {summary['skipped']} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
