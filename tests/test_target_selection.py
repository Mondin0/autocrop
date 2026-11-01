"""Contract tests for app.subject.select_target (V2-12, synthetic only).

Images are built in memory from flat grey plus deterministic black stripes;
blur is applied to mark a "desenfocado" region. No weights, no network, no
private photographs.
"""

import pytest
from PIL import Image, ImageDraw, ImageFilter

from app.subject import select_subject, select_target

BACKGROUND = (120, 120, 120)


# --- Synthetic image helpers ---------------------------------------------------


def make_image(width=1200, height=800):
    return Image.new("RGB", (width, height), BACKGROUND)


def paint_stripes(image, box, period=4, width=2):
    """Draw deterministic vertical stripes, a cheap high-frequency texture."""
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = (int(value) for value in box)
    for x in range(left, right, period):
        draw.rectangle([x, top, x + width - 1, bottom - 1], fill=(0, 0, 0))


def blur_region(image, box, radius):
    left, top, right, bottom = (int(value) for value in box)
    region = image.crop((left, top, right, bottom))
    image.paste(region.filter(ImageFilter.GaussianBlur(radius)),
                (left, top, right, bottom))


def textured(image, box, blur=0):
    paint_stripes(image, box)
    if blur:
        blur_region(image, box, blur)
    return box


# --- Validation ----------------------------------------------------------------


@pytest.mark.parametrize("boxes", [[], ()])
def test_no_boxes_is_no_person(boxes):
    assert select_target(make_image(), boxes) == (None, "no_person")


@pytest.mark.parametrize("bad", [None, "image", 123, object()])
def test_image_must_be_a_pillow_image(bad):
    with pytest.raises(ValueError):
        select_target(bad, [(0, 0, 10, 10)])


@pytest.mark.parametrize("mode", ["L", "RGBA", "P", "CMYK"])
def test_image_must_be_rgb(mode):
    with pytest.raises(ValueError):
        select_target(Image.new(mode, (50, 50)), [(0, 0, 10, 10)])


@pytest.mark.parametrize("size", [(0, 0), (0, 5), (5, 0)])
def test_rgb_image_with_zero_dimension_raises(size):
    with pytest.raises(ValueError):
        select_target(Image.new("RGB", size), [(0, 0, 1, 1)])


@pytest.mark.parametrize(
    "bad",
    [None, "box", b"box", 123, 4.5, (x for x in [(0, 0, 1, 1)]),
     {"boxes": []}],
)
def test_invalid_boxes_container_raises(bad):
    with pytest.raises(ValueError):
        select_target(make_image(), bad)


@pytest.mark.parametrize(
    "bad_box",
    [
        None,
        "box",
        123,
        (0, 0, 1),
        (0, 0, 1, 1, 2),
        (),
        [0, 0, 1, 1],
        (True, 0, 1, 1),
        (0, False, 1, 1),
        ((0, 0), (1, 1)),
        (-1, 0, 10, 10),
        (float("nan"), 0, 1, 1),
        (0, float("inf"), 1, 1),
        (0, 0, 0, 10),
        (0, 0, 10, 0),
        (10, 0, 5, 10),
        (0, 0, "a", 1),
        (0, 0, 1, None),
    ],
)
def test_invalid_box_values_raise(bad_box):
    with pytest.raises(ValueError):
        select_target(make_image(), [bad_box])


@pytest.mark.parametrize(
    "outside",
    [(0, 0, 1300, 10), (0, -1, 10, 10), (0, 0, 10, 900), (1200, 0, 1200, 10)],
)
def test_box_outside_image_raises(outside):
    with pytest.raises(ValueError):
        select_target(make_image(), [outside])


def test_invalid_box_behind_valid_one_still_raises():
    with pytest.raises(ValueError):
        select_target(make_image(), [(0, 0, 100, 100), (5, 5, 1, 1)])


# --- Individuals ---------------------------------------------------------------


def test_single_box_is_individual_and_returned_unchanged():
    image = make_image()
    box = (100.5, 200.25, 400.5, 700.75)
    textured(image, (100, 200, 400, 700))
    selected, reason = select_target(image, [box])
    assert reason == "individual"
    assert selected == box
    assert selected is box


def test_focused_player_beats_larger_blurred_foreground():
    image = make_image()
    foreground = textured(image, (60, 120, 420, 780), blur=4)
    target = textured(image, (700, 300, 880, 700))
    selected, reason = select_target(image, [foreground, target])
    assert reason == "individual"
    assert selected == target


def test_size_and_position_beat_a_tiny_edge_detection():
    image = make_image()
    central = textured(image, (450, 150, 750, 750), blur=0.5)
    edge = textured(image, (20, 20, 80, 140))
    selected, reason = select_target(image, [edge, central])
    assert reason == "individual"
    assert selected == central


def test_irrelevant_edge_does_not_change_a_clear_individual_choice():
    """R3: irrelevant detections are discarded before normalising focus.

    The same relevant scene must produce the same selection with and without a
    tiny, extremely textured detection at the border. Discarding that
    detection afterwards still lets it shrink the protagonist's focus score.
    """
    image = make_image()
    foreground = textured(image, (60, 120, 420, 780), blur=4)
    protagonist = textured(image, (700, 300, 880, 700), blur=0.7)
    baseline = select_target(image, [foreground, protagonist])
    assert baseline == (protagonist, "individual")
    edge = textured(image, (300, 20, 360, 140))
    assert select_target(image, [foreground, protagonist, edge]) == baseline


def test_softer_textured_foreground_does_not_hide_a_sharper_target():
    """R3 residual: a big foreground with visible texture is not a tie.

    The foreground covers roughly three times the area of the protagonist and
    keeps real texture (mild blur, not flat or fully blurred); the relevant
    protagonist is moderately sharper. The small border detection is
    irrelevant by area and must not change the observable choice either.
    """
    image = make_image()
    foreground = textured(image, (60, 120, 420, 780), blur=0.7)
    target = textured(image, (700, 300, 880, 700), blur=0.5)
    edge = textured(image, (300, 20, 360, 140))
    assert select_target(image, [foreground, target]) == (target, "individual")
    assert select_target(
        image, [foreground, target, edge]) == (target, "individual")


def test_dominant_sharp_subject_beats_a_slightly_sharper_smaller_one():
    """R7: a dominant, sharp subject is not a real duel against a small rival.

    The main detection covers about 2.6x the area, is better placed and keeps
    around 90% of the secondary's focus. Both are sharp. A slightly sharper
    but much smaller detection must not force ``ambiguous_subject``.
    """
    image = make_image()
    dominant = textured(image, (250, 150, 650, 650), blur=0.25)
    sharper = textured(image, (720, 150, 900, 570))
    assert select_target(image, [dominant, sharper]) == (
        dominant, "individual")


def test_two_far_apart_people_are_not_a_group():
    image = make_image()
    left = textured(image, (100, 300, 300, 700))
    right = textured(image, (900, 300, 1100, 700), blur=3)
    selected, reason = select_target(image, [left, right])
    assert reason == "individual"
    assert selected == left


def test_compact_play_is_not_a_formation_and_keeps_focused_player():
    """Regression R1: three nearby players at different depths are a play.

    Their detection bottoms lie on different lines (different distance to the
    camera), so they must not become a group; the focused protagonist wins.
    """
    image = make_image()
    left = textured(image, (300, 250, 440, 720), blur=3)
    protagonist = textured(image, (470, 300, 620, 760))
    right = textured(image, (640, 200, 760, 600), blur=3)
    selected, reason = select_target(image, [left, protagonist, right])
    assert reason == "individual"
    assert selected == protagonist


def test_pair_alone_is_not_a_formation():
    """Two people side by side are not evidence of a structured formation."""
    image = make_image()
    sharp = textured(image, (300, 300, 420, 700))
    blurred = textured(image, (430, 300, 550, 700), blur=3)
    selected, reason = select_target(image, [sharp, blurred])
    assert reason == "individual"
    assert selected == sharp


def test_play_of_three_with_mismatched_heights_is_not_a_group():
    """R1: proximity and a shared ground line are not a coherent formation.

    Three players close together on the same line but seen at very different
    distances (large height differences) are a play, not a lineup.
    """
    image = make_image()
    foreground = textured(image, (300, 200, 440, 700), blur=3)
    protagonist = textured(image, (460, 250, 600, 700))
    distant = textured(image, (620, 400, 700, 700), blur=3)
    selected, reason = select_target(
        image, [foreground, protagonist, distant])
    assert reason == "individual"
    assert selected == protagonist


def test_symmetric_equal_candidates_are_ambiguous():
    image = make_image()
    left = textured(image, (100, 300, 300, 700))
    right = textured(image, (900, 300, 1100, 700))
    assert select_target(image, [left, right]) == (None, "ambiguous_subject")


def test_comparable_focus_with_equal_relevance_stays_ambiguous():
    """Reasonable tie: same size, same position, barely different focus.

    The sharper box differs by less than the ambiguity margin, so the scene
    must remain ambiguous instead of picking a winner on measurement noise.
    """
    image = make_image()
    left = textured(image, (300, 200, 400, 700), blur=0.45)
    right = textured(image, (800, 200, 900, 700), blur=0.5)
    assert select_target(image, [left, right]) == (None, "ambiguous_subject")


def test_deterministic_and_does_not_mutate_input():
    image = make_image()
    boxes = [textured(image, (100, 300, 300, 700)),
             textured(image, (900, 300, 1100, 700), blur=3)]
    snapshot = list(boxes)
    first = select_target(image, boxes)
    assert select_target(image, boxes) == first
    assert boxes == snapshot


# --- Formations ----------------------------------------------------------------


def test_formation_is_kept_whole_and_background_person_excluded():
    image = make_image()
    members = [textured(image, (100, 400, 160, 550)),
               textured(image, (180, 405, 240, 555)),
               textured(image, (260, 402, 320, 552))]
    background = textured(image, (700, 430, 730, 560))
    selected, reason = select_target(image, members + [background])
    assert reason == "group"
    assert selected == (100, 400, 320, 555)


def test_large_foreground_spectator_does_not_widen_formation():
    image = make_image()
    members = [textured(image, (100, 400, 160, 550)),
               textured(image, (180, 405, 240, 555)),
               textured(image, (260, 402, 320, 552))]
    spectator = textured(image, (330, 300, 450, 780), blur=4)
    selected, reason = select_target(image, members + [spectator])
    assert reason == "group"
    assert selected == (100, 400, 320, 555)
    # Real bound check: the envelope stops before the spectator starts.
    assert selected[2] < spectator[0]
    assert selected[3] == max(box[3] for box in members)


def test_group_envelope_contains_every_member():
    image = make_image()
    members = [textured(image, (120, 380, 200, 540)),
               textured(image, (240, 390, 320, 550)),
               textured(image, (360, 385, 440, 545))]
    selected, reason = select_target(image, members)
    assert reason == "group"
    for box in members:
        assert selected[0] <= box[0] and selected[1] <= box[1]
        assert selected[2] >= box[2] and selected[3] >= box[3]


def test_overlapping_pair_is_not_a_formation():
    """R2: the previous test claimed two overlapping boxes formed a group.

    Contract says several nearby detections are not enough for a formation.
    Two overlapping detections stay an individual decision; the focused box
    is kept. The old assertion encoded a defect, not the contract.
    """
    image = make_image()
    sharp = textured(image, (300, 200, 500, 700))
    blurred = textured(image, (420, 210, 620, 710), blur=3)
    selected, reason = select_target(image, [sharp, blurred])
    assert reason == "individual"
    assert selected == sharp


def test_coherent_two_row_formation_of_six_is_a_group():
    """A numerous, coherent formation (two rows of three) is a group.

    It is the positive side of the R1 regression: tightening the formation
    rule must keep this scene grouped while rejecting the misaligned play.
    """
    image = make_image()
    back_row = [textured(image, (100, 200, 180, 500)),
                textured(image, (200, 205, 280, 505)),
                textured(image, (300, 200, 380, 500))]
    front_row = [textured(image, (150, 380, 280, 700)),
                 textured(image, (250, 385, 380, 705)),
                 textured(image, (350, 380, 470, 700))]
    selected, reason = select_target(image, back_row + front_row)
    assert reason == "group"
    assert selected == (100, 200, 470, 705)


def test_two_row_formation_with_occlusions_and_duplicate_is_a_group():
    """R4: a real formation tolerates two rows, partial overlaps and a duplicate.

    Detections of the same person must not break the row, and partially
    overlapping members of adjacent rows are still one formation.
    """
    image = make_image()
    back_row = [textured(image, (100, 200, 180, 500)),
                textured(image, (200, 205, 280, 505)),
                textured(image, (202, 207, 278, 503)),
                textured(image, (300, 200, 380, 500))]
    front_row = [textured(image, (150, 380, 280, 700)),
                 textured(image, (250, 385, 380, 705)),
                 textured(image, (350, 380, 470, 700))]
    selected, reason = select_target(image, back_row + front_row)
    assert reason == "group"
    assert selected == (100, 200, 470, 705)
    for box in back_row + front_row:
        assert selected[0] <= box[0] and selected[1] <= box[1]
        assert selected[2] >= box[2] and selected[3] >= box[3]


def test_staggered_bottoms_beyond_tolerance_are_not_a_group():
    """R5: chained small steps must not fake one ground-aligned row.

    Each consecutive bottom differs by 0.2 of the height (under the 0.25
    tolerance), but the extremes differ by 0.4, so the three detections do not
    share a ground line and are not a formation.
    """
    image = make_image()
    boxes = [textured(image, (100, 200, 200, 500)),
             textured(image, (220, 260, 320, 560)),
             textured(image, (340, 320, 440, 620))]
    selected, reason = select_target(image, boxes)
    assert reason != "group"


def test_group_envelope_includes_related_bodies_not_only_heads():
    """R6: short aligned head boxes are not the whole team.

    Cropping the envelope of the head row alone cuts every body and limb below
    it. Head/torso detections and the full-body detections of the same people
    (~3x taller, two rows) are one team: the envelope must cover all related
    bodies and still exclude an isolated spectator of another scale.
    """
    image = make_image()
    back_heads = [textured(image, (120, 180, 200, 250)),
                  textured(image, (240, 180, 320, 250)),
                  textured(image, (360, 180, 440, 250))]
    back_bodies = [textured(image, (80, 180, 240, 400)),
                   textured(image, (200, 130, 360, 400)),
                   textured(image, (320, 80, 480, 400))]
    front_heads = [textured(image, (160, 380, 240, 450)),
                   textured(image, (280, 380, 360, 450)),
                   textured(image, (400, 380, 480, 450))]
    front_bodies = [textured(image, (120, 360, 280, 580)),
                    textured(image, (240, 310, 400, 580)),
                    textured(image, (360, 260, 520, 580))]
    spectator = textured(image, (800, 300, 900, 700), blur=3)
    related = back_heads + back_bodies + front_heads + front_bodies
    selected, reason = select_target(image, related + [spectator])
    assert reason == "group"
    for box in related:
        assert selected[0] <= box[0] and selected[1] <= box[1]
        assert selected[2] >= box[2] and selected[3] >= box[3]
    assert selected[2] < spectator[0]


def test_historical_select_subject_is_untouched():
    boxes = [(0, 0, 10, 10), (0, 0, 100, 100)]
    assert select_subject(boxes) == (0, 0, 100, 100)
