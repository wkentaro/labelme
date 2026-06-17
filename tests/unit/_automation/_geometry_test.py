from __future__ import annotations

import math

import numpy as np
import pytest
from numpy.typing import NDArray

from labelme._automation._geometry import compute_circle_from_mask
from labelme._automation._geometry import compute_oriented_rectangle_from_mask
from labelme._automation._geometry import compute_polygon_from_mask
from labelme._automation._geometry import shape_to_xyxy_bbox
from labelme._shape import Shape


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


def test_shape_to_xyxy_bbox_raises_on_unsupported_shape_type() -> None:
    shape = Shape(shape_type="point", points=np.array([(1, 2)], dtype=np.float64))

    with pytest.raises(ValueError, match="Unsupported shape_type"):
        shape_to_xyxy_bbox(shape=shape)


def test_compute_polygon_from_mask_returns_empty_for_empty_mask() -> None:
    polygon = compute_polygon_from_mask(mask=np.zeros((5, 5), dtype=bool))

    assert polygon.shape == (0, 2)


def test_compute_polygon_from_mask_traces_rectangle_extent_in_xy_order() -> None:
    # Rows 1-3, cols 1-7 set. The result is xy-ordered, so the max extent is
    # x=8.0, y=4.0 (a yx result would swap them, which the max assertion catches).
    # The lower bound is the contour's half-pixel offset; the upper bound is
    # clamped to mask size minus 1.
    mask = np.zeros((5, 9), dtype=bool)
    mask[1:4, 1:8] = True

    polygon = compute_polygon_from_mask(mask=mask)

    assert polygon.min(axis=0) == pytest.approx([1.5, 1.5])
    assert polygon.max(axis=0) == pytest.approx([8.0, 4.0])


def test_compute_polygon_from_mask_picks_largest_contour() -> None:
    # Two blobs; the longer-perimeter 4x6 block wins over the 2x2 one, so the
    # returned polygon spans the larger block only.  The large blob is
    # non-square so a yx/xy transposition would swap the unequal extents and
    # fail both the selection check and the axis-order check simultaneously.
    mask = np.zeros((10, 12), dtype=bool)
    mask[1:5, 1:7] = True
    mask[6:8, 6:8] = True

    polygon = compute_polygon_from_mask(mask=mask)

    assert polygon.min(axis=0) == pytest.approx([1.5, 1.5])
    assert polygon.max(axis=0) == pytest.approx([7.5, 5.5])


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
