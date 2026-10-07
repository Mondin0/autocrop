from __future__ import annotations

import math

import pytest

from app.crop import calculate_crop


class TestRegressions:
    @pytest.mark.parametrize(
        "img, bbox, ar, margin, expected",
        [
            ((10, 10), (4.1, 4.1, 6.8, 6.8), (1, 1), 0.0, (4, 4, 7, 7)),
            ((10, 10), (4.1, 4.1, 5.1, 5.1), (1, 1), 0.15, (4, 4, 6, 6)),
            ((10, 10), (4, 4, 6, 6), (1, 1), 1e308, (0, 0, 10, 10)),
            ((20_000_000, 20_000_000), (0, 0, 10_000_002, 10_000_002), (1, 1), 0.0, (0, 0, 10_000_002, 10_000_002)),
            ((10, 10), (4.9, 4.9, 5.1, 5.1), (1, 1), 0.0, (4, 4, 6, 6)),
            ((10, 10), (4.9, 4.9, 5.1, 5.1), (3, 2), 0.0, (3, 4, 6, 6)),
        ],
    )
    def test_r1_r2_exact(self, img, bbox, ar, margin, expected):
        res = calculate_crop(img[0], img[1], bbox, ar, margin)
        assert res == expected


class TestExamples:
    def test_example_1x1_margin015(self):
        assert calculate_crop(1000, 800, (400, 300, 600, 500), (1, 1), 0.15) == (370, 270, 630, 530)

    def test_example_left_edge(self):
        assert calculate_crop(1000, 800, (0, 300, 200, 500), (1, 1), 0.15) == (0, 270, 260, 530)

    def test_example_right_edge(self):
        assert calculate_crop(1000, 800, (800, 300, 1000, 500), (1, 1), 0.15) == (740, 270, 1000, 530)

    def test_example_top_edge(self):
        assert calculate_crop(1000, 800, (400, 0, 600, 200), (1, 1), 0.15) == (370, 0, 630, 260)

    def test_example_bottom_edge(self):
        assert calculate_crop(1000, 800, (400, 600, 600, 800), (1, 1), 0.15) == (370, 540, 630, 800)

    def test_example_reduce_margin(self):
        res = calculate_crop(1000, 800, (100, 100, 900, 700), (3, 2), 0.5)
        assert res is not None
        assert res == (0, 67, 999, 733)

    def test_example_impossible_32(self):
        assert calculate_crop(600, 1000, (100, 50, 500, 950), (3, 2), 0.0) is None

    def test_example_frac_bbox(self):
        assert calculate_crop(10, 10, (4.2, 4.2, 5.8, 5.8), (1, 1), 0.0) == (4, 4, 6, 6)


class TestF1:
    @pytest.mark.parametrize(
        "img,bbox,ar,margin",
        [
            ((100, 100), (10, 10, 90, 90), (1, 1), 0.0),
            ((200, 150), (20, 30, 180, 120), (4, 3), 0.1),
            ((150, 200), (30, 20, 120, 180), (3, 4), 0.05),
        ],
    )
    def test_f1_properties(self, img, bbox, ar, margin):
        res = calculate_crop(img[0], img[1], bbox, ar, margin)
        assert res is not None
        left, top, right, bottom = res
        assert isinstance(res, tuple)
        assert len(res) == 4
        for v in res:
            assert type(v) is int
        assert right > left and bottom > top
        assert left >= 0 and top >= 0 and right <= img[0] and bottom <= img[1]
        assert left <= math.floor(bbox[0])
        assert top <= math.floor(bbox[1])
        assert right >= math.ceil(bbox[2])
        assert bottom >= math.ceil(bbox[3])
        a, b = ar
        assert (right - left) * b == (bottom - top) * a


class TestF2F3CornersEdges:
    @pytest.mark.parametrize(
        "img,bbox,ar,margin",
        [
            ((1000, 800), (0, 0, 100, 200), (1, 1), 0.1),
            ((1000, 800), (900, 0, 1000, 100), (1, 1), 0.05),
            ((1000, 800), (0, 700, 150, 800), (1, 1), 0.1),
            ((1000, 800), (850, 700, 1000, 800), (1, 1), 0.1),
            ((800, 1000), (400, 500, 600, 600), (2, 3), 0.0),
        ],
    )
    def test_corners_edges(self, img, bbox, ar, margin):
        res = calculate_crop(img[0], img[1], bbox, ar, margin)
        assert res is not None
        a, b = ar
        l, t, r, bt = res
        assert (r - l) * b == (bt - t) * a
        assert l <= math.floor(bbox[0]) and t <= math.floor(bbox[1])
        assert r >= math.ceil(bbox[2]) and bt >= math.ceil(bbox[3])
        assert l >= 0 and t >= 0 and r <= img[0] and bt <= img[1]


class TestRatiosOrientations:
    ratios = [(1, 1), (4, 5), (5, 4), (3, 2), (2, 3), (16, 9), (9, 16)]
    orients = [(800, 600), (600, 800), (500, 500)]
    bbox = (200, 200, 250, 250)

    @pytest.mark.parametrize("ar", ratios)
    @pytest.mark.parametrize("img", orients)
    def test_ratio_orient_matrix(self, img, ar):
        res = calculate_crop(img[0], img[1], self.bbox, ar, 0.1)
        assert res is not None
        left, top, right, bottom = res
        for v in res:
            assert type(v) is int
        assert left >= 0 and top >= 0 and right <= img[0] and bottom <= img[1]
        assert left <= math.floor(self.bbox[0])
        assert top <= math.floor(self.bbox[1])
        assert right >= math.ceil(self.bbox[2])
        assert bottom >= math.ceil(self.bbox[3])
        a, b = ar
        assert (right - left) * b == (bottom - top) * a

    def test_equivalent_ratios(self):
        r1 = calculate_crop(100, 100, (40, 40, 60, 60), (3, 2), 0.0)
        r2 = calculate_crop(100, 100, (40, 40, 60, 60), (6, 4), 0.0)
        assert r1 == (35, 40, 65, 60)
        assert r2 == (35, 40, 65, 60)


class TestImpossibleCases:
    @pytest.mark.parametrize(
        "img,bbox,ar,margin",
        [
            ((100, 100), (10, 10, 90, 90), (16, 9), 0.0),
            ((50, 100), (10, 20, 40, 80), (3, 2), 0.0),
            ((600, 1000), (100, 50, 500, 950), (3, 2), 0.0),
            ((2, 2), (0, 0, 1, 1), (3, 2), 0.0),
            ((10, 10), (0, 0, 10, 10), (3, 2), 0.0),
        ],
    )
    def test_impossible(self, img, bbox, ar, margin):
        assert calculate_crop(img[0], img[1], bbox, ar, margin) is None


class TestValidationF6:
    @pytest.mark.parametrize(
        "args",
        [
            (-1, 100, (0, 0, 10, 10), (1, 1), 0.1),
            (100, 0, (0, 0, 10, 10), (1, 1), 0.1),
            (100.0, 100, (0, 0, 10, 10), (1, 1), 0.1),
            (100, True, (0, 0, 10, 10), (1, 1), 0.1),
            (100, 100, (0, 0, 10), (1, 1), 0.1),
            (100, 100, (0, 0, 10, 10, 20), (1, 1), 0.1),
            (100, 100, [0, 0, 10, 10], (1, 1), 0.1),
            (100, 100, (True, 0, 10, 10), (1, 1), 0.1),
            (100, 100, (0, float("nan"), 10, 10), (1, 1), 0.1),
            (100, 100, (0, 0, float("inf"), 10), (1, 1), 0.1),
            (100, 100, (0, 0, -1, 10), (1, 1), 0.1),
            (100, 100, (0, 0, 10, -1), (1, 1), 0.1),
            (100, 100, (5, 0, 3, 10), (1, 1), 0.1),
            (100, 100, (0, 5, 10, 3), (1, 1), 0.1),
            (100, 100, (-1, 0, 10, 10), (1, 1), 0.1),
            (100, 100, (0, -1, 10, 10), (1, 1), 0.1),
            (100, 100, (0, 0, 101, 10), (1, 1), 0.1),
            (100, 100, (0, 0, 10, 101), (1, 1), 0.1),
            (100, 100, (0, 0, 10, 10), (0, 1), 0.1),
            (100, 100, (0, 0, 10, 10), (1, 0), 0.1),
            (100, 100, (0, 0, 10, 10), (1.0, 1), 0.1),
            (100, 100, (0, 0, 10, 10), (1, True), 0.1),
            (100, 100, (0, 0, 10, 10), (1, 1, 2), 0.1),
            (100, 100, (0, 0, 10, 10), [1, 1], 0.1),
            (100, 100, (0, 0, 10, 10), (1, 1), -0.1),
            (100, 100, (0, 0, 10, 10), (1, 1), float("nan")),
            (100, 100, (0, 0, 10, 10), (1, 1), float("inf")),
            (100, 100, (0, 0, 10, 10), (1, 1), True),
            (True, 100, (0, 0, 10, 10), (1, 1), 0.1),
            (100, 100, None, (1, 1), 0.1),
            (100, 100, (0, 0, 10, 10), None, 0.1),
            (100, 100, (0, 0, 10, 10), (1, 1), None),
            ("100", 100, (0, 0, 10, 10), (1, 1), 0.1),
            (100, 100, "bad", (1, 1), 0.1),
            (100, 100, (0, 0, 10, 10), "1:1", 0.1),
            (100, 100, (0, 0, 10, 10), (-1, 1), 0.1),
            (None, 100, (0, 0, 10, 10), (1, 1), 0.1),
            (100, None, (0, 0, 10, 10), (1, 1), 0.1),
            (100, 100, (0, 0, 0, 10), (1, 1), 0.1),
            (100, 100, (0, 0, 10, 0), (1, 1), 0.1),
            (100, 100, (5, 5, 5, 10), (1, 1), 0.1),
            (100, 100, (0, 5, 10, 5), (1, 1), 0.1),
            (100, 100, (0, 0, 10, 10), (1,), 0.1),
            (100, 100, (0, 0, 10, 10), (-1, -1), 0.1),
            (100, 100, (float("-inf"), 0, 10, 10), (1, 1), 0.1),
        ],
    )
    def test_invalid_inputs_raise_valueerror(self, args):
        with pytest.raises(ValueError):
            calculate_crop(*args)


class TestSpecialCases:
    def test_entire_image_viable(self):
        res = calculate_crop(800, 600, (0, 0, 800, 600), (4, 3), 0.0)
        assert res == (0, 0, 800, 600)

    def test_tiny_subject(self):
        res = calculate_crop(100, 100, (49.2, 49.2, 50.8, 50.8), (1, 1), 0.1)
        assert res == (49, 49, 51, 51)

    def test_determinism(self):
        r1 = calculate_crop(1000, 800, (400, 300, 600, 500), (1, 1), 0.15)
        r2 = calculate_crop(1000, 800, (400, 300, 600, 500), (1, 1), 0.15)
        assert r1 == r2

    def test_middle_pixel_tie(self):
        res = calculate_crop(10, 10, (4, 4, 6, 6), (1, 1), 0.25)
        assert res == (3, 3, 6, 6)

    def test_frac_bbox_all_sides(self):
        res = calculate_crop(200, 200, (10.3, 20.7, 50.9, 80.1), (1, 1), 0.05)
        assert res is not None
        for v in res:
            assert type(v) is int
        l, t, r, b = res
        assert l <= math.floor(10.3) and t <= math.floor(20.7)
        assert r >= math.ceil(50.9) and b >= math.ceil(80.1)
        assert l >= 0 and t >= 0 and r <= 200 and b <= 200
        assert (r - l) == (b - t)


class TestEnvelopeCross:
    @pytest.mark.parametrize(
        "img,bbox,ar,margin,expected",
        [
            ((10, 10), (4.9, 4.9, 5.1, 5.1), (1, 1), 0.0, (4, 4, 6, 6)),
            ((10, 10), (4.9, 4.9, 5.1, 5.1), (3, 2), 0.0, (3, 4, 6, 6)),
            ((10, 10), (4.8, 4.9, 5.2, 5.1), (1, 1), 0.0, (4, 4, 6, 6)),
        ],
    )
    def test_envelope_cross(self, img, bbox, ar, margin, expected):
        assert calculate_crop(img[0], img[1], bbox, ar, margin) == expected
