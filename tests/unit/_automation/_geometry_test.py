from __future__ import annotations

import math

import numpy as np
import pytest
import skimage
from numpy.typing import NDArray

from labelme._automation._geometry import _compute_polygon_deviation
from labelme._automation._geometry import _round_bbox_to_int
from labelme._automation._geometry import compute_circle_from_mask
from labelme._automation._geometry import compute_oriented_rectangle_from_mask
from labelme._automation._geometry import compute_polygons_from_mask
from labelme._automation._geometry import shape_to_xyxy_bbox
from labelme._shape import Shape


def test_round_bbox_to_int_uses_ties_to_even_for_tuple_and_array() -> None:
    bbox = (-11.5, -10.5, 10.5, 11.5)
    expected = (-12, -10, 10, 12)

    assert _round_bbox_to_int(bbox=bbox) == expected
    assert _round_bbox_to_int(bbox=np.array(bbox, dtype=np.float32)) == expected


def test_compute_circle_from_mask_returns_none_when_empty() -> None:
    assert compute_circle_from_mask(mask=np.zeros((10, 10), dtype=bool)) is None


def test_compute_circle_from_mask_centroid_and_area_equivalent_radius() -> None:
    mask = np.zeros((11, 11), dtype=bool)
    mask[0:3, 0:3] = True

    circle = compute_circle_from_mask(mask=mask)

    assert circle is not None
    assert circle.cx == pytest.approx(1)
    assert circle.cy == pytest.approx(1)
    assert circle.radius == pytest.approx(math.sqrt(9 / math.pi))


def test_compute_oriented_rectangle_from_mask_returns_none_when_empty() -> None:
    assert (
        compute_oriented_rectangle_from_mask(mask=np.zeros((10, 10), dtype=bool))
        is None
    )


def test_compute_oriented_rectangle_from_mask_returns_none_when_single_pixel() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[3, 4] = True
    assert compute_oriented_rectangle_from_mask(mask=mask) is None


def test_compute_oriented_rectangle_from_mask_axis_aligned_wider_than_tall() -> None:
    # 21x11 mask (cols x rows): wider than tall, so the long axis is +x and the
    # corners trace (xmin, ymin) → (xmax, ymin) → (xmax, ymax) → (xmin, ymax).
    mask = np.ones((11, 21), dtype=bool)

    corners = compute_oriented_rectangle_from_mask(mask=mask)

    assert corners is not None
    expected = np.array(
        [[0, 0], [20, 0], [20, 10], [0, 10]],
        dtype=np.float32,
    )
    assert corners == pytest.approx(expected)


def test_compute_oriented_rectangle_from_mask_axis_aligned_taller_than_wide() -> None:
    # 11x21 mask (cols x rows): taller than wide, so the long axis is +y. The
    # right-handed perpendicular rotates the corner sequence one quarter turn
    # relative to the wider-than-tall case while keeping the same convention.
    mask = np.ones((21, 11), dtype=bool)

    corners = compute_oriented_rectangle_from_mask(mask=mask)

    assert corners is not None
    expected = np.array(
        [[10, 0], [10, 20], [0, 20], [0, 0]],
        dtype=np.float32,
    )
    assert corners == pytest.approx(expected)


def test_compute_oriented_rectangle_from_mask_recovers_rotation_angle(
    *,
    rotated_rectangle_mask: NDArray[np.bool_],
    rotated_rectangle_angle: float,
) -> None:
    corners = compute_oriented_rectangle_from_mask(mask=rotated_rectangle_mask)

    assert corners is not None
    edge = corners[1] - corners[0]
    recovered = math.atan2(float(edge[1]), float(edge[0]))
    assert recovered == pytest.approx(rotated_rectangle_angle, abs=math.radians(3))


def test_compute_oriented_rectangle_from_mask_returns_none_for_collinear_mask() -> None:
    # All set pixels lie on a single row, so the convex hull collapses to two
    # points and there is no rectangle to fit. Bail out so callers fall back
    # to the axis-aligned bbox.
    mask = np.zeros((10, 10), dtype=bool)
    mask[5, :] = True
    assert compute_oriented_rectangle_from_mask(mask=mask) is None


def test_compute_oriented_rectangle_from_mask_square_mask_is_axis_aligned() -> None:
    # A square mask has a well-defined minimum-area rectangle (the bbox
    # itself), unlike the variance-based PCA approach which is ambiguous
    # under equal eigenvalues.
    mask = np.ones((11, 11), dtype=bool)

    corners = compute_oriented_rectangle_from_mask(mask=mask)

    assert corners is not None
    expected = np.array(
        [[0, 0], [10, 0], [10, 10], [0, 10]],
        dtype=np.float32,
    )
    assert corners == pytest.approx(expected)


def test_shape_to_xyxy_bbox_circle() -> None:
    shape = Shape(
        shape_type="circle", points=np.array([(50, 40), (53, 44)], dtype=np.float64)
    )

    bbox = shape_to_xyxy_bbox(shape=shape)

    radius = math.sqrt((53 - 50) ** 2 + (44 - 40) ** 2)
    assert bbox is not None
    assert bbox.tolist() == pytest.approx(
        [50 - radius, 40 - radius, 50 + radius, 40 + radius]
    )


def test_shape_to_xyxy_bbox_polygon() -> None:
    shape = Shape(
        shape_type="polygon",
        points=np.array([(1, 2), (10, 4), (6, 12)], dtype=np.float64),
    )

    bbox = shape_to_xyxy_bbox(shape=shape)

    assert bbox is not None
    assert bbox.tolist() == pytest.approx([1, 2, 10, 12])


def test_shape_to_xyxy_bbox_returns_none_when_polygon_has_too_few_points() -> None:
    shape = Shape(
        shape_type="polygon", points=np.array([(0, 0), (10, 10)], dtype=np.float64)
    )

    assert shape_to_xyxy_bbox(shape=shape) is None


def test_shape_to_xyxy_bbox_returns_none_when_circle_has_only_center() -> None:
    shape = Shape(shape_type="circle", points=np.array([(5, 5)], dtype=np.float64))

    assert shape_to_xyxy_bbox(shape=shape) is None


def test_shape_to_xyxy_bbox_rectangle() -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(10, 4), (1, 12)], dtype=np.float64),
    )

    bbox = shape_to_xyxy_bbox(shape=shape)

    assert bbox is not None
    assert bbox.tolist() == pytest.approx([1, 4, 10, 12])


def test_shape_to_xyxy_bbox_mask() -> None:
    shape = Shape(
        shape_type="mask",
        points=np.array([(20, 5), (3, 8)], dtype=np.float64),
    )

    bbox = shape_to_xyxy_bbox(shape=shape)

    assert bbox is not None
    assert bbox.tolist() == pytest.approx([3, 5, 20, 8])


def test_shape_to_xyxy_bbox_oriented_rectangle() -> None:
    shape = Shape(
        shape_type="oriented_rectangle",
        points=np.array([(1, 1), (5, 0), (6, 4), (2, 5)], dtype=np.float64),
    )

    bbox = shape_to_xyxy_bbox(shape=shape)

    assert bbox is not None
    assert bbox.tolist() == pytest.approx([1, 0, 6, 5])


def test_shape_to_xyxy_bbox_returns_none_when_rectangle_has_too_few_points() -> None:
    shape = Shape(shape_type="rectangle", points=np.array([(5, 5)], dtype=np.float64))

    assert shape_to_xyxy_bbox(shape=shape) is None


def test_shape_to_xyxy_bbox_returns_none_when_mask_has_too_few_points() -> None:
    shape = Shape(shape_type="mask", points=np.array([(5, 5)], dtype=np.float64))

    assert shape_to_xyxy_bbox(shape=shape) is None


def test_shape_to_xyxy_bbox_none_when_oriented_rectangle_has_too_few_points() -> None:
    shape = Shape(
        shape_type="oriented_rectangle",
        points=np.array([(0, 0), (5, 0), (5, 5)], dtype=np.float64),
    )

    assert shape_to_xyxy_bbox(shape=shape) is None


def test_shape_to_xyxy_bbox_raises_on_unsupported_shape_type() -> None:
    shape = Shape(shape_type="point", points=np.array([(1, 2)], dtype=np.float64))

    with pytest.raises(ValueError, match="Unsupported shape_type"):
        shape_to_xyxy_bbox(shape=shape)


def test_compute_polygons_from_mask_returns_empty_for_empty_mask() -> None:
    polygons = compute_polygons_from_mask(mask=np.zeros((5, 5), dtype=bool))

    assert polygons == []


def test_compute_polygons_from_mask_drops_concave_land_with_too_little_clearance() -> (
    None
):
    mask = np.array(
        [
            [True, True, True],
            [True, False, False],
            [True, False, False],
        ]
    )

    assert compute_polygons_from_mask(mask=mask, detail=75) == []


def test_compute_polygons_from_mask_drops_corner_land_with_too_little_clearance() -> (
    None
):
    mask = np.array(
        [
            [True, True, True],
            [True, False, True],
            [True, True, False],
        ]
    )

    assert compute_polygons_from_mask(mask=mask, detail=75) == []


def test_compute_polygons_from_mask_drops_land_at_exact_clearance_threshold() -> None:
    mask = np.array(
        [
            [False, True, True, False],
            [True, True, True, True],
            [True, True, True, True],
            [False, True, True, False],
        ]
    )

    assert compute_polygons_from_mask(mask=mask, detail=60) == []


def test_compute_polygons_from_mask_traces_rectangle_extent_in_xy_order() -> None:
    # Rows 1-3, cols 1-7 set. The result is xy-ordered, so the max extent is
    # x=7.5, y=3.5 (a yx result would swap them, which the max assertion catches).
    # The coordinates are the region's half-pixel boundary in image space:
    # x in [0.5, 7.5], y in [0.5, 3.5].
    mask = np.zeros((5, 9), dtype=bool)
    mask[1:4, 1:8] = True

    [polygon] = compute_polygons_from_mask(mask=mask)

    assert polygon.min(axis=0) == pytest.approx([0.5, 0.5], abs=0.001)
    assert polygon.max(axis=0) == pytest.approx([7.5, 3.5], abs=0.001)


def test_compute_polygons_from_mask_returns_every_disconnected_land() -> None:
    mask = np.zeros((10, 12), dtype=bool)
    mask[1:5, 1:7] = True
    mask[6:9, 8:11] = True

    polygons = compute_polygons_from_mask(mask=mask)

    assert len(polygons) == 2
    extents = np.array(
        sorted(
            (polygon.min(axis=0).tolist(), polygon.max(axis=0).tolist())
            for polygon in polygons
        )
    )
    np.testing.assert_allclose(
        extents,
        [[[0.5, 0.5], [6.5, 4.5]], [[7.5, 5.5], [10.5, 8.5]]],
        atol=0.001,
    )


def test_compute_polygons_from_mask_traces_all_lands_once(
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mask = np.zeros((10, 12), dtype=bool)
    mask[1:5, 1:7] = True
    mask[6:8, 6:8] = True
    calls = 0
    find_contours = skimage.measure.find_contours

    def count_calls(
        image: NDArray[np.bool_],
        *,
        fully_connected: str,
        positive_orientation: str,
    ) -> list[NDArray[np.float64]]:
        nonlocal calls
        calls += 1
        return find_contours(
            image,
            fully_connected=fully_connected,
            positive_orientation=positive_orientation,
        )

    monkeypatch.setattr(skimage.measure, "find_contours", count_calls)

    polygons = compute_polygons_from_mask(mask=mask, detail=100)

    assert len(polygons) == 2
    assert calls == 1


def test_compute_polygons_from_mask_keeps_tiny_land_at_large_coordinates() -> None:
    mask = np.zeros((3010, 3010), dtype=bool)
    mask[2999, 2999] = True

    polygons = compute_polygons_from_mask(mask=mask, detail=100)

    assert len(polygons) == 1


def test_compute_polygons_from_mask_drops_curved_land_within_deviation() -> None:
    mask = np.zeros((50, 50), dtype=bool)
    mask[10:40, 10] = True
    mask[39, 10:40] = True
    mask[10:40, 39] = True

    polygons = compute_polygons_from_mask(mask=mask, detail=0)

    assert polygons == []


def test_compute_polygons_from_mask_keeps_compact_land_beyond_deviation() -> None:
    mask = np.zeros((50, 50), dtype=bool)
    mask[10:30, 10:30] = True

    polygons = compute_polygons_from_mask(mask=mask, detail=0)

    assert len(polygons) == 1


def test_compute_polygons_from_mask_keeps_boundary_error_within_deviation() -> None:
    mask = np.zeros((30, 30), dtype=bool)
    mask[2:28, 2:14] = True
    mask[16:28, 2:28] = True
    [contour] = skimage.measure.find_contours(
        np.pad(mask, pad_width=1),
        fully_connected="low",
        positive_orientation="low",
    )
    original_points = (contour - 1)[:, ::-1]

    [polygon] = compute_polygons_from_mask(mask=mask, detail=0)

    starts = polygon
    vectors = np.roll(polygon, shift=-1, axis=0) - starts
    offsets = original_points[:, np.newaxis, :] - starts[np.newaxis, :, :]
    positions = np.clip(
        np.sum(offsets * vectors, axis=2) / np.sum(vectors**2, axis=1),
        0,
        1,
    )
    closest = starts + positions[:, :, np.newaxis] * vectors
    distances = np.linalg.norm(
        original_points[:, np.newaxis, :] - closest,
        axis=2,
    )
    assert distances.min(axis=1).max() <= _compute_polygon_deviation(detail=0) + 0.001


def test_compute_polygons_from_mask_keeps_half_pixel_boundary_at_image_edge() -> None:
    # A fully-set mask has no background border, so its contour is the outer
    # half-pixel boundary: x in [-0.5, W-0.5], y in [-0.5, H-0.5]. The near side
    # clips to 0, while the far side must clamp to mask size (W=9, H=5), not
    # size-1, so it keeps its half-pixel offset (8.5, 4.5) instead of being
    # pulled in by a pixel.
    mask = np.ones((5, 9), dtype=bool)

    [polygon] = compute_polygons_from_mask(mask=mask)

    assert polygon.min(axis=0) == pytest.approx([0.0, 0.0])
    assert polygon.max(axis=0) == pytest.approx([8.5, 4.5], abs=0.001)
    incoming = polygon - np.roll(polygon, shift=1, axis=0)
    outgoing = np.roll(polygon, shift=-1, axis=0) - polygon
    cross_products = incoming[:, 0] * outgoing[:, 1] - incoming[:, 1] * outgoing[:, 0]
    assert np.all(np.abs(cross_products) > np.finfo(np.float32).eps)


def test_compute_polygons_from_mask_detail_controls_point_count() -> None:
    mask = np.zeros((100, 100), dtype=bool)
    mask[20:80, 30:70] = True

    [maximum_detail] = compute_polygons_from_mask(mask=mask, detail=100)
    [balanced_detail] = compute_polygons_from_mask(mask=mask, detail=80)

    assert len(maximum_detail) == 8
    assert len(balanced_detail) == 4


@pytest.mark.parametrize("detail", [-1, 101])
def test_compute_polygons_from_mask_rejects_detail_outside_range(
    *, detail: int
) -> None:
    with pytest.raises(ValueError, match="detail must be between 0 and 100"):
        compute_polygons_from_mask(mask=np.ones((5, 5), dtype=bool), detail=detail)


def test_compute_oriented_rectangle_from_mask_l_shape_is_axis_aligned() -> None:
    # An L-shape with axis-aligned arms: the minimum-area enclosing rectangle
    # is the axis-aligned bbox, regardless of how mass is distributed between
    # the arms. PCA tilts the principal axis toward the heavier arm, which is
    # the failure mode this implementation avoids.
    mask = np.zeros((20, 30), dtype=bool)
    mask[0:5, 0:30] = True
    mask[0:20, 0:5] = True

    corners = compute_oriented_rectangle_from_mask(mask=mask)

    assert corners is not None
    expected = np.array(
        [[0, 0], [29, 0], [29, 19], [0, 19]],
        dtype=np.float32,
    )
    assert corners == pytest.approx(expected)
