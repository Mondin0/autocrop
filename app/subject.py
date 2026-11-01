"""Subject selection: historical area rule plus V2-12 visual target.

``select_subject`` keeps the stage-02 contract: the largest-area box.
``select_target`` (stage V2-12) adds formation preservation and visual
evidence. Both are deterministic and free of I/O beyond reading pixels
from the Pillow image already in memory.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from PIL import Image, ImageFilter, ImageStat

# --- V2-12 selection parameters (documented in the stage registro) ------------
# Candidate clusters: two detections are linked when their heights differ by at
# most 2x (same distance to the camera), their horizontal gap is at most half
# the narrower box and their vertical centres are close.
GROUP_RATIO = (3, 2)
_NEAR_GAP_FACTOR = 0.5
_NEAR_HEIGHT_RATIO = 0.5
_NEAR_CENTER_FACTOR = 0.75
# Proximity alone is not a formation (director findings R1/R3): after merging
# duplicate detections, a structured formation needs a ground-aligned row of at
# least three detections with coherent scale and separated centres. Compact
# plays, pairs and rows with very different heights stay individual.
_MIN_FORMATION_MEMBERS = 3
_FORMATION_ROW_TOLERANCE = 0.25
_FORMATION_HEIGHT_SPREAD = 1.35
_FORMATION_WIDTH_SPREAD = 2.0
_FORMATION_CENTER_GAP = 0.2
# Detections that share a real region belong to the same body/team (a head or
# torso box inside its body box, or bodies of two rows occluding each other).
_OCCLUSION_OVERLAP = 0.1
_DUPLICATE_IOU = 0.8
# Individual evidence: focus is the primary clue of the intended subject
# (0.60), while relative area (0.20) and centrality (0.20) act as context
# tie-breakers, so a large but soft foreground cannot outvote clearly sharper
# relevant evidence. Equal-relevance candidates need a relative sharpness gap
# above the ambiguity margin before one is chosen.
_FOCUS_WEIGHT = 0.60
_SIZE_WEIGHT = 0.20
_CENTER_WEIGHT = 0.20
_AMBIGUITY_MARGIN = 0.10
# R7: a leader that wins the stable context (size + position, weights 0.20 +
# 0.20) by at least the tie margin itself and keeps >= 80% of the sharpest
# candidate's focus is not a real duel. Both clues must agree; a 20% relative
# focus gap is treated as meaningful defocus, below it as texture noise.
_CONTEXT_DOMINANCE = 0.10
_MIN_DOMINANT_FOCUS = 0.8
_RELEVANCE_AREA_FLOOR = 0.15
_LAPLACIAN = ImageFilter.Kernel(
    (3, 3), (0, -1, 0, -1, 4, -1, 0, -1, 0), scale=1, offset=0)


def _check_coordinate(value: int | float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid coordinate: {value!r}")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"invalid coordinate: {value!r}")


def _check_image(image: object) -> None:
    if not isinstance(image, Image.Image):
        raise ValueError(f"image must be a Pillow image, got {type(image).__name__}")
    if image.mode != "RGB":
        raise ValueError(f"image must be RGB, got mode {image.mode!r}")
    if image.width <= 0 or image.height <= 0:
        raise ValueError(f"invalid image size: {image.width}x{image.height}")


def _checked_boxes(
    image: Image.Image,
    boxes: object,
) -> list[tuple[float, float, float, float]]:
    if isinstance(boxes, (str, bytes, bytearray)) or not isinstance(boxes, Sequence):
        raise ValueError(f"boxes must be a list or tuple, got {type(boxes).__name__}")
    checked = []
    for box in boxes:
        if not isinstance(box, tuple) or len(box) != 4:
            raise ValueError(f"invalid box: {box!r}")
        left, top, right, bottom = box
        for value in (left, top, right, bottom):
            _check_coordinate(value)
        if left < 0 or top < 0 or not left < right or not top < bottom:
            raise ValueError(f"invalid box: {box!r}")
        if right > image.width or bottom > image.height:
            raise ValueError(f"box outside image: {box!r}")
        checked.append(box)
    return checked


def _width_height(box: tuple[float, ...]) -> tuple[float, float]:
    return box[2] - box[0], box[3] - box[1]


def _area(box: tuple[float, ...]) -> float:
    width, height = _width_height(box)
    return width * height


def _center(box: tuple[float, ...]) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _same_formation(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    first_width, first_height = _width_height(first)
    second_width, second_height = _width_height(second)
    smallest_height = min(first_height, second_height)
    if max(first_height, second_height) > smallest_height / _NEAR_HEIGHT_RATIO:
        return False
    gap = max(0.0, max(first[0], second[0]) - min(first[2], second[2]))
    if gap > _NEAR_GAP_FACTOR * min(first_width, second_width):
        return False
    return abs(_center(first)[1] - _center(second)[1]) <= (
        _NEAR_CENTER_FACTOR * smallest_height)


def _formation_clusters(
    boxes: Sequence[tuple[float, float, float, float]],
) -> list[list[int]]:
    """Group box indexes by near, same-scale detections; first-seen order."""
    parent = list(range(len(boxes)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for first in range(len(boxes)):
        for second in range(first + 1, len(boxes)):
            if _same_formation(boxes[first], boxes[second]):
                parent[find(second)] = find(first)
    clusters: dict[int, list[int]] = {}
    for index in range(len(boxes)):
        clusters.setdefault(find(index), []).append(index)
    return list(clusters.values())


def _envelope(
    boxes: Sequence[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    return (min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes))


def _bottom_rows(
    boxes: Sequence[tuple[float, float, float, float]],
) -> list[list[tuple[float, float, float, float]]]:
    """Split detections into rows sharing a ground line.

    The tolerance is anchored to the first (smallest) bottom of each row, so a
    chain of small steps cannot accumulate past it.
    """
    heights = sorted(_width_height(box)[1] for box in boxes)
    tolerance = _FORMATION_ROW_TOLERANCE * heights[len(heights) // 2]
    rows: list[list[tuple[float, float, float, float]]] = []
    for box in sorted(boxes, key=lambda item: item[3]):
        if rows and box[3] - rows[-1][0][3] <= tolerance:
            rows[-1].append(box)
        else:
            rows.append([box])
    return rows


def _iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    union = _area(first) + _area(second) - intersection
    return intersection / union if union else 0.0


def _overlap_area(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def _related_body(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    """True when two detections share a substantial body/team region.

    A head or torso box inside its body box, and bodies from two rows that
    occlude each other, share at least 10% of the smaller box. Touching or
    unrelated boxes share nothing, and the rule is purely geometric: it never
    invents pixels or new boxes.
    """
    smaller = min(_area(first), _area(second))
    return smaller > 0 and _overlap_area(
        first, second) >= _OCCLUSION_OVERLAP * smaller


def _envelope_with_related(
    boxes: Sequence[tuple[float, float, float, float]],
    members: Sequence[int],
) -> tuple[float, float, float, float]:
    """Envelope of the formation plus detections sharing a body region."""
    included = set(members)
    pending = list(members)
    while pending:
        current = boxes[pending.pop()]
        for index, box in enumerate(boxes):
            if index in included:
                continue
            if _related_body(current, box):
                included.add(index)
                pending.append(index)
    return _envelope([boxes[index] for index in included])


def _deduplicated(
    boxes: Sequence[tuple[float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    """Drop repeated detections of the same person (IoU >= 0.8)."""
    kept: list[tuple[float, float, float, float]] = []
    for box in boxes:
        if any(_iou(box, other) >= _DUPLICATE_IOU for other in kept):
            continue
        kept.append(box)
    return kept


def _row_is_structured(
    row: Sequence[tuple[float, float, float, float]],
) -> bool:
    """Similar scale and distinct people in one row.

    Overlaps between rows or partial boxes are tolerated; duplicate
    detections of the same person are merged first, and only the horizontal
    distance between centres must show distinct footprints.
    """
    boxes = _deduplicated(row)
    if len(boxes) < _MIN_FORMATION_MEMBERS:
        return False
    heights = [_width_height(box)[1] for box in boxes]
    widths = [_width_height(box)[0] for box in boxes]
    if max(heights) > min(heights) * _FORMATION_HEIGHT_SPREAD:
        return False
    if max(widths) > min(widths) * _FORMATION_WIDTH_SPREAD:
        return False
    ordered = sorted(boxes, key=lambda box: _center(box)[0])
    for previous, current in zip(ordered, ordered[1:]):
        minimum = _FORMATION_CENTER_GAP * min(
            _width_height(previous)[0], _width_height(current)[0])
        if _center(current)[0] - _center(previous)[0] < minimum:
            return False
    return True


def _has_structured_row(
    boxes: Sequence[tuple[float, float, float, float]],
) -> bool:
    """Return True only for a formation row (>=3 aligned, separated people)."""
    if len(boxes) < _MIN_FORMATION_MEMBERS:
        return False
    return any(len(row) >= _MIN_FORMATION_MEMBERS and _row_is_structured(row)
               for row in _bottom_rows(boxes))


def _sharpness(image: Image.Image, box: tuple[float, ...]) -> float:
    """Laplacian variance inside ``box`` (higher means more focused)."""
    left = max(0, min(int(math.floor(box[0])), image.width - 1))
    top = max(0, min(int(math.floor(box[1])), image.height - 1))
    right = min(image.width, max(int(math.ceil(box[2])), left + 1))
    bottom = min(image.height, max(int(math.ceil(box[3])), top + 1))
    gray = image.crop((left, top, right, bottom)).convert("L")
    laplacian = gray.filter(_LAPLACIAN)
    width, height = laplacian.size
    if width > 2 and height > 2:
        laplacian = laplacian.crop((1, 1, width - 1, height - 1))
    return float(ImageStat.Stat(laplacian).var[0])


def _selection_scores(
    image: Image.Image,
    boxes: Sequence[tuple[float, float, float, float]],
) -> tuple[list[float], list[float]]:
    """Return ``(scores, focus_scores)`` for every detection.

    Scores combine focus (0.60), relative area (0.20) and centrality (0.20).
    Candidates below ``_RELEVANCE_AREA_FLOOR`` of the largest area are not
    scene-relevant (a narrow textured edge, a distant spectator): they are
    discarded before focus is normalised, so they score zero and cannot
    shrink the evidence of the relevant candidates either.
    """
    areas = [_area(box) for box in boxes]
    max_area = max(areas)
    relevant = [index for index, area in enumerate(areas)
                if area >= _RELEVANCE_AREA_FLOOR * max_area]
    focus = {index: _sharpness(image, boxes[index]) for index in relevant}
    max_focus = max(focus.values())
    half_diagonal = math.hypot(image.width / 2, image.height / 2)
    image_center = (image.width / 2, image.height / 2)
    scores = [0.0] * len(boxes)
    focus_scores = [0.0] * len(boxes)
    for index in relevant:
        box = boxes[index]
        focus_score = focus[index] / max_focus if max_focus > 0 else 0.0
        focus_scores[index] = focus_score
        center = _center(box)
        distance = math.hypot(center[0] - image_center[0],
                              center[1] - image_center[1]) / half_diagonal
        centrality = max(0.0, 1.0 - distance)
        scores[index] = (_FOCUS_WEIGHT * focus_score
                         + _SIZE_WEIGHT * areas[index] / max_area
                         + _CENTER_WEIGHT * centrality)
    return scores, focus_scores


def _context_dominates(
    winner: int,
    runner_up: int,
    scores: Sequence[float],
    focus_scores: Sequence[float],
) -> bool:
    """True when the leader wins the stable clues and stays sharp.

    The context part of a score is size + centrality; every candidate scored
    at least as much focus, so ``score - 0.60 * focus`` recovers it. A leader
    that beats the runner-up on context by the tie margin and keeps 80% of the
    sharpest focus is not separated by noise.
    """
    if focus_scores[runner_up] <= 0:
        return False
    context = [score - _FOCUS_WEIGHT * focus
               for score, focus in zip(scores, focus_scores)]
    return (focus_scores[winner] >= _MIN_DOMINANT_FOCUS * focus_scores[runner_up]
            and context[winner] - context[runner_up] >= _CONTEXT_DOMINANCE)


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


def select_target(
    image: Image.Image,
    boxes: Sequence[tuple[float, float, float, float]],
) -> tuple[tuple[float, float, float, float] | None, str]:
    """Select the target box (V2-12) and return ``(box, reason)``.

    ``image`` is an already oriented RGB Pillow image. ``boxes`` are finite
    ``(left, top, right, bottom)`` tuples, ordered, non-empty and inside the
    image; anything else raises ``ValueError``. Reasons: ``individual`` and
    ``group`` return a box; ``no_person`` and ``ambiguous_subject`` return
    ``None``.

    Candidate clusters link nearby, same-scale detections (height ratio up to
    2x, horizontal gap up to half the narrower box). A cluster is a
    ``group`` only when, after merging duplicates (IoU >= 0.8), one of its
    ground-aligned rows has at least three members with height ratio <= 1.35,
    width ratio <= 2, bottoms within 0.25 of the median height (measured from
    the first bottom of the row) and centres separated by at least 0.2 of the
    narrower width. Rows with very different heights, compact plays and pairs
    are not formations.

    The returned group envelope is the whole main cluster (most members, then
    largest area) expanded with any detection sharing at least 10% of its
    smaller box with an included one: short head/torso boxes travel with their
    bodies and the bodies of two rows that occlude each other stay together.
    The rule is purely geometric, so isolated or other-scale detections are
    excluded while a detection that really overlaps the team is kept.

    Otherwise candidates whose area is below 15% of the largest are discarded
    before focus normalisation and score zero. The remaining ones combine
    focus (0.60), relative area (0.20) and centrality (0.20), so a large but
    softer relevant detection cannot outvote clearly sharper evidence. A gap
    below 0.10 between the first two is ``ambiguous_subject``, unless the
    leader also wins the size+position context by at least 0.10 and keeps at
    least 80% of the sharpest candidate's focus: then it is the individual
    target, because that is not a real duel. A single detection is always
    ``individual``. Detection and geometry errors are never turned into
    ambiguity.
    """
    _check_image(image)
    checked = _checked_boxes(image, boxes)
    if not checked:
        return None, "no_person"
    if len(checked) == 1:
        return checked[0], "individual"
    clusters = _formation_clusters(checked)
    formations = [
        cluster for cluster in clusters
        if _has_structured_row([checked[index] for index in cluster])]
    if formations:
        main = max(formations, key=lambda indexes: (
            len(indexes), sum(_area(checked[index]) for index in indexes)))
        return _envelope_with_related(checked, main), "group"
    scores, focus_scores = _selection_scores(image, checked)
    ranked = sorted(range(len(checked)), key=lambda index: (-scores[index], index))
    winning, runner_up = ranked[0], ranked[1]
    if (scores[winning] - scores[runner_up] < _AMBIGUITY_MARGIN
            and not _context_dominates(winning, runner_up, scores, focus_scores)):
        return None, "ambiguous_subject"
    return checked[winning], "individual"
