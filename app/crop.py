from __future__ import annotations

import fractions
import math


def _floor_exact(v: int | float) -> int:
    return v if isinstance(v, int) else math.floor(v)


def _ceil_exact(v: int | float) -> int:
    return v if isinstance(v, int) else math.ceil(v)


def calculate_crop(
    image_width: int,
    image_height: int,
    subject_bbox: tuple[float, float, float, float],
    aspect_ratio: tuple[int, int],
    margin: float,
) -> tuple[int, int, int, int] | None:
    """Calculate crop rectangle (left, top, right, bottom) with exact aspect ratio.

    Margin is a non-negative finite number applied on each side relative to
    the original bbox dimensions (``0.15`` adds 15% of the box width on each
    side and 15% of the height above and below). The reduced ``(p, q)`` pair
    requires exact sizes ``(k*p, k*q)`` with positive integer ``k``.
    The subject box ``(left, top, right, bottom)`` must satisfy
    ``0 <= left < right <= image_width`` and ``0 <= top < bottom <=
    image_height``; integer and fractional coordinates are accepted.

    Raises ``ValueError`` on invalid inputs: non-integer or non-positive
    image dimensions, boxes that are not 4-tuples of finite numbers or are
    empty/inverted/out of bounds, ratios that are not 2-tuples of positive
    integers, negative or non-finite margins, ``None`` or wrong types or
    lengths, and booleans anywhere (booleans are never valid numbers).
    Returns ``None`` only when the inputs are valid but no integer crop with
    the exact ratio can contain the whole subject; the subject is never
    cropped partially.

    Position rounds the ideal origin (subject center minus half the crop
    size) down and clamps it into the feasible interval; on half-pixel
    ties the smaller origin wins. Margins near borders may end up
    asymmetric and shrink when the full margin does not fit.
    """
    if isinstance(image_width, bool) or not isinstance(image_width, int):
        raise ValueError
    if isinstance(image_height, bool) or not isinstance(image_height, int):
        raise ValueError
    if image_width <= 0 or image_height <= 0:
        raise ValueError

    if subject_bbox is None or not isinstance(subject_bbox, tuple) or len(subject_bbox) != 4:
        raise ValueError
    left, top, right, bottom = subject_bbox
    for v in (left, top, right, bottom):
        if isinstance(v, bool):
            raise ValueError
        if not isinstance(v, (int, float)):
            raise ValueError
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError
    left_f = left
    top_f = top
    right_f = right
    bottom_f = bottom
    if left_f >= right_f or top_f >= bottom_f:
        raise ValueError
    if left_f < 0 or right_f > image_width or top_f < 0 or bottom_f > image_height:
        raise ValueError

    if aspect_ratio is None or not isinstance(aspect_ratio, tuple) or len(aspect_ratio) != 2:
        raise ValueError
    a_r, b_r = aspect_ratio
    if isinstance(a_r, bool) or isinstance(b_r, bool):
        raise ValueError
    if not isinstance(a_r, int) or not isinstance(b_r, int):
        raise ValueError
    if a_r <= 0 or b_r <= 0:
        raise ValueError

    if isinstance(margin, bool):
        raise ValueError
    if not isinstance(margin, (int, float)) or margin < 0:
        raise ValueError
    if isinstance(margin, float) and not math.isfinite(margin):
        raise ValueError
    margin_q = fractions.Fraction(margin)

    g = math.gcd(a_r, b_r)
    p, q = a_r // g, b_r // g

    bx0 = _floor_exact(left_f)
    by0 = _floor_exact(top_f)
    bx1 = _ceil_exact(right_f)
    by1 = _ceil_exact(bottom_f)
    sub_w = bx1 - bx0
    sub_h = by1 - by0

    # Exact rational arithmetic: Fraction(int) and Fraction(float) are both
    # exact, so arbitrarily large ints never collapse via float conversion.
    left_q = fractions.Fraction(left_f)
    top_q = fractions.Fraction(top_f)
    right_q = fractions.Fraction(right_f)
    bottom_q = fractions.Fraction(bottom_f)
    bw = right_q - left_q
    bh = bottom_q - top_q

    max_k_by_w = image_width // p
    max_k_by_h = image_height // q
    max_k = min(max_k_by_w, max_k_by_h)
    if max_k < 1:
        return None

    target_w_box = bw * (1 + 2 * margin_q)
    target_h_box = bh * (1 + 2 * margin_q)

    if target_w_box > image_width:
        k_w = max_k
    else:
        k_w = math.ceil(target_w_box / p)

    if target_h_box > image_height:
        k_h = max_k
    else:
        k_h = math.ceil(target_h_box / q)

    k = max(k_w, k_h, -(-sub_w // p), -(-sub_h // q))
    if k > max_k:
        k = max_k

    crop_w_eff = k * p
    crop_h_eff = k * q
    if crop_w_eff < sub_w or crop_h_eff < sub_h:
        return None

    cx = (left_q + right_q) / 2
    cy = (top_q + bottom_q) / 2
    ideal_left = cx - fractions.Fraction(crop_w_eff, 2)
    ideal_top = cy - fractions.Fraction(crop_h_eff, 2)

    min_left = bx1 - crop_w_eff
    max_left = _floor_exact(left_f)
    if min_left < 0:
        min_left = 0
    if max_left > image_width - crop_w_eff:
        max_left = image_width - crop_w_eff
    min_top = by1 - crop_h_eff
    max_top = _floor_exact(top_f)
    if min_top < 0:
        min_top = 0
    if max_top > image_height - crop_h_eff:
        max_top = image_height - crop_h_eff

    crop_left = math.floor(ideal_left)
    if crop_left < min_left:
        crop_left = min_left
    if crop_left > max_left:
        crop_left = max_left

    crop_top = math.floor(ideal_top)
    if crop_top < min_top:
        crop_top = min_top
    if crop_top > max_top:
        crop_top = max_top

    return (crop_left, crop_top, crop_left + crop_w_eff, crop_top + crop_h_eff)
