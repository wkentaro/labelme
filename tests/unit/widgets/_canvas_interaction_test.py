from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMenu

from labelme._shape import Shape
from labelme.widgets._canvas_interaction import ContextMenuPair
from labelme.widgets._canvas_interaction import CursorRole
from labelme.widgets._canvas_interaction import HitKind
from labelme.widgets._canvas_interaction import HitTarget
from labelme.widgets._canvas_interaction import cursor_shape_for
from labelme.widgets._canvas_interaction import find_hover_target
from labelme.widgets._canvas_interaction import is_within_pick_threshold

# Shared test constants
_EPSILON: float = 10.0
_SCALE: float = 1.0
_POINT_SIZE: int = 8


def _point(x: float, y: float) -> np.ndarray:
    return np.array([x, y], dtype=np.float64)


def _polygon(points: list[tuple[float, float]], *, visible: bool = True) -> Shape:
    return Shape(
        shape_type="polygon",
        points=np.array(points, dtype=np.float64),
        closed=True,
        visible=visible,
    )


# ---------------------------------------------------------------------------
# HitTarget
# ---------------------------------------------------------------------------


def test_hit_target_frozen() -> None:
    shape = _polygon([(0, 0), (10, 0), (10, 10)])
    target = HitTarget(kind=HitKind.BODY, shape=shape, index=None)
    with pytest.raises((AttributeError, TypeError)):
        target.kind = HitKind.VERTEX  # ty: ignore[invalid-assignment]


# ---------------------------------------------------------------------------
# find_hover_target — empty shapes
# ---------------------------------------------------------------------------


def test_find_hover_target_empty_shapes_returns_none() -> None:
    result = find_hover_target(
        shapes=[],
        point=_point(0.0, 0.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=None,
    )
    assert result is None


# ---------------------------------------------------------------------------
# find_hover_target — visibility filtering
# ---------------------------------------------------------------------------


def test_invisible_shapes_are_excluded() -> None:
    invisible = _polygon([(10, 10), (50, 10), (50, 50), (10, 50)], visible=False)
    result = find_hover_target(
        shapes=[invisible],
        point=_point(25.0, 25.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=None,
    )
    assert result is None


def test_visible_shape_body_hit() -> None:
    shape = _polygon([(10, 10), (50, 10), (50, 50), (10, 50)])
    result = find_hover_target(
        shapes=[shape],
        point=_point(25.0, 25.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=None,
    )
    assert result is not None
    assert result.kind == HitKind.BODY
    assert result.shape is shape


# ---------------------------------------------------------------------------
# find_hover_target — category precedence: vertex > rotation > edge > body
# ---------------------------------------------------------------------------


def test_vertex_match_beats_body() -> None:
    # Shape with vertex at (10, 10); hover exactly on vertex -> VERTEX, not BODY.
    shape = _polygon([(10, 10), (50, 10), (50, 50), (10, 50)])
    result = find_hover_target(
        shapes=[shape],
        point=_point(10.0, 10.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=None,
    )
    assert result is not None
    assert result.kind == HitKind.VERTEX
    assert result.shape is shape
    assert result.index == 0


def test_vertex_on_last_candidate_beats_body_on_first_candidate() -> None:
    # Two shapes: first (in list order) has a body at (25, 25) and its vertex
    # far away; second (examined first in reverse order) has a vertex at (10, 10).
    # Hover at (10, 10): the VERTEX on the second (topmost) shape must win.
    body_shape = _polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    vertex_shape = _polygon([(10, 10), (50, 10), (50, 50), (10, 50)])
    # shapes=[body_shape, vertex_shape]: reverse order tries vertex_shape first.
    result = find_hover_target(
        shapes=[body_shape, vertex_shape],
        point=_point(10.0, 10.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=None,
    )
    assert result is not None
    assert result.kind == HitKind.VERTEX
    assert result.shape is vertex_shape


def test_category_precedence_vertex_over_body_across_shapes() -> None:
    # Shape A (listed first, lower paint order): has body at center, vertex far.
    # Shape B (listed second, higher paint order, examined first): vertex at (10,10).
    # Hover at (10,10): vertex category dominates even though shape A is "first".
    big = _polygon([(0, 0), (200, 0), (200, 200), (0, 200)])
    small = _polygon([(10, 10), (50, 10), (50, 50), (10, 50)])
    result = find_hover_target(
        shapes=[big, small],
        point=_point(10.0, 10.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=None,
    )
    assert result is not None
    assert result.kind == HitKind.VERTEX
    assert result.shape is small


# ---------------------------------------------------------------------------
# find_hover_target — edge pass only for can_add_point shapes
# ---------------------------------------------------------------------------


def test_edge_hit_on_polygon() -> None:
    # polygon: midpoint of top edge (10,10)-(90,10) is (50,10).
    shape = _polygon([(10, 10), (90, 10), (90, 50), (10, 50)])
    result = find_hover_target(
        shapes=[shape],
        point=_point(50.0, 10.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=None,
    )
    # Should be VERTEX or EDGE depending on distance to vertices.
    # (50,10) is 40px from (10,10) and 40px from (90,10) — no vertex hit.
    assert result is not None
    assert result.kind == HitKind.EDGE
    assert result.shape is shape


def test_edge_not_tested_on_non_polyline_shape() -> None:
    # A rectangle does not support can_add_point; an edge-only hover returns NONE
    # (no vertex, no rotation, no edge pass, and body miss at far point).
    rect = Shape(
        shape_type="rectangle",
        points=np.array([(10, 10), (50, 50)], dtype=np.float64),
        closed=True,
    )
    # Hover at midpoint of top edge: (30, 10). For rectangle this should be BODY
    # (inside path test), not EDGE.
    result = find_hover_target(
        shapes=[rect],
        point=_point(30.0, 30.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=None,
    )
    # rectangle is not a polyline, so edge pass is skipped; body hit for interior.
    assert result is not None
    assert result.kind == HitKind.BODY
    assert result.shape is rect


# ---------------------------------------------------------------------------
# find_hover_target — priority_shape ordering
# ---------------------------------------------------------------------------


def test_priority_shape_is_checked_first() -> None:
    # priority_shape is listed last in shapes but must be tried first.
    # Two shapes overlap at (10,10). priority_shape has vertex at (10,10).
    # The other shape also has vertex at (10,10).
    # Without priority, reverse order tries shape_b first (it is last in list).
    # With priority=shape_a, shape_a is tried first.
    shape_a = _polygon([(10, 10), (50, 10), (50, 50), (10, 50)])
    shape_b = _polygon([(10, 10), (80, 10), (80, 80), (10, 80)])
    result = find_hover_target(
        shapes=[shape_b, shape_a],
        point=_point(10.0, 10.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=shape_a,
    )
    assert result is not None
    assert result.kind == HitKind.VERTEX
    assert result.shape is shape_a


def test_priority_shape_not_in_shapes_is_still_checked() -> None:
    # priority_shape need not be a member of shapes.
    orphan = _polygon([(10, 10), (50, 10), (50, 50), (10, 50)])
    result = find_hover_target(
        shapes=[],
        point=_point(10.0, 10.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=orphan,
    )
    assert result is not None
    assert result.kind == HitKind.VERTEX
    assert result.shape is orphan


def test_priority_shape_not_duplicated_in_candidates() -> None:
    # priority_shape appears in shapes; it must not be examined twice.
    shape = _polygon([(10, 10), (50, 10), (50, 50), (10, 50)])
    # Only one match expected: VERTEX at index 0.
    result = find_hover_target(
        shapes=[shape],
        point=_point(10.0, 10.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=shape,
    )
    assert result is not None
    assert result.kind == HitKind.VERTEX
    assert result.shape is shape
    assert result.index == 0


# ---------------------------------------------------------------------------
# find_hover_target — reverse paint order for non-priority shapes
# ---------------------------------------------------------------------------


def test_reverse_paint_order_topmost_body_wins() -> None:
    # Two overlapping body-only shapes. The second in the list (top paint layer)
    # should be returned as the body hit.
    shape_a = _polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    shape_b = _polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    result = find_hover_target(
        shapes=[shape_a, shape_b],
        point=_point(50.0, 50.0),
        scale=_SCALE,
        epsilon=_EPSILON,
        point_size=_POINT_SIZE,
        priority_shape=None,
    )
    assert result is not None
    assert result.kind == HitKind.BODY
    # shape_b is last in list, so first in reverse order — it should match first.
    assert result.shape is shape_b


# ---------------------------------------------------------------------------
# is_within_pick_threshold
# ---------------------------------------------------------------------------


def test_is_within_pick_threshold_strictly_less_than() -> None:
    a = _point(0.0, 0.0)
    # Distance = epsilon/scale - small delta => True
    b = _point(9.9, 0.0)
    assert is_within_pick_threshold(a=a, b=b, scale=_SCALE, epsilon=_EPSILON) is True


def test_is_within_pick_threshold_at_boundary_false() -> None:
    # Exactly at epsilon/scale is NOT within (strictly less than).
    a = _point(0.0, 0.0)
    b = _point(10.0, 0.0)
    assert is_within_pick_threshold(a=a, b=b, scale=_SCALE, epsilon=_EPSILON) is False


def test_is_within_pick_threshold_beyond_boundary_false() -> None:
    a = _point(0.0, 0.0)
    b = _point(11.0, 0.0)
    assert is_within_pick_threshold(a=a, b=b, scale=_SCALE, epsilon=_EPSILON) is False


def test_is_within_pick_threshold_scale_shrinks_image_radius() -> None:
    # At scale=2, the image-space threshold is epsilon/2 = 5.
    # Distance of 6 in image space > 5, so False.
    a = _point(0.0, 0.0)
    b = _point(6.0, 0.0)
    assert is_within_pick_threshold(a=a, b=b, scale=2.0, epsilon=_EPSILON) is False


def test_is_within_pick_threshold_scale_shrinks_image_radius_hit() -> None:
    # At scale=2, image threshold = 5. Distance of 4 < 5 => True.
    a = _point(0.0, 0.0)
    b = _point(4.0, 0.0)
    assert is_within_pick_threshold(a=a, b=b, scale=2.0, epsilon=_EPSILON) is True


def test_is_within_pick_threshold_larger_scale_smaller_image_radius() -> None:
    # At scale=0.5, image threshold = 20. Distance 15 < 20 => True.
    a = _point(0.0, 0.0)
    b = _point(15.0, 0.0)
    assert is_within_pick_threshold(a=a, b=b, scale=0.5, epsilon=_EPSILON) is True


# ---------------------------------------------------------------------------
# cursor_shape_for
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (CursorRole.DEFAULT, Qt.CursorShape.ArrowCursor),
        (CursorRole.DRAW, Qt.CursorShape.CrossCursor),
        (CursorRole.HANDLE, Qt.CursorShape.PointingHandCursor),
        (CursorRole.GRAB, Qt.CursorShape.OpenHandCursor),
        (CursorRole.MOVE, Qt.CursorShape.ClosedHandCursor),
    ],
)
def test_cursor_shape_for_all_roles(role: CursorRole, expected: Qt.CursorShape) -> None:
    assert cursor_shape_for(role) == expected


# ---------------------------------------------------------------------------
# ContextMenuPair
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_context_menu_pair_menu_for_no_selection(
    qapp: QApplication,
) -> None:
    without = QMenu()
    with_ = QMenu()
    pair = ContextMenuPair(without_selection=without, with_selection=with_)
    assert pair.menu_for(has_selection=False) is without


@pytest.mark.gui
def test_context_menu_pair_menu_for_with_selection(
    qapp: QApplication,
) -> None:
    without = QMenu()
    with_ = QMenu()
    pair = ContextMenuPair(without_selection=without, with_selection=with_)
    assert pair.menu_for(has_selection=True) is with_


@pytest.mark.gui
def test_context_menu_pair_stores_menus_as_named_attributes(
    qapp: QApplication,
) -> None:
    without = QMenu()
    with_ = QMenu()
    pair = ContextMenuPair(without_selection=without, with_selection=with_)
    assert pair.without_selection is without
    assert pair.with_selection is with_
