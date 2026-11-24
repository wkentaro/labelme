from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction
from typing import Final

import numpy as np
import pytest

from labelme._automation import Detection
from labelme._automation import shapes_from_detections
from labelme._automation._scaling import Scale
from labelme._automation._scaling import scale_shape
from labelme._automation._suppression import _local_mask_from_detection
from labelme._automation._suppression import match_detections_to_existing_shapes
from labelme._automation._suppression import suppress_detections_greedy
from labelme._shape import Shape
from labelme._shape import ShapeType


@pytest.fixture
def make_full_detection() -> Callable[..., Detection]:
    def _make(*, label: str | None = None) -> Detection:
        return Detection(
            bbox=(0.0, 0.0, 10.0, 10.0),
            mask=np.ones((11, 11), dtype=bool),
            label=label,
        )

    return _make


def test_redundant_drops_duplicate_mask_keeps_first(
    *,
    make_full_detection: Callable[..., Detection],
) -> None:
    first = make_full_detection()
    second = make_full_detection()

    kept = suppress_detections_greedy(detections=[first, second], iou_threshold=0.5)

    assert kept == [first]


def test_redundant_keeps_first_when_descriptions_differ() -> None:
    mask = np.ones((11, 11), dtype=bool)
    first = Detection(bbox=(0.0, 0.0, 10.0, 10.0), mask=mask, description="first")
    second = Detection(
        bbox=(0.0, 0.0, 10.0, 10.0), mask=mask.copy(), description="second"
    )

    kept = suppress_detections_greedy(detections=[first, second], iou_threshold=0.5)

    assert len(kept) == 1
    assert kept[0].description == "first"


def test_redundant_keeps_only_first_among_three_duplicates(
    *,
    make_full_detection: Callable[..., Detection],
) -> None:
    first = make_full_detection()
    second = make_full_detection()
    third = make_full_detection()

    kept = suppress_detections_greedy(
        detections=[first, second, third], iou_threshold=0.5
    )

    assert kept == [first]


def test_redundant_keeps_disjoint_masks() -> None:
    first = Detection(
        bbox=(0.0, 0.0, 5.0, 5.0),
        mask=np.ones((6, 6), dtype=bool),
    )
    second = Detection(
        bbox=(20.0, 20.0, 25.0, 25.0),
        mask=np.ones((6, 6), dtype=bool),
    )

    kept = suppress_detections_greedy(detections=[first, second], iou_threshold=0.5)

    assert kept == [first, second]


def test_redundant_drops_mask_contained_in_larger_mask() -> None:
    # Small mask is fully inside the large one — low IoU, high containment.
    # Tree-cluster vs single-tree scenario.
    large = Detection(
        bbox=(0.0, 0.0, 20.0, 20.0),
        mask=np.ones((21, 21), dtype=bool),
    )
    small = Detection(
        bbox=(5.0, 5.0, 9.0, 9.0),
        mask=np.ones((5, 5), dtype=bool),
    )

    kept = suppress_detections_greedy(detections=[large, small], iou_threshold=0.5)

    assert kept == [large]


def test_redundant_keeps_partial_overlap_below_containment_threshold() -> None:
    # big: 10x10 full mask, area 100. small: 5x5 full mask, area 25, shifted
    # one row past big's lower edge so only a 4x5 strip (20 pixels) overlaps.
    # IoU = 20/(100+25-20) = 0.19 (below 0.5, IoU check misses).
    # containment = 20/min(100,25) = 0.8 (below 0.85, containment check misses).
    big = Detection(
        bbox=(0.0, 0.0, 9.0, 9.0),
        mask=np.ones((10, 10), dtype=bool),
    )
    small = Detection(
        bbox=(5.0, 6.0, 9.0, 10.0),
        mask=np.ones((5, 5), dtype=bool),
    )

    kept = suppress_detections_greedy(detections=[big, small], iou_threshold=0.5)

    assert kept == [big, small]


def test_redundant_keeps_triangles_sharing_bbox() -> None:
    rows, cols = np.indices((11, 11))
    lower_left = Detection(
        bbox=(0.0, 0.0, 10.0, 10.0),
        mask=rows + cols <= 10,
    )
    upper_right = Detection(
        bbox=(0.0, 0.0, 10.0, 10.0),
        mask=rows + cols > 10,
    )

    kept = suppress_detections_greedy(
        detections=[lower_left, upper_right], iou_threshold=0.5
    )

    assert kept == [lower_left, upper_right]


def test_redundant_does_not_suppress_across_labels(
    *,
    make_full_detection: Callable[..., Detection],
) -> None:
    tree = make_full_detection(label="tree")
    grass = make_full_detection(label="grass")

    kept = suppress_detections_greedy(detections=[tree, grass], iou_threshold=0.5)

    assert kept == [tree, grass]


def test_redundant_empty_detections() -> None:
    assert suppress_detections_greedy(detections=[], iou_threshold=0.5) == []


def test_redundant_drops_duplicate_bbox_only_detections() -> None:
    first = Detection(bbox=(0.0, 0.0, 10.0, 10.0))
    second = Detection(bbox=(0.0, 0.0, 10.0, 10.0))

    kept = suppress_detections_greedy(detections=[first, second], iou_threshold=0.5)

    assert kept == [first]


def test_redundant_passes_through_detections_without_bbox() -> None:
    no_bbox = Detection(mask=np.ones((11, 11), dtype=bool))

    kept = suppress_detections_greedy(detections=[no_bbox, no_bbox], iou_threshold=0.5)

    assert kept == [no_bbox, no_bbox]


def test_redundant_raises_on_mask_shape_mismatch() -> None:
    bad = Detection(
        bbox=(0.0, 0.0, 9.0, 9.0),
        mask=np.ones((11, 11), dtype=bool),
    )

    with pytest.raises(ValueError, match="mask shape"):
        suppress_detections_greedy(detections=[bad], iou_threshold=0.5)


def test_redundant_rejects_mixed_mask_and_bbox_only() -> None:
    with_mask = Detection(
        bbox=(0.0, 0.0, 10.0, 10.0),
        mask=np.ones((11, 11), dtype=bool),
    )
    bbox_only = Detection(bbox=(0.0, 0.0, 10.0, 10.0))

    with pytest.raises(ValueError, match="homogeneous"):
        suppress_detections_greedy(detections=[with_mask, bbox_only], iou_threshold=0.5)


def test_overlapping_drops_polygon_detection_overlapping_existing_polygon() -> None:
    existing = Shape(
        shape_type="polygon",
        points=np.array([(0, 0), (10, 0), (10, 10), (0, 10)], dtype=np.float64),
    )

    detection_mask = np.ones((11, 11), dtype=bool)
    detection = Detection(bbox=(0.0, 0.0, 10.0, 10.0), mask=detection_mask)

    result = match_detections_to_existing_shapes(
        detections=[detection],
        existing_shapes=[existing],
    )

    assert result.new_detections == []
    assert result.matching_shapes == [existing]


def test_overlapping_keeps_when_iou_below_threshold() -> None:
    existing = Shape(
        shape_type="rectangle", points=np.array([(0, 0), (10, 10)], dtype=np.float64)
    )

    detection = Detection(bbox=(8.0, 8.0, 18.0, 18.0))

    result = match_detections_to_existing_shapes(
        detections=[detection],
        existing_shapes=[existing],
    )

    assert result.new_detections == [detection]
    assert result.matching_shapes == []


def test_overlapping_uses_mask_iou_not_bbox_iou() -> None:
    # Two right triangles share the same bbox but cover opposite halves,
    # so bbox IoU would be 1.0 while mask IoU is 0.
    existing = Shape(
        shape_type="polygon",
        points=np.array([(0, 0), (10, 0), (0, 10)], dtype=np.float64),
    )

    rows, cols = np.indices((11, 11))
    detection_mask = rows + cols > 10
    detection = Detection(bbox=(0.0, 0.0, 10.0, 10.0), mask=detection_mask)

    result = match_detections_to_existing_shapes(
        detections=[detection],
        existing_shapes=[existing],
    )

    assert result.new_detections == [detection]
    assert result.matching_shapes == []


def test_overlapping_empty_detections() -> None:
    existing = Shape(
        shape_type="rectangle", points=np.array([(0, 0), (10, 10)], dtype=np.float64)
    )

    result = match_detections_to_existing_shapes(
        detections=[],
        existing_shapes=[existing],
    )

    assert result.new_detections == []
    assert result.matching_shapes == []


def test_overlapping_no_existing_shapes_passes_through() -> None:
    detection = Detection(bbox=(0.0, 0.0, 10.0, 10.0))

    result = match_detections_to_existing_shapes(
        detections=[detection],
        existing_shapes=[],
    )

    assert result.new_detections == [detection]
    assert result.matching_shapes == []


def test_overlapping_passes_through_detection_without_bbox() -> None:
    existing = Shape(
        shape_type="rectangle", points=np.array([(0, 0), (10, 10)], dtype=np.float64)
    )
    no_bbox = Detection(mask=np.ones((11, 11), dtype=bool))

    result = match_detections_to_existing_shapes(
        detections=[no_bbox],
        existing_shapes=[existing],
    )

    assert result.new_detections == [no_bbox]
    assert result.matching_shapes == []


def test_overlapping_drops_detection_engulfing_smaller_existing_shape() -> None:
    # Small existing mask fully inside the new detection's mask: IoU is low
    # (small/big ratio) but containment of existing in new is ~1.0. The
    # nested-mask scenario the user hit on a crowded-tree image.
    existing = Shape(
        shape_type="rectangle", points=np.array([(5, 5), (9, 9)], dtype=np.float64)
    )

    detection = Detection(
        bbox=(0.0, 0.0, 20.0, 20.0),
        mask=np.ones((21, 21), dtype=bool),
    )

    result = match_detections_to_existing_shapes(
        detections=[detection],
        existing_shapes=[existing],
    )

    assert result.new_detections == []
    assert result.matching_shapes == [existing]


def test_overlapping_uses_existing_mask_shape_geometry() -> None:
    # A mask shape whose stored mask covers only the lower-left triangle of
    # its bbox should suppress a detection occupying the same triangle but
    # not one occupying the complementary upper-right triangle.
    rows, cols = np.indices((11, 11))
    existing = Shape(
        shape_type="mask",
        points=np.array([(0, 0), (10, 10)], dtype=np.float64),
        mask=rows + cols <= 10,
    )

    lower_left = Detection(bbox=(0.0, 0.0, 10.0, 10.0), mask=(rows + cols <= 10).copy())
    upper_right = Detection(bbox=(0.0, 0.0, 10.0, 10.0), mask=rows + cols > 10)

    result = match_detections_to_existing_shapes(
        detections=[lower_left, upper_right],
        existing_shapes=[existing],
    )

    assert result.new_detections == [upper_right]
    assert result.matching_shapes == [existing]


def test_overlapping_accepts_mask_shape_moved_by_half_a_pixel() -> None:
    # Rounding each corner alone turns x 10.5..13.5 into 10..14, one pixel
    # wider than the stored 4-pixel mask.
    existing = Shape(
        shape_type="mask",
        points=np.array([(10.5, 20.5), (13.5, 23.5)], dtype=np.float64),
        mask=np.ones((4, 4), dtype=bool),
    )
    covered = Detection(bbox=(11.0, 21.0, 14.0, 24.0), mask=np.ones((4, 4), dtype=bool))
    elsewhere = Detection(
        bbox=(40.0, 40.0, 43.0, 43.0), mask=np.ones((4, 4), dtype=bool)
    )

    result = match_detections_to_existing_shapes(
        detections=[covered, elsewhere],
        existing_shapes=[existing],
    )

    assert result.new_detections == [elsewhere]
    assert result.matching_shapes == [existing]


def test_mask_shape_from_fractional_detection_can_be_an_existing_shape() -> None:
    detection = Detection(
        bbox=(10.4, 20.6, 30.9, 50.1),
        mask=np.ones((30, 22), dtype=bool),
    )
    [existing] = shapes_from_detections(
        detections=[detection],
        shape_type="mask",
    )

    result = match_detections_to_existing_shapes(
        detections=[detection],
        existing_shapes=[existing],
    )

    assert result.new_detections == []
    assert result.matching_shapes == [existing]


def test_overlapping_rasterizes_existing_circle_as_a_disk() -> None:
    # A circle shape is rasterized as its inscribed disk, not its bounding
    # square: a detection at the disk center is suppressed, but one in a bbox
    # corner (outside the disk) survives, where a rectangle bbox would drop it.
    existing = Shape(
        shape_type="circle",
        points=np.array([(10, 10), (20, 10)], dtype=np.float64),  # radius 10
    )

    center = Detection(bbox=(8.0, 8.0, 12.0, 12.0), mask=np.ones((5, 5), dtype=bool))
    corner = Detection(bbox=(0.0, 0.0, 2.0, 2.0), mask=np.ones((3, 3), dtype=bool))

    result = match_detections_to_existing_shapes(
        detections=[center, corner],
        existing_shapes=[existing],
    )

    assert result.new_detections == [corner]
    assert result.matching_shapes == [existing]


@pytest.mark.parametrize(
    ("shape_type", "extra_points"),
    [
        ("point", []),
        ("points", [[20, 20]]),
        ("line", [[20, 20]]),
        ("linestrip", [[20, 20]]),
    ],
)
def test_overlapping_skips_existing_shape_without_bbox_interpretation(
    *, shape_type: ShapeType, extra_points: list[list[float]]
) -> None:
    # Canvas shapes without a bbox/mask interpretation (e.g. a stray point
    # landmark) must not break the AI suppression call.
    existing = Shape(
        shape_type=shape_type,
        points=np.array([[5, 5], *extra_points], dtype=np.float64),
    )
    detection = Detection(
        bbox=(0.0, 0.0, 10.0, 10.0), mask=np.ones((11, 11), dtype=bool)
    )

    result = match_detections_to_existing_shapes(
        detections=[detection],
        existing_shapes=[existing],
    )

    assert result.new_detections == [detection]
    assert result.matching_shapes == []


@pytest.mark.parametrize(
    ("xmin", "mask", "scale", "column"),
    [
        (14, [True] * 3, 10, 1),
        (0, [False] * 14 + [True] * 3 + [False], 10, 1),
        (3.5, [True], 4, 1),
        (2.5, [False, True], 4, 1),
        (3.5, [True], 1, 4),
        (2.5, [False, True], 1, 4),
    ],
)
def test_shrunk_speck_covers_a_match_however_it_is_padded(
    xmin: float, mask: list[bool], scale: int, column: int
) -> None:
    speck = Shape(
        shape_type="mask",
        points=np.array([[xmin, 0], [xmin + len(mask) - 1, 0]], dtype=np.float64),
        mask=np.array([mask], dtype=bool),
    )

    result = match_detections_to_existing_shapes(
        detections=[
            Detection(bbox=(column, 0, column, 0), mask=np.ones((1, 1), dtype=bool))
        ],
        existing_shapes=[speck],
        scale_to_image=(Fraction(scale), Fraction(scale)),
    )

    assert result.new_detections == []
    assert result.matching_shapes == [speck]


def test_saved_match_covers_only_its_own_sent_column() -> None:
    scale = (Fraction(1025, 1024), Fraction(1))
    [saved] = shapes_from_detections(
        detections=[Detection(bbox=(512, 0, 512, 0), mask=np.ones((1, 1), bool))],
        shape_type="mask",
        scale_to_image=scale,
    )
    neighbor = Detection(bbox=(511, 0, 511, 0), mask=np.ones((1, 1), bool))
    same = Detection(bbox=(512, 0, 512, 0), mask=np.ones((1, 1), bool))

    result = match_detections_to_existing_shapes(
        detections=[neighbor, same], existing_shapes=[saved], scale_to_image=scale
    )

    assert result.new_detections == [neighbor]
    assert result.matching_shapes == [saved]


def test_mask_shape_with_swapped_corners_covers_its_first_point() -> None:
    mask = Shape(
        shape_type="mask",
        points=np.array([[12.5, 20], [9.5, 20]], dtype=np.float64),
        mask=np.ones((1, 1), dtype=bool),
    )
    drawn = Detection(bbox=(13, 20, 13, 20), mask=np.ones((1, 1), bool))

    result = match_detections_to_existing_shapes(
        detections=[drawn], existing_shapes=[mask]
    )

    assert result.matching_shapes == [mask]


@pytest.mark.parametrize(
    "scale",
    [
        pytest.param((Fraction(1), Fraction(1)), id="unscaled"),
        pytest.param((Fraction(5, 2), Fraction(5, 2)), id="larger"),
        pytest.param((Fraction(65, 63), Fraction(65, 63)), id="a-little-larger"),
        pytest.param((Fraction(2, 5), Fraction(2, 5)), id="smaller"),
        pytest.param((Fraction(2), Fraction(1, 3)), id="wider-and-shorter"),
        pytest.param((Fraction(63, 65), Fraction(3)), id="narrower-and-taller"),
    ],
)
@pytest.mark.parametrize("seed", range(10))
def test_a_candidate_saved_as_a_mask_is_compared_by_its_saved_pixels(
    *, scale: Scale, seed: int
) -> None:
    rng = np.random.default_rng(seed)
    height, width = (int(side) for side in rng.integers(1, 12, size=2))
    x, y = (int(offset) for offset in rng.integers(0, 40, size=2))
    mask = rng.random((height, width)) < 0.5  # noqa: PLR2004
    mask[rng.integers(height), rng.integers(width)] = True
    detection = Detection(
        bbox=(float(x), float(y), float(x + width - 1), float(y + height - 1)),
        mask=mask,
    )
    [saved] = shapes_from_detections(
        detections=[detection], shape_type="mask", scale_to_image=scale
    )
    back_on_sent_image = scale_shape(shape=saved, factor=(1 / scale[0], 1 / scale[1]))

    compared = _local_mask_from_detection(
        detection=detection, scale_to_image=scale, saved_as_mask=True
    )

    assert back_on_sent_image.mask is not None
    np.testing.assert_array_equal(compared.mask, back_on_sent_image.mask)
    assert list(compared.origin_xy) == back_on_sent_image.points[0].tolist()


_WIDER_AND_SHORTER: Final[Scale] = (Fraction(2), Fraction(1, 3))


def _one_sent_row(*, row: int) -> Detection:
    return Detection(
        bbox=(0.0, float(row), 49.0, float(row)), mask=np.ones((1, 50), dtype=bool)
    )


@pytest.mark.parametrize(
    ("saved_as_mask", "is_new"),
    [
        pytest.param(True, False, id="a-mask-merges-its-three-sent-rows"),
        pytest.param(False, True, id="another-format-keeps-its-row"),
    ],
)
def test_overlapping_compares_a_thin_candidate_as_its_shape_is_saved(
    *, saved_as_mask: bool, is_new: bool
) -> None:
    detection = _one_sent_row(row=3)
    [saved] = shapes_from_detections(
        detections=[detection], shape_type="mask", scale_to_image=_WIDER_AND_SHORTER
    )
    assert saved.points.tolist() == [[0, 1], [99, 1]]
    two_thirds_of_it = Shape(
        shape_type="mask",
        points=np.array([[20.0, 1.0], [119.0, 1.0]]),
        mask=np.ones((1, 100), dtype=bool),
    )

    result = match_detections_to_existing_shapes(
        detections=[detection],
        existing_shapes=[two_thirds_of_it],
        scale_to_image=_WIDER_AND_SHORTER,
        saved_as_mask=saved_as_mask,
    )

    assert result.new_detections == ([detection] if is_new else [])
    assert result.matching_shapes == ([] if is_new else [two_thirds_of_it])


def test_overlapping_keeps_a_candidate_whose_sent_mask_has_no_rows() -> None:
    no_rows = Detection(bbox=(0.0, 1.0, 49.0, 0.0), mask=np.ones((0, 50), dtype=bool))

    result = match_detections_to_existing_shapes(
        detections=[no_rows],
        existing_shapes=[
            Shape(
                shape_type="mask",
                points=np.array([[0.0, 0.0], [99.0, 0.0]]),
                mask=np.ones((1, 100), dtype=bool),
            )
        ],
        scale_to_image=_WIDER_AND_SHORTER,
        saved_as_mask=True,
    )

    assert result.new_detections == [no_rows]


def test_overlapping_keeps_a_candidate_beside_a_mask_far_off_the_image() -> None:
    candidate = _one_sent_row(row=3)

    result = match_detections_to_existing_shapes(
        detections=[candidate],
        existing_shapes=[
            Shape(
                shape_type="mask",
                points=np.array([[-(2.0**63), 0.0], [-(2.0**63) + 2, 0.0]]),
                mask=np.ones((1, 3), dtype=bool),
            )
        ],
        scale_to_image=_WIDER_AND_SHORTER,
        saved_as_mask=True,
    )

    assert result.new_detections == [candidate]


@pytest.mark.parametrize(
    ("second_row", "saved_as_mask", "kept_count"),
    [
        pytest.param(4, True, 1, id="masks-saved-onto-the-same-image-row"),
        pytest.param(6, True, 2, id="masks-saved-onto-neighboring-image-rows"),
        pytest.param(4, False, 2, id="another-format-keeps-both-rows"),
    ],
)
def test_redundant_compares_thin_candidates_as_their_shapes_are_saved(
    *, second_row: int, saved_as_mask: bool, kept_count: int
) -> None:
    candidates = [_one_sent_row(row=3), _one_sent_row(row=second_row)]

    kept = suppress_detections_greedy(
        detections=candidates,
        iou_threshold=0.5,
        scale_to_image=_WIDER_AND_SHORTER,
        saved_as_mask=saved_as_mask,
    )

    assert kept == candidates[:kept_count]
