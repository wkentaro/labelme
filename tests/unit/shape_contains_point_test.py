from __future__ import annotations

from PyQt5 import QtCore

from labelme.shape import Shape


def _make_point_shape(x: float, y: float) -> Shape:
    """Create a point shape with a single point at (x, y)."""
    shape = Shape(shape_type="point")
    shape.addPoint(QtCore.QPointF(x, y))
    return shape


def test_point_shape_contains_center():
    """Clicking exactly on a point shape should return True."""
    shape = _make_point_shape(100.0, 200.0)
    assert shape.containsPoint(QtCore.QPointF(100.0, 200.0)) is True


def test_point_shape_contains_within_radius():
    """Clicking within point_size/2 of the center should return True."""
    shape = _make_point_shape(100.0, 200.0)
    # point_size defaults to 8, so radius = 4. A point 3px away should hit.
    assert shape.containsPoint(QtCore.QPointF(103.0, 200.0)) is True


def test_point_shape_at_exact_boundary():
    """Clicking exactly at point_size/2 distance should return True (inclusive)."""
    shape = _make_point_shape(100.0, 200.0)
    # point_size defaults to 8, so radius = 4. Exactly 4px away should hit.
    assert shape.containsPoint(QtCore.QPointF(104.0, 200.0)) is True


def test_point_shape_outside_radius():
    """Clicking more than point_size/2 away should return False."""
    shape = _make_point_shape(100.0, 200.0)
    # 10px away, well outside the radius of 4
    assert shape.containsPoint(QtCore.QPointF(110.0, 200.0)) is False


def test_point_shape_empty_points():
    """A point shape with no points should return False, not raise."""
    shape = Shape(shape_type="point")
    assert shape.containsPoint(QtCore.QPointF(0.0, 0.0)) is False
