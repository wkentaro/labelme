from __future__ import annotations

import math

import numpy as np
import pytest
from loguru import logger

from labelme import _shape
from labelme._shape import Shape
from labelme._shape import ShapeType


def _make_oriented_rectangle(points: list[tuple[float, float]]) -> Shape:
    return Shape(
        shape_type="oriented_rectangle",
        points=np.array(points, dtype=np.float64),
        closed=True,
    )


def _make_axis_aligned_oriented_rectangle() -> Shape:
    return _make_oriented_rectangle([(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0)])


def test_rotate_oriented_rectangle_around_origin() -> None:
    shape = _make_axis_aligned_oriented_rectangle()

    _shape.rotate(
        shape=shape,
        center=np.array([0.0, 0.0]),
        angle=math.pi / 2,
    )

    expected = [(0.0, 0.0), (0.0, 10.0), (-4.0, 10.0), (-4.0, 0.0)]
    for i, (x, y) in enumerate(expected):
        assert (shape.points[i][0], shape.points[i][1]) == pytest.approx((x, y))


def test_oriented_rectangle_center_of_axis_aligned() -> None:
    shape = _make_axis_aligned_oriented_rectangle()

    center = _shape.oriented_rectangle_center(shape=shape)

    assert (center[0], center[1]) == pytest.approx((5.0, 2.0))


def test_oriented_rectangle_center_of_rotated_rectangle() -> None:
    # A non-axis-aligned (45 deg) rectangle, so the center is exercised on a
    # rotated shape rather than only the trivial axis-aligned case.
    shape = Shape(
        shape_type="oriented_rectangle",
        points=np.array(
            [(5.0, 0.0), (10.0, 5.0), (5.0, 10.0), (0.0, 5.0)], dtype=np.float64
        ),
        closed=True,
    )

    center = _shape.oriented_rectangle_center(shape=shape)

    assert (center[0], center[1]) == pytest.approx((5.0, 5.0))


def test_oriented_rectangle_center_raises_for_wrong_shape_type() -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(0.0, 0.0), (10.0, 4.0)], dtype=np.float64),
    )

    with pytest.raises(ValueError, match="only defined for oriented rectangles"):
        _shape.oriented_rectangle_center(shape=shape)


def test_oriented_rectangle_center_raises_for_wrong_point_count() -> None:
    shape = Shape(
        shape_type="oriented_rectangle",
        points=np.array([(0.0, 0.0), (10.0, 0.0), (10.0, 4.0)], dtype=np.float64),
    )

    with pytest.raises(ValueError, match="requires 4 points"):
        _shape.oriented_rectangle_center(shape=shape)


def test_rotate_non_oriented_rectangle_raises() -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(0.0, 0.0), (10.0, 5.0)], dtype=np.float64),
        closed=True,
    )

    with pytest.raises(ValueError):
        _shape.rotate(
            shape=shape,
            center=np.array([0.0, 0.0]),
            angle=math.pi / 2,
        )


def test_rotate_uses_source_points_snapshot_not_current_points() -> None:
    # Given source_points, rotate() computes from it and ignores the shape's
    # current points. This single-call precedence is what lets an interactive
    # drag replay from a fixed snapshot; it is the only path production uses
    # (canvas.py always passes source_points).
    source_points = np.array(
        [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0)], dtype=np.float64
    )
    shape = _make_oriented_rectangle([(1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (4.0, 4.0)])

    _shape.rotate(
        shape=shape,
        center=np.array([0.0, 0.0]),
        angle=math.pi / 2,
        source_points=source_points,
    )

    expected = [(0.0, 0.0), (0.0, 10.0), (-4.0, 10.0), (-4.0, 0.0)]
    for i, (x, y) in enumerate(expected):
        assert (shape.points[i][0], shape.points[i][1]) == pytest.approx((x, y))


def test_rotate_reports_source_points_length_in_error() -> None:
    shape = _make_axis_aligned_oriented_rectangle()
    source_points = np.array([(0.0, 0.0), (10.0, 0.0), (10.0, 4.0)], dtype=np.float64)

    with pytest.raises(ValueError, match=r"len\(source_points\)=3"):
        _shape.rotate(
            shape=shape,
            center=np.array([0.0, 0.0]),
            angle=math.pi / 2,
            source_points=source_points,
        )


def test_nearest_vertex_index_returns_none_for_mask() -> None:
    # Mask bbox is anchored to the bitmap; exposing draggable vertices would
    # desync the rectangle from the mask.
    shape = Shape(
        shape_type="mask",
        mask=np.ones((4, 4), dtype=bool),
        points=np.array([(0.0, 0.0), (3.0, 3.0)], dtype=np.float64),
        closed=True,
    )

    for corner in shape.points:
        assert (
            _shape.nearest_vertex_index(
                shape=shape, point=corner, scale=1.0, epsilon=10.0
            )
            is None
        )


def test_nearest_vertex_index_returns_none_for_point() -> None:
    # A point shape's single point is the shape itself, not a draggable vertex;
    # it is selected and moved as a whole, so it exposes no vertex to hit.
    shape = Shape(
        shape_type="point",
        points=np.array([(5.0, 5.0)], dtype=np.float64),
        closed=True,
    )

    assert (
        _shape.nearest_vertex_index(
            shape=shape, point=shape.points[0], scale=1.0, epsilon=10.0
        )
        is None
    )


def _make_square_polygon() -> Shape:
    return Shape(
        shape_type="polygon",
        points=np.array(
            [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)], dtype=np.float64
        ),
        closed=True,
    )


def _make_open_linestrip() -> Shape:
    return Shape(
        shape_type="linestrip",
        points=np.array([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], dtype=np.float64),
    )


@pytest.mark.parametrize(
    # One row per ShapeType member; changing an existing type's membership in
    # POLYLINE_SHAPE_TYPES flips can_add_point and fails its row here.
    ("shape_type", "expected"),
    [
        ("polygon", True),
        ("linestrip", True),
        ("rectangle", False),
        ("oriented_rectangle", False),
        ("point", False),
        ("line", False),
        ("circle", False),
        ("points", False),
        ("mask", False),
    ],
)
def test_can_add_point(shape_type: ShapeType, expected: bool) -> None:
    assert Shape(shape_type=shape_type).can_add_point() is expected


def test_insert_point_keeps_points_and_labels_in_sync() -> None:
    shape = _make_square_polygon()

    shape.insert_point(i=1, point=(5.0, 0.0))

    assert len(shape.points) == 5
    assert len(shape.point_labels) == 5
    assert shape.points[1] == pytest.approx((5.0, 0.0))
    assert int(shape.point_labels[1]) == 1


def test_insert_point_records_label() -> None:
    shape = _make_square_polygon()

    shape.insert_point(i=0, point=(1.0, 1.0), label=0)

    assert int(shape.point_labels[0]) == 0


def test_insert_point_is_noop_for_non_polyline() -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(0.0, 0.0), (10.0, 10.0)], dtype=np.float64),
    )

    shape.insert_point(i=1, point=(5.0, 5.0))

    assert len(shape.points) == 2
    assert len(shape.point_labels) == 2


def test_insert_point_noop_logs_shape_state() -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(0.0, 0.0), (10.0, 10.0)], dtype=np.float64),
    )
    messages: list[str] = []
    sink_id = logger.add(
        lambda m: messages.append(m.record["message"]), level="WARNING"
    )

    try:
        shape.insert_point(i=1, point=(5.0, 5.0))
    finally:
        logger.remove(sink_id)

    assert messages == ["Cannot add point to: shape_type='rectangle', len(points)=2"]


def test_can_remove_point_polygon_requires_more_than_three() -> None:
    shape = _make_square_polygon()
    assert shape.can_remove_point() is True

    shape.remove_point(i=0)
    assert len(shape.points) == 3
    assert shape.can_remove_point() is False


def test_can_remove_point_linestrip_requires_more_than_two() -> None:
    shape = Shape(
        shape_type="linestrip",
        points=np.array([(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)], dtype=np.float64),
    )
    assert shape.can_remove_point() is True

    shape.remove_point(i=1)
    assert len(shape.points) == 2
    assert shape.can_remove_point() is False


def test_can_remove_point_false_for_non_polyline() -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(0.0, 0.0), (10.0, 10.0)], dtype=np.float64),
    )
    assert shape.can_remove_point() is False


def test_remove_point_keeps_points_and_labels_in_sync() -> None:
    shape = _make_square_polygon()

    shape.remove_point(i=2)

    assert len(shape.points) == 3
    assert len(shape.point_labels) == 3
    assert shape.points[2] == pytest.approx((0.0, 10.0))


def test_remove_point_is_noop_at_polygon_minimum() -> None:
    shape = Shape(
        shape_type="polygon",
        points=np.array([(0.0, 0.0), (10.0, 0.0), (5.0, 10.0)], dtype=np.float64),
    )

    shape.remove_point(i=0)

    assert len(shape.points) == 3
    assert len(shape.point_labels) == 3


def test_remove_point_is_noop_for_non_polyline() -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(0.0, 0.0), (10.0, 10.0)], dtype=np.float64),
    )

    shape.remove_point(i=0)

    assert len(shape.points) == 2
    assert len(shape.point_labels) == 2


def test_remove_point_noop_logs_substituted_values() -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(0.0, 0.0), (10.0, 10.0)], dtype=np.float64),
    )
    messages: list[str] = []
    sink_id = logger.add(
        lambda m: messages.append(m.record["message"]), level="WARNING"
    )

    try:
        shape.remove_point(i=0)
    finally:
        logger.remove(sink_id)

    assert messages == [
        "Cannot remove point from: shape_type='rectangle', len(points)=2"
    ]


def test_move_vertex_replaces_only_target_point() -> None:
    shape = _make_square_polygon()

    shape.move_vertex(i=1, pos=(3.5, -1.25))

    assert len(shape.points) == 4
    assert shape.points[1] == pytest.approx((3.5, -1.25))
    assert shape.points[0] == pytest.approx((0.0, 0.0))
    assert shape.points[2] == pytest.approx((10.0, 10.0))
    assert shape.points[3] == pytest.approx((0.0, 10.0))


def test_translate_shifts_all_points_by_offset() -> None:
    shape = _make_square_polygon()

    shape.translate(offset=(2.5, -0.75))

    assert len(shape.points) == 4
    expected = [(2.5, -0.75), (12.5, -0.75), (12.5, 9.25), (2.5, 9.25)]
    for i, (x, y) in enumerate(expected):
        assert shape.points[i] == pytest.approx((x, y))


# Edge i is the segment from points[i-1] to points[i] (roll-by-1 convention),
# so for the square below edge 1 is the bottom and edge 0 is the left side.
@pytest.mark.parametrize(
    ("point", "expected_edge"),
    [
        ((5.0, 0.0), 1),
        ((0.0, 5.0), 0),
        ((10.0, 5.0), 2),
        ((5.0, 10.0), 3),
    ],
)
def test_nearest_edge_index_matches_edge_under_point(
    point: tuple[float, float], expected_edge: int
) -> None:
    shape = _make_square_polygon()

    index = _shape.nearest_edge_index(
        shape=shape, point=np.array(point), scale=1.0, epsilon=1.0
    )

    assert index == expected_edge


def test_nearest_edge_index_handles_zero_length_segment() -> None:
    # Duplicate consecutive points make one edge zero-length; the divide-by-zero
    # guard must keep the projection finite so a real edge still wins.
    shape = Shape(
        shape_type="polygon",
        points=np.array(
            [(0.0, 0.0), (0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)],
            dtype=np.float64,
        ),
    )

    index = _shape.nearest_edge_index(
        shape=shape, point=np.array([5.0, 0.0]), scale=1.0, epsilon=1.0
    )

    assert index == 2


def test_nearest_edge_index_returns_none_when_far() -> None:
    shape = _make_square_polygon()

    index = _shape.nearest_edge_index(
        shape=shape, point=np.array([5.0, 100.0]), scale=1.0, epsilon=1.0
    )

    assert index is None


def test_nearest_edge_index_returns_none_for_empty_shape() -> None:
    shape = Shape(shape_type="polygon")

    index = _shape.nearest_edge_index(
        shape=shape, point=np.array([0.0, 0.0]), scale=1.0, epsilon=10.0
    )

    assert index is None


def test_nearest_edge_index_ignores_phantom_closing_edge_for_linestrip() -> None:
    # A linestrip is open, so the segment from the last point back to the first
    # is never rendered and must not register as a hit. (5, 5) lies exactly on
    # that phantom diagonal but far from every drawn segment.
    shape = _make_open_linestrip()

    index = _shape.nearest_edge_index(
        shape=shape, point=np.array([5.0, 5.0]), scale=1.0, epsilon=2.0
    )

    assert index is None


def test_nearest_edge_index_matches_drawn_edge_for_linestrip() -> None:
    shape = _make_open_linestrip()

    index = _shape.nearest_edge_index(
        shape=shape, point=np.array([5.0, 0.0]), scale=1.0, epsilon=1.0
    )

    assert index == 1


def test_nearest_vertex_index_returns_nearest_within_epsilon() -> None:
    shape = _make_square_polygon()
    # vertex 1 is at (10.0, 0.0); probe 0.4 units away, within epsilon=1.0
    vertex_1 = shape.points[1]
    point_within_epsilon = vertex_1 + np.array([0.4, 0.0])

    index = _shape.nearest_vertex_index(
        shape=shape, point=point_within_epsilon, scale=1.0, epsilon=1.0
    )

    assert index == 1


def test_nearest_vertex_index_returns_none_when_far() -> None:
    shape = _make_square_polygon()

    index = _shape.nearest_vertex_index(
        shape=shape, point=np.array([5.0, 5.0]), scale=1.0, epsilon=1.0
    )

    assert index is None


def test_nearest_vertex_index_returns_none_for_empty_shape() -> None:
    shape = Shape(shape_type="polygon")

    index = _shape.nearest_vertex_index(
        shape=shape, point=np.array([0.0, 0.0]), scale=1.0, epsilon=10.0
    )

    assert index is None


# Rotation handles sit at the edge midpoints; handle i is the midpoint of the
# edge from points[i-1] to points[i] (roll-by-1 convention).
@pytest.mark.parametrize(
    ("index", "expected"),
    [
        (0, (0.0, 2.0)),
        (1, (5.0, 0.0)),
        (2, (10.0, 2.0)),
        (3, (5.0, 4.0)),
    ],
)
def test_get_rotation_handle_returns_edge_midpoints(
    index: int, expected: tuple[float, float]
) -> None:
    shape = _make_axis_aligned_oriented_rectangle()

    handle = _shape.get_rotation_handle(shape=shape, index=index)

    assert handle == pytest.approx(expected)


def test_get_rotation_handle_raises_for_non_oriented_rectangle() -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(0.0, 0.0), (10.0, 4.0)], dtype=np.float64),
    )

    with pytest.raises(ValueError, match="4-point oriented rectangles"):
        _shape.get_rotation_handle(shape=shape, index=0)


def test_nearest_rotation_point_index_returns_handle_within_epsilon() -> None:
    shape = _make_axis_aligned_oriented_rectangle()
    # handle 2 is the right-edge midpoint at (10, 2); probe just beside it.
    point = np.array([10.3, 2.0])

    index = _shape.nearest_rotation_point_index(
        shape=shape, point=point, scale=1.0, epsilon=1.0
    )

    assert index == 2


def test_nearest_rotation_point_index_returns_none_when_far() -> None:
    shape = _make_axis_aligned_oriented_rectangle()

    index = _shape.nearest_rotation_point_index(
        shape=shape, point=np.array([20.0, 20.0]), scale=1.0, epsilon=1.0
    )

    assert index is None


def test_nearest_rotation_point_index_returns_none_for_non_oriented_rectangle() -> None:
    shape = _make_square_polygon()

    index = _shape.nearest_rotation_point_index(
        shape=shape, point=np.array([5.0, 0.0]), scale=1.0, epsilon=10.0
    )

    assert index is None


def test_nearest_rotation_point_index_returns_none_for_empty_shape() -> None:
    shape = Shape(shape_type="oriented_rectangle")

    index = _shape.nearest_rotation_point_index(
        shape=shape, point=np.array([0.0, 0.0]), scale=1.0, epsilon=10.0
    )

    assert index is None


def test_oriented_rectangle_arrow_points_axis_aligned() -> None:
    shape = _make_axis_aligned_oriented_rectangle()

    arrow = _shape.oriented_rectangle_arrow_points(shape=shape)

    # index 1 is the tip; index 3 is the tail
    expected = np.array(
        [[6.1, -0.5], [10.0, 2.0], [6.1, 4.5], [0.0, 2.0]], dtype=np.float64
    )
    assert arrow == pytest.approx(expected)


def test_oriented_rectangle_arrow_points_rotates_tip_along_direction() -> None:
    # direction = points[1] - points[0] = (0, 10), so angle = pi/2: the tip
    # rotates from +x to +y. Center is (3, 5).
    shape = _make_oriented_rectangle([(5.0, 0.0), (5.0, 10.0), (1.0, 10.0), (1.0, 0.0)])

    arrow = _shape.oriented_rectangle_arrow_points(shape=shape)

    expected = np.array(
        [[5.5, 6.1], [3.0, 10.0], [0.5, 6.1], [3.0, 0.0]], dtype=np.float64
    )
    assert arrow == pytest.approx(expected)


def test_oriented_rectangle_arrow_points_for_non_cardinal_direction() -> None:
    # direction = (8, 6): a non-cardinal angle (cos 0.8, sin 0.6) so that
    # swapping the arctan2 arguments would change the result. Center is (2.5, 5).
    shape = _make_oriented_rectangle([(0.0, 0.0), (8.0, 6.0), (5.0, 10.0), (-3.0, 4.0)])

    arrow = _shape.oriented_rectangle_arrow_points(shape=shape)

    expected = np.array(
        [[4.88, 3.66], [6.5, 8.0], [1.88, 7.66], [-1.5, 2.0]], dtype=np.float64
    )
    assert arrow == pytest.approx(expected)
