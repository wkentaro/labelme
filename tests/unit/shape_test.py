from __future__ import annotations

import math

import numpy as np
import pytest
from numpy.typing import NDArray
from PyQt5 import QtCore

from labelme.shape import Shape
from labelme.shape import rotate_point_around_origin


def _make_mask_shape(
    mask: NDArray[np.bool_], origin_x: float, origin_y: float
) -> Shape:
    shape = Shape(shape_type="mask")
    h, w = mask.shape
    shape.addPoint(QtCore.QPointF(origin_x, origin_y))
    shape.addPoint(QtCore.QPointF(origin_x + w, origin_y + h))
    shape.mask = mask
    return shape


@pytest.mark.parametrize(
    "point, expected",
    [
        ((4, 3), True),  # inside True region
        ((4, 4), True),  # last valid row/column
        ((5, 2), False),  # one pixel past right boundary
        ((2, 5), False),  # one pixel past bottom boundary
        ((5, 5), False),  # past both boundaries
    ],
)
def test_mask_contains_point(point: tuple[int, int], expected: bool) -> None:
    mask = np.ones((5, 5), dtype=bool)
    shape = _make_mask_shape(mask, origin_x=0, origin_y=0)
    assert shape.containsPoint(QtCore.QPointF(*point)) is expected


@pytest.fixture
def axis_aligned_oriented_rectangle() -> Shape:
    shape = Shape(shape_type="oriented_rectangle")
    for x, y in [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0)]:
        shape.addPoint(QtCore.QPointF(x, y))
    shape.close()
    return shape


@pytest.fixture
def closed_axis_aligned_rectangle() -> Shape:
    shape = Shape(shape_type="rectangle")
    shape.addPoint(QtCore.QPointF(0.0, 0.0))
    shape.addPoint(QtCore.QPointF(10.0, 5.0))
    shape.close()
    return shape


def test_oriented_rectangle_get_center_averages_corners(
    axis_aligned_oriented_rectangle: Shape,
) -> None:
    center = axis_aligned_oriented_rectangle.getCenter()
    assert (center.x(), center.y()) == pytest.approx((5.0, 2.0))


def test_oriented_rectangle_get_rotation_points_are_edge_midpoints(
    axis_aligned_oriented_rectangle: Shape,
) -> None:
    points = axis_aligned_oriented_rectangle.getRotationPoints()
    midpoints = [(p.x(), p.y()) for p in points]
    assert midpoints == pytest.approx([(0.0, 2.0), (5.0, 0.0), (10.0, 2.0), (5.0, 4.0)])


def test_oriented_rectangle_get_angle_rad_matches_first_edge() -> None:
    shape = Shape(shape_type="oriented_rectangle")
    for x, y in [(0.0, 0.0), (1.0, 1.0), (0.0, 2.0), (-1.0, 1.0)]:
        shape.addPoint(QtCore.QPointF(x, y))
    shape.close()
    assert shape.getAngleRad() == pytest.approx(math.pi / 4)


@pytest.mark.parametrize(
    "point, expected",
    [
        (QtCore.QPointF(5.5, 0.2), 1),  # near bottom-edge midpoint (5, 0)
        (QtCore.QPointF(-0.1, 1.9), 0),  # near left-edge midpoint (0, 2)
        (QtCore.QPointF(100.0, 100.0), None),  # too far for epsilon
    ],
)
def test_oriented_rectangle_nearest_rotation_point(
    axis_aligned_oriented_rectangle: Shape,
    point: QtCore.QPointF,
    expected: int | None,
) -> None:
    assert (
        axis_aligned_oriented_rectangle.nearestRotationPoint(point=point, epsilon=5.0)
        == expected
    )


@pytest.mark.parametrize(
    "point, expected",
    [
        (QtCore.QPointF(5.0, 2.0), True),  # inside
        (QtCore.QPointF(20.0, 20.0), False),  # outside
    ],
)
def test_oriented_rectangle_contains_point(
    axis_aligned_oriented_rectangle: Shape,
    point: QtCore.QPointF,
    expected: bool,
) -> None:
    assert axis_aligned_oriented_rectangle.containsPoint(point) is expected


@pytest.mark.parametrize(
    "method_name, expected",
    [
        ("canAddPoint", False),
        ("canRemovePoint", False),
    ],
)
def test_oriented_rectangle_rejects_point_mutation(
    axis_aligned_oriented_rectangle: Shape, method_name: str, expected: bool
) -> None:
    assert getattr(axis_aligned_oriented_rectangle, method_name)() is expected


def test_oriented_rectangle_add_point_does_not_auto_close_on_duplicate() -> None:
    shape = Shape(shape_type="oriented_rectangle")
    point = QtCore.QPointF(1.0, 1.0)
    shape.addPoint(point)
    shape.addPoint(point)
    assert len(shape.points) == 2
    assert not shape.isClosed()


def test_non_oriented_shape_get_angle_rad_returns_zero(
    closed_axis_aligned_rectangle: Shape,
) -> None:
    assert closed_axis_aligned_rectangle.getAngleRad() == 0.0


def test_non_oriented_shape_get_rotation_points_returns_empty(
    closed_axis_aligned_rectangle: Shape,
) -> None:
    assert closed_axis_aligned_rectangle.getRotationPoints() == []


def test_non_oriented_shape_nearest_rotation_point_returns_none(
    closed_axis_aligned_rectangle: Shape,
) -> None:
    assert (
        closed_axis_aligned_rectangle.nearestRotationPoint(
            point=QtCore.QPointF(5.0, 0.0), epsilon=5.0
        )
        is None
    )


@pytest.mark.parametrize(
    "point, angle_rad, expected",
    [
        (np.array([1.0, 0.0]), math.pi / 2, (0.0, 1.0)),
        (np.array([1.0, 0.0]), math.pi, (-1.0, 0.0)),
        (np.array([0.0, 1.0]), -math.pi / 2, (1.0, 0.0)),
    ],
)
def test_rotate_point_around_origin(
    point: np.ndarray, angle_rad: float, expected: tuple[float, float]
) -> None:
    rotated = rotate_point_around_origin(point=point, angle_rad=angle_rad)
    assert (rotated[0], rotated[1]) == pytest.approx(expected)


def test_unsupported_shape_type_raises() -> None:
    with pytest.raises(ValueError):
        Shape(shape_type="bogus shape")
