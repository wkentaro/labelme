from __future__ import annotations

import dataclasses
import math
from typing import Final

import numpy as np
import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6.QtCore import QPointF
from PySide6.QtCore import QSize
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme._shape import ShapeType
from labelme.widgets.canvas import Canvas
from labelme.widgets.canvas import _compute_intersection_edges_image
from labelme.widgets.canvas import _compute_overscroll_slack
from labelme.widgets.canvas import _DraftShape
from labelme.widgets.canvas import _is_degenerate_draft
from labelme.widgets.canvas import _normalize_bbox_points
from labelme.widgets.canvas import _opposite_corner_in_parallelogram
from labelme.widgets.canvas import _project_oriented_rectangle_corners

_WIDTH: Final[int] = 100
_HEIGHT: Final[int] = 50


@pytest.fixture()
def canvas(qtbot: QtBot) -> Canvas:
    canvas = Canvas()
    canvas.pixmap = QtGui.QPixmap(_WIDTH, _HEIGHT)
    qtbot.addWidget(canvas)
    return canvas


def _make_oriented_rectangle(corners: list[tuple[float, float]]) -> Shape:
    return Shape(
        shape_type="oriented_rectangle",
        points=np.array(corners, dtype=np.float64),
        closed=True,
    )


@pytest.mark.gui
def test_drag_hovered_rotation_point_does_not_drift_on_repeated_drags(
    canvas: Canvas,
) -> None:
    # Rotate a shape through many small steps, then back to the start. Without
    # snapshot-based rotation (re-deriving each frame from captured anchors),
    # accumulated FP error from composed rotation matrices would leave residual
    # offset on the corners.
    original: list[tuple[float, float]] = [
        (30, 10),
        (70, 10),
        (70, 40),
        (30, 40),
    ]
    shape = _make_oriented_rectangle(corners=original)
    canvas.load_shapes(shapes=[shape])

    canvas._refresh_hover_state(pos=QPointF(50, 10))
    assert canvas._hovered_rotation == 1
    canvas._capture_rotation_anchors()

    center_x, center_y = 50.0, 25.0
    radius = 15.0
    steps = 200
    for step in range(1, steps + 1):
        theta = -math.pi / 2 + 2 * math.pi * step / steps
        pos = QPointF(
            center_x + radius * math.cos(theta), center_y + radius * math.sin(theta)
        )
        canvas._drag_hovered_rotation_point(pos=pos)

    for i, (x, y) in enumerate(original):
        assert canvas.shapes[0].points[i][0] == pytest.approx(x)
        assert canvas.shapes[0].points[i][1] == pytest.approx(y)


@pytest.mark.gui
def test_bounded_move_oriented_rectangle_vertex_clips_when_perpendicular_corner_outside(
    canvas: Canvas,
) -> None:
    # Tilted parallelogram chosen so dragging vertex 2 to (95, 5) keeps the
    # moving corner inside the pixmap but pushes the perpendicular adjacent
    # corner above y=0, isolating the perpendicular-clip branch.
    shape = _make_oriented_rectangle(corners=[(50, 30), (60, 35), (65, 25), (55, 20)])

    canvas._bounded_move_oriented_rectangle_vertex(
        shape=shape, vertex_index=2, pos=QPointF(95, 5)
    )

    expected = [(50, 30), (76, 43), (91, 13), (65, 0)]
    for i, (x, y) in enumerate(expected):
        assert (shape.points[i][0], shape.points[i][1]) == pytest.approx((x, y))


@pytest.mark.gui
def test_bounded_move_oriented_rectangle_vertex_clips_when_parallel_corner_outside(
    canvas: Canvas,
) -> None:
    # Same tilted shape; dragging vertex 2 to (95, 45) keeps the moving and
    # perpendicular adjacent inside but pushes the parallel adjacent corner
    # below y=50, isolating the parallel-clip branch.
    shape = _make_oriented_rectangle(corners=[(50, 30), (60, 35), (65, 25), (55, 20)])

    canvas._bounded_move_oriented_rectangle_vertex(
        shape=shape, vertex_index=2, pos=QPointF(95, 45)
    )

    expected = [(50, 30), (90, 50), (93, 44), (53, 24)]
    for i, (x, y) in enumerate(expected):
        assert (shape.points[i][0], shape.points[i][1]) == pytest.approx((x, y))


@pytest.mark.gui
def test_set_shape_visible_toggles_visibility(canvas: Canvas) -> None:
    # Visibility is canvas state keyed by object identity.
    shape = Shape(
        label="a",
        shape_type="rectangle",
        points=np.array([(0, 0), (10, 10)], dtype=np.float64),
        closed=True,
    )
    canvas.load_shapes([shape])

    assert canvas.shapes[0].visible is True

    canvas.set_shape_visible(canvas.shapes[0], False)
    assert canvas.shapes[0].visible is False

    canvas.set_shape_visible(canvas.shapes[0], True)
    assert canvas.shapes[0].visible is True


@pytest.mark.gui
def test_shape_visibility_survives_backup_and_restore(canvas: Canvas) -> None:
    # `visible` is the one ephemeral view flag kept on the Qt-free Shape so it
    # rides along the deepcopy-based undo/backup stack.
    shape = Shape(
        label="a",
        shape_type="rectangle",
        points=np.array([(0, 0), (10, 10)], dtype=np.float64),
        closed=True,
    )
    canvas.load_shapes([shape])

    canvas.set_shape_visible(canvas.shapes[0], False)
    canvas.backup_shapes()
    canvas.load_shapes([shape.copy()])
    assert canvas.shapes[0].visible is False

    canvas.restore_last_shape()
    assert canvas.shapes[0].visible is False


@pytest.mark.gui
@pytest.mark.parametrize("create_mode", ["ai_box_to_shape", "ai_points_to_shape"])
def test_finalize_with_empty_inference_resets_state_and_notifies(
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
    create_mode: str,
) -> None:
    # AI-Box / AI-Points inference can return no shapes (e.g. dedup suppresses
    # an overlapping detection). The empty branch of _finalize must reset the
    # in-progress drawing state so the edit-mode button becomes usable again
    # and notify the user that inference produced nothing.
    monkeypatch.setattr(canvas, "_shapes_from_ai_points", lambda **_: [])
    canvas.create_mode = create_mode
    # ai_box_to_shape normalizes the two bbox corners before delegating to the
    # (monkeypatched) inference call, so the in-progress shape needs 2 points.
    canvas._current = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(1, 1),
    )
    drawing_polygon_emissions: list[bool] = []
    inference_no_shapes_emissions: list[None] = []
    canvas.drawing_polygon.connect(drawing_polygon_emissions.append)
    canvas.inference_produced_no_shapes.connect(
        lambda: inference_no_shapes_emissions.append(None)
    )

    canvas._finalize()

    assert drawing_polygon_emissions == [False]
    assert len(inference_no_shapes_emissions) == 1
    assert canvas._current is None
    assert canvas.shapes == []


@pytest.mark.gui
def test_create_mode_switch_retypes_one_point_partial(canvas: Canvas) -> None:
    # Retype must update _current.shape_type and _line.shape_type, but must
    # NOT re-seed _line.points (which would alias both slots and break the
    # next extend click).
    canvas.create_mode = "rectangle"
    canvas._current = _DraftShape(
        shape_type="rectangle", points=(QPointF(10, 10),), point_labels=(1,)
    )
    canvas._line = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(10, 10), QPointF(50, 30)),
        point_labels=(1, 1),
        closed=True,
    )

    canvas.create_mode = "polygon"

    assert canvas._current is not None
    assert canvas._current.shape_type == "polygon"
    assert canvas._current.points == (QPointF(10, 10),)
    assert canvas._line.shape_type == "polygon"
    assert canvas._line.points == (QPointF(10, 10), QPointF(50, 30))
    assert canvas._line.point_labels == (1, 1)


@pytest.mark.gui
def test_create_mode_switch_cancels_multi_point_partial_with_new_mode_observable(
    canvas: Canvas,
) -> None:
    # Multi-point partial cancels, and listeners on drawing_polygon must
    # observe the new create_mode synchronously.
    canvas.create_mode = "polygon"
    canvas._current = _DraftShape(
        shape_type="polygon",
        points=(QPointF(10, 10), QPointF(20, 20)),
        point_labels=(1, 1),
    )
    emissions: list[bool] = []
    observed_modes: list[str] = []

    def listener(drawing: bool) -> None:
        emissions.append(drawing)
        observed_modes.append(canvas.create_mode)

    canvas.drawing_polygon.connect(listener)

    canvas.create_mode = "rectangle"

    assert canvas._current is None
    assert emissions == [False]
    assert observed_modes == ["rectangle"]


@pytest.mark.gui
def test_create_mode_switch_to_ai_target_cancels_one_point_partial(
    canvas: Canvas,
) -> None:
    # AI modes carry per-point labels, so a non-AI seed can't be
    # reinterpreted as an AI seed even with only 1 point.
    canvas.create_mode = "rectangle"
    canvas._current = _DraftShape(
        shape_type="rectangle", points=(QPointF(10, 10),), point_labels=(1,)
    )
    emissions: list[bool] = []
    canvas.drawing_polygon.connect(emissions.append)

    canvas.create_mode = "ai_box_to_shape"

    assert canvas._current is None
    assert emissions == [False]


@pytest.mark.gui
def test_create_mode_switch_preserves_seed_point_label(canvas: Canvas) -> None:
    # Retype must preserve _current.point_labels (a shift-click sets label=0).
    canvas.create_mode = "polygon"
    canvas._current = _DraftShape(
        shape_type="polygon", points=(QPointF(10, 10),), point_labels=(0,)
    )

    canvas.create_mode = "rectangle"

    assert canvas._current is not None
    assert canvas._current.point_labels == (0,)


@pytest.mark.gui
@pytest.mark.parametrize("to_mode", ["rectangle", "circle", "line"])
def test_extend_after_mode_switch_finalizes_at_last_cursor(
    canvas: Canvas, to_mode: str
) -> None:
    # After mode switch, the preserved [seed, last_cursor] _line drives
    # extend so finalize commits a non-degenerate shape.
    canvas.create_mode = "rectangle"
    canvas._current = _DraftShape(
        shape_type="rectangle", points=(QPointF(10, 10),), point_labels=(1,)
    )
    canvas._line = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(10, 10), QPointF(50, 30)),
        point_labels=(1, 1),
    )

    canvas.create_mode = to_mode

    event = QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonPress,
        QPointF(50, 30),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    canvas._extend_current_shape(current=canvas._current, event=event)

    assert canvas._current is None
    assert len(canvas.shapes) == 1
    assert canvas.shapes[0].shape_type == to_mode
    assert canvas.shapes[0].points[0][0] == pytest.approx(10)
    assert canvas.shapes[0].points[0][1] == pytest.approx(10)
    assert canvas.shapes[0].points[1][0] == pytest.approx(50)
    assert canvas.shapes[0].points[1][1] == pytest.approx(30)


@pytest.mark.gui
@pytest.mark.parametrize("to_mode", ["polygon", "linestrip", "oriented_rectangle"])
def test_extend_after_mode_switch_grows_partial_at_last_cursor(
    canvas: Canvas, to_mode: str
) -> None:
    # Non-finalizing modes grow at last_cursor; for oriented_rectangle the
    # locked first edge has non-zero length.
    canvas.create_mode = "rectangle"
    canvas._current = _DraftShape(
        shape_type="rectangle", points=(QPointF(10, 10),), point_labels=(1,)
    )
    canvas._line = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(10, 10), QPointF(50, 30)),
        point_labels=(1, 1),
    )

    canvas.create_mode = to_mode

    event = QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonPress,
        QPointF(50, 30),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    canvas._extend_current_shape(current=canvas._current, event=event)

    assert canvas.shapes == []
    assert canvas._current is not None
    if to_mode == "oriented_rectangle":
        assert canvas._current.points[0] == QPointF(10, 10)
        assert canvas._current.points[1] == QPointF(50, 30)
        assert canvas._current.points[0] != canvas._current.points[1]
    else:
        assert canvas._current.points == (QPointF(10, 10), QPointF(50, 30))


@pytest.mark.parametrize(
    ("shape_type", "points", "expected"),
    [
        pytest.param("polygon", [(0, 0), (1, 0), (2, 0)], False, id="polygon_valid"),
        pytest.param("polygon", [(0, 0), (1, 0)], True, id="polygon_two_points"),
        pytest.param("polygon", [(0, 0), (0, 0), (0, 0)], True, id="polygon_collapsed"),
        pytest.param("linestrip", [(0, 0), (1, 0)], False, id="linestrip_valid"),
        pytest.param("linestrip", [(0, 0)], True, id="linestrip_one_point"),
        pytest.param("linestrip", [(0, 0), (0, 0)], True, id="linestrip_collapsed"),
        pytest.param("rectangle", [(0, 0), (1, 1)], False, id="rectangle_valid"),
        pytest.param("rectangle", [(0, 0), (0, 1)], True, id="rectangle_zero_width"),
        pytest.param("rectangle", [(0, 0), (1, 0)], True, id="rectangle_zero_height"),
        pytest.param("rectangle", [(0, 0)], True, id="rectangle_one_point"),
        pytest.param("circle", [(0, 0), (1, 0)], False, id="circle_valid"),
        pytest.param("circle", [(0, 0), (0, 0)], True, id="circle_zero_radius"),
        pytest.param("line", [(0, 0), (1, 0)], False, id="line_valid"),
        pytest.param("line", [(0, 0), (0, 0)], True, id="line_zero_length"),
        pytest.param(
            "oriented_rectangle",
            [(0, 0), (1, 0), (1, 1), (0, 1)],
            False,
            id="oriented_rectangle_valid",
        ),
        pytest.param(
            "oriented_rectangle",
            [(0, 0), (0, 0), (0, 0), (0, 0)],
            True,
            id="oriented_rectangle_zero_first_edge",
        ),
        pytest.param(
            "oriented_rectangle",
            [(0, 0), (1, 0), (1, 0), (0, 0)],
            True,
            id="oriented_rectangle_zero_width",
        ),
    ],
)
def test_is_degenerate_draft(
    shape_type: ShapeType, points: list[tuple[float, float]], expected: bool
) -> None:
    draft = _DraftShape(
        shape_type=shape_type,
        points=tuple(QPointF(x, y) for x, y in points),
        point_labels=tuple(1 for _ in points),
    )
    assert _is_degenerate_draft(draft) is expected


@pytest.mark.gui
@pytest.mark.parametrize("shape_type", ["rectangle", "circle", "line"])
def test_finalize_rejects_degenerate_shape(
    canvas: Canvas, shape_type: ShapeType
) -> None:
    # Zero-area / zero-length shapes never enter canvas.shapes; the user gets
    # a clean cancel instead of a silent malformed annotation, and the rejection
    # is announced so the app can surface a status message.
    canvas.create_mode = shape_type
    canvas._current = _DraftShape(
        shape_type=shape_type,
        points=(QPointF(10, 10), QPointF(10, 10)),
        point_labels=(1, 1),
    )
    rejection_emissions: list[None] = []
    canvas.degenerate_shape_rejected.connect(lambda: rejection_emissions.append(None))

    canvas._finalize()

    assert canvas.shapes == []
    assert canvas._current is None
    assert len(rejection_emissions) == 1


@pytest.mark.gui
def test_finalize_rejects_polygon_with_fewer_than_three_distinct_points(
    canvas: Canvas,
) -> None:
    canvas.create_mode = "polygon"
    canvas._current = _DraftShape(
        shape_type="polygon",
        points=(QPointF(10, 10), QPointF(20, 20)),
        point_labels=(1, 1),
    )

    canvas._finalize()

    assert canvas.shapes == []
    assert canvas._current is None


def test_retype_draft_into_fresh_shape_type() -> None:
    # dataclasses.replace carries the points over to a distinct draft with the
    # new shape_type; _DraftShape is frozen, so the two share no mutable state.
    original = _DraftShape(
        shape_type="polygon",
        points=(QPointF(10, 10), QPointF(20, 20)),
        point_labels=(1, 1),
    )

    rebuilt = dataclasses.replace(original, shape_type="rectangle")

    assert rebuilt is not original
    assert rebuilt.shape_type == "rectangle"
    assert rebuilt.points == (QPointF(10, 10), QPointF(20, 20))
    assert rebuilt.point_labels == (1, 1)


_IMAGE_SIZE: Final[QSize] = QSize(100, 50)


@pytest.mark.parametrize(
    ("p1", "p2", "expected"),
    [
        pytest.param(
            QPointF(50, 25),
            QPointF(150, 25),
            QPointF(100, 25),
            id="interior_to_right_exits_right_edge",
        ),
        pytest.param(
            QPointF(50, 25),
            QPointF(50, -10),
            QPointF(50, 0),
            id="interior_to_top_exits_top_edge",
        ),
        pytest.param(
            QPointF(50, 25),
            QPointF(-10, 25),
            QPointF(0, 25),
            id="interior_to_left_exits_left_edge",
        ),
        pytest.param(
            QPointF(50, 25),
            QPointF(50, 80),
            QPointF(50, 50),
            id="interior_to_bottom_exits_bottom_edge",
        ),
        pytest.param(
            QPointF(0, 25),
            QPointF(-5, 25),
            QPointF(0, 25),
            id="on_left_edge_pushed_left_stays",
        ),
        pytest.param(
            QPointF(50, 0),
            QPointF(50, -5),
            QPointF(50, 0),
            id="on_top_edge_pushed_up_stays",
        ),
        pytest.param(
            QPointF(0, 25),
            QPointF(-5, 35),
            QPointF(0, 35),
            id="on_left_edge_pushed_left_and_down_slides_down_left_edge",
        ),
        pytest.param(
            QPointF(0, 0),
            QPointF(-5, -5),
            QPointF(0, 0),
            id="on_top_left_corner_pushed_diagonally_out_stays",
        ),
        pytest.param(
            QPointF(100, 50),
            QPointF(105, 55),
            QPointF(100, 50),
            id="on_bottom_right_corner_pushed_diagonally_out_stays",
        ),
    ],
)
def test_compute_intersection_edges_image(
    p1: QPointF, p2: QPointF, expected: QPointF
) -> None:
    assert (
        _compute_intersection_edges_image(p1=p1, p2=p2, image_size=_IMAGE_SIZE)
        == expected
    )


@pytest.mark.parametrize(
    ("p1", "p2"),
    [
        pytest.param(QPointF(10, 20), QPointF(30, 40), id="top_left_to_bottom_right"),
        pytest.param(QPointF(30, 40), QPointF(10, 20), id="bottom_right_to_top_left"),
        pytest.param(QPointF(30, 20), QPointF(10, 40), id="top_right_to_bottom_left"),
        pytest.param(QPointF(10, 40), QPointF(30, 20), id="bottom_left_to_top_right"),
    ],
)
def test_normalize_bbox_points_returns_top_left_and_bottom_right(
    p1: QPointF, p2: QPointF
) -> None:
    assert _normalize_bbox_points(bbox_points=[p1, p2]) == [
        QPointF(10, 20),
        QPointF(30, 40),
    ]


def test_normalize_bbox_points_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="Expected 2 points"):
        _normalize_bbox_points(bbox_points=[QPointF(0, 0)])


def test_opposite_corner_in_parallelogram_completes_axis_aligned_square() -> None:
    # Given three corners (0,0), (10,0), (0,10), the fourth opposite (0,0) is (10,10).
    assert _opposite_corner_in_parallelogram(
        opposite_to=QPointF(0, 0),
        neighbor1=QPointF(10, 0),
        neighbor2=QPointF(0, 10),
    ) == QPointF(10, 10)


def test_opposite_corner_in_parallelogram_completes_skewed_parallelogram() -> None:
    # Skewed: anchor (0,0), neighbors (10,0) and (3,5) -> opposite is (13,5).
    assert _opposite_corner_in_parallelogram(
        opposite_to=QPointF(0, 0),
        neighbor1=QPointF(10, 0),
        neighbor2=QPointF(3, 5),
    ) == QPointF(13, 5)


def test_project_oriented_rectangle_corners_axis_aligned() -> None:
    perp, para = _project_oriented_rectangle_corners(
        anchor=QPointF(0, 0),
        edge_axis=QPointF(10, 0),
        moving=QPointF(10, 4),
    )
    assert (perp.x(), perp.y()) == pytest.approx((0.0, 4.0))
    assert (para.x(), para.y()) == pytest.approx((10.0, 0.0))


def test_project_oriented_rectangle_corners_with_cursor_off_locked_edge() -> None:
    # Locked edge from (0,0) to (10,0); cursor at (15,4) projects perpendicular
    # to the edge axis at (0,4); para corner balances the parallelogram.
    perp, para = _project_oriented_rectangle_corners(
        anchor=QPointF(0, 0),
        edge_axis=QPointF(10, 0),
        moving=QPointF(15, 4),
    )
    assert (perp.x(), perp.y()) == pytest.approx((0.0, 4.0))
    assert (para.x(), para.y()) == pytest.approx((15.0, 0.0))


@pytest.mark.parametrize(
    ("scaled", "viewport", "expected"),
    [
        pytest.param(399, 400, 0, id="image_fits_below_threshold"),
        pytest.param(400, 400, 0, id="image_exactly_fills_viewport"),
        pytest.param(401, 400, 50, id="slight_overflow_floored_to_viewport_eighth"),
        pytest.param(450, 400, 50, id="overflow_at_floor_boundary"),
        pytest.param(500, 400, 100, id="ramp_grows_with_overflow_past_floor"),
        pytest.param(600, 400, 200, id="overflow_at_cap_boundary"),
        pytest.param(1000, 400, 200, id="large_overflow_capped_at_viewport_half"),
    ],
)
def test_compute_overscroll_slack(scaled: int, viewport: int, expected: int) -> None:
    assert _compute_overscroll_slack(scaled=scaled, viewport=viewport) == expected
