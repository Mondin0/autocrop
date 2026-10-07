"""Subject selection by box area (stage 02).

Pure function: no I/O, no Pillow, no Ultralytics. Picks the largest-area
box; ties go to the first box in the sequence.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def _check_coordinate(value: int | float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid coordinate: {value!r}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"invalid coordinate: {value!r}")


def select_subject(
    boxes: Sequence[tuple[float, float, float, float]],
) -> tuple[float, float, float, float] | None:
    """Return the box with the largest area, or ``None`` when empty.

    Accepts a list or tuple of 4-tuples ``(left, top, right, bottom)`` with
    finite ``int``/``float`` coordinates (never booleans), non-negative and
    ordered as ``left < right`` and ``top < bottom``. Every box is validated
    while scanning, so an invalid box raises ``ValueError`` even when it
    would not have won. Ties keep the first box. The input sequence and the
    winning box are returned unchanged.
    """
    if isinstance(boxes, (str, bytes, bytearray)) or not isinstance(boxes, Sequence):
        raise ValueError(f"boxes must be a list or tuple, got {type(boxes).__name__}")
    if len(boxes) == 0:
        return None
    best: tuple[float, float, float, float] | None = None
    best_area: int | float = 0
    for box in boxes:
        if not isinstance(box, tuple) or len(box) != 4:
            raise ValueError(f"invalid box: {box!r}")
        left, top, right, bottom = box
        for value in (left, top, right, bottom):
            _check_coordinate(value)
        if left < 0 or top < 0 or not left < right or not top < bottom:
            raise ValueError(f"invalid box: {box!r}")
        area = (right - left) * (bottom - top)
        if best is None or area > best_area:
            best, best_area = box, area
    return best
