"""Tests for app.subject.select_subject (stage 02, contract first)."""

import math

import pytest

from app.subject import select_subject


def test_empty_list_returns_none():
    assert select_subject([]) is None


def test_empty_tuple_returns_none():
    assert select_subject(()) is None


def test_single_box_returned_as_is():
    box = (10.0, 20.0, 110.0, 220.0)
    result = select_subject([box])
    assert result == box
    assert result is box


def test_single_int_box_keeps_precision():
    box = (0, 0, 10**400, 1)
    assert select_subject([box]) == box


def test_winner_at_start():
    boxes = [(0, 0, 100, 100), (0, 0, 10, 10), (50, 50, 60, 60)]
    assert select_subject(boxes) == (0, 0, 100, 100)


def test_winner_in_middle():
    boxes = [(0, 0, 10, 10), (0, 0, 100, 100), (50, 50, 60, 60)]
    assert select_subject(boxes) == (0, 0, 100, 100)


def test_winner_at_end():
    boxes = [(0, 0, 10, 10), (50, 50, 60, 60), (0, 0, 100, 100)]
    assert select_subject(boxes) == (0, 0, 100, 100)


def test_wide_vs_tall_chooses_by_area():
    wide = (0, 0, 100, 10)  # area 1000
    tall = (0, 0, 10, 200)  # area 2000
    assert select_subject([wide, tall]) == tall
    assert select_subject([tall, wide]) == tall


def test_tie_returns_first_of_distinct_boxes():
    first = (0, 0, 10, 10)
    second = (20, 20, 30, 30)
    assert select_subject([first, second]) == first


def test_tie_inverted_order_returns_first():
    first = (0, 0, 10, 10)
    second = (20, 20, 30, 30)
    assert select_subject([second, first]) == second


def test_fractional_coordinates():
    boxes = [(0.5, 0.25, 10.5, 5.25), (0.0, 0.0, 2.5, 2.5)]
    assert select_subject(boxes) == (0.5, 0.25, 10.5, 5.25)


def test_minimal_area_box():
    tiny = (1.0, 1.0, 1.5, 1.25)
    assert select_subject([tiny]) == tiny
    assert select_subject([(0, 0, 10, 10), tiny]) == (0, 0, 10, 10)


def test_huge_ints_do_not_overflow_and_keep_extremes_distinct():
    big = (0, 0, 10**400, 1)
    bigger = (0, 0, 10**400 - 1, 2)
    assert select_subject([big, bigger]) == bigger
    assert select_subject([bigger, big]) == bigger


def test_tuple_input_accepted():
    boxes = ((0, 0, 10, 10), (0, 0, 100, 100))
    assert select_subject(boxes) == (0, 0, 100, 100)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "box",
        b"box",
        123,
        4.5,
        (x for x in [(0, 0, 1, 1)]),
        {"boxes": []},
    ],
)
def test_invalid_container_types_raise(bad):
    with pytest.raises(ValueError):
        select_subject(bad)


@pytest.mark.parametrize(
    "bad_box",
    [
        None,
        "box",
        123,
        (0, 0, 1),  # too short
        (0, 0, 1, 1, 2),  # too long
        (),  # empty
        [0, 0, 1, 1],  # list instead of tuple
        (True, 0, 1, 1),  # booleans
        (0, False, 1, 1),
        ((0, 0), (1, 1)),  # nested tuples instead of numbers
        (-1, 0, 10, 10),  # negative
        (0, -0.5, 10, 10),
        (float("nan"), 0, 1, 1),
        (0, float("inf"), 1, 1),
        (0, 0, float("-inf"), 1),
        (0, 0, 0, 10),  # empty width
        (0, 0, 10, 0),  # empty height
        (10, 0, 5, 10),  # inverted
        (0, 10, 5, 5),
        (0, 0, "a", 1),
        (0, 0, 1, None),
    ],
)
def test_invalid_boxes_raise(bad_box):
    with pytest.raises(ValueError):
        select_subject([bad_box])


def test_invalid_box_behind_valid_one_still_raises():
    with pytest.raises(ValueError):
        select_subject([(0, 0, 100, 100), (5, 5, 1, 1)])


def test_does_not_mutate_input():
    boxes = [(0, 0, 10, 10), (0, 0, 100, 50), (5, 5, 9, 9)]
    snapshot = list(boxes)
    first = select_subject(boxes)
    second = select_subject(boxes)
    assert boxes == snapshot
    assert first == second == (0, 0, 100, 50)


def test_deterministic_repeated_calls():
    boxes = [(0, 0, 30, 20), (1, 1, 32, 21), (0, 0, 5, 5)]
    assert select_subject(boxes) == select_subject(list(boxes))
    assert select_subject(boxes) == (1, 1, 32, 21)


def test_nan_area_comparison_does_not_win():
    with pytest.raises(ValueError):
        select_subject([(float("nan"), 0, 1, 1)])


def test_result_usable_without_conversion():
    box = select_subject([(0, 0, 3, 4)])
    assert isinstance(box, tuple) and len(box) == 4
    assert math.isfinite(box[2] - box[0])
