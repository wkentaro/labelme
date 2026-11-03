from __future__ import annotations

import dataclasses
import math
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import Final
from unittest.mock import Mock

import numpy as np
import osam
import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import QPointF
from PySide6.QtCore import QSize
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

import labelme
from labelme._automation import InferenceRequest
from labelme._automation._ai_assist import AiAssistProposal
from labelme._shape import Shape
from labelme._shape import ShapeType
from labelme._widgets._canvas import _CREATE_MODE_TO_SHAPE_TYPE
from labelme._widgets._canvas import Canvas
from labelme._widgets._canvas import _compute_intersection_edges_image
from labelme._widgets._canvas import _compute_shapes_bounds
from labelme._widgets._canvas import _draft_to_shape
from labelme._widgets._canvas import _DraftShape
from labelme._widgets._canvas import _is_degenerate_draft
from labelme._widgets._canvas import _is_out_of_image
from labelme._widgets._canvas import _normalize_bbox_points
from labelme._widgets._canvas import _opposite_corner_in_parallelogram
from labelme._widgets._canvas import _project_oriented_rectangle_corners
from labelme._widgets._canvas import _reproject_oriented_rectangle_corners
from labelme._widgets._canvas import _shape_to_draft
from labelme._widgets._canvas import _should_reselect_on_right_press
from labelme._widgets._canvas import _snap_cursor_pos_for_square
from labelme._widgets._shape_render import ShapeRenderContext

_WIDTH: Final[int] = 100
_HEIGHT: Final[int] = 50


class _InlineOsamWorker(QtCore.QObject):
    # Answers each submit before returning, as a worker that fails to start does.
    finished = QtCore.Signal(object, object)
    failed = QtCore.Signal(object, str)
    requests: list[InferenceRequest]
    annotations: list[osam.types.Annotation]
    paused: bool

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[InferenceRequest] = []
        self.annotations: list[osam.types.Annotation] = []
        self.paused = False
        self._held: list[object] = []

    def submit(
        self, *, channel: object, job: object, request: InferenceRequest
    ) -> None:
        del channel
        self.requests.append(request)
        if self.paused:
            self._held.append(job)
        else:
            self.finished.emit(job, self.annotations)

    def resume(self) -> None:
        self.paused = False
        held, self._held = self._held, []
        for job in held:
            self.finished.emit(job, self.annotations)


@pytest.fixture()
def canvas(*, qtbot: QtBot) -> Canvas:
    canvas = Canvas()
    canvas.pixmap = QtGui.QPixmap(_WIDTH, _HEIGHT)
    canvas.set_osam_worker(_InlineOsamWorker())  # ty: ignore[invalid-argument-type]
    qtbot.addWidget(canvas)
    return canvas


def _worker(canvas: Canvas, /) -> _InlineOsamWorker:
    worker = canvas._osam_worker
    assert isinstance(worker, _InlineOsamWorker)
    return worker


@pytest.mark.gui
def test_setting_scale_resizes_canvas(*, canvas: Canvas) -> None:
    canvas.scale = 2.0
    assert canvas.size() == QSize(2 * _WIDTH, 2 * _HEIGHT)


@pytest.mark.gui
def test_setting_unchanged_scale_still_resizes_canvas(*, canvas: Canvas) -> None:
    # A new image changes the size hint while the zoom stays put; assigning
    # the same scale is how the canvas is told to take the new size.
    canvas.scale = 1.0
    canvas.pixmap = QtGui.QPixmap(2 * _WIDTH, 2 * _HEIGHT)
    canvas.scale = 1.0
    assert canvas.size() == QSize(2 * _WIDTH, 2 * _HEIGHT)


@pytest.mark.gui
@pytest.mark.parametrize(
    ("scale", "area", "pan", "widget_point", "image_point"),
    [
        (2.0, QSize(500, 300), QPointF(17, -11), QPointF(207, 149), QPointF(20, 30)),
        (2.0, QSize(80, 40), QPointF(-7, 3), QPointF(33, 63), QPointF(20, 30)),
        (1.25, QSize(160, 70), QPointF(5.5, -2.25), QPointF(48, 39), QPointF(20, 30)),
        (0.5, QSize(100, 50), QPointF(), QPointF(-20, -30), QPointF(-90, -85)),
    ],
)
def test_transform_widget_point_to_image(
    *,
    canvas: Canvas,
    scale: float,
    area: QSize,
    pan: QPointF,
    widget_point: QPointF,
    image_point: QPointF,
) -> None:
    canvas.scale = scale
    canvas.resize(area)
    canvas._view_offset = pan

    actual = canvas.transform_widget_point_to_image(widget_point)

    assert actual.x() == pytest.approx(image_point.x())
    assert actual.y() == pytest.approx(image_point.y())


@pytest.mark.gui
def test_ai_job_passes_rgb_image_to_model(*, canvas: Canvas) -> None:
    canvas.pixmap.fill(QtGui.QColor(10, 20, 30))

    canvas._submit_ai_job(
        channel="preview", prompt_kind="points", points=[], point_labels=[]
    )

    (request,) = _worker(canvas).requests
    assert request.image is not None
    np.testing.assert_array_equal(request.image[0, 0], [10, 20, 30])


def _make_oriented_rectangle(*, corners: list[tuple[float, float]]) -> Shape:
    return Shape(
        shape_type="oriented_rectangle",
        points=np.array(corners, dtype=np.float64),
        closed=True,
    )


@pytest.mark.gui
def test_drag_hovered_rotation_point_does_not_drift_on_repeated_drags(
    *,
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
    *,
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
    *,
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
def test_bounded_move_vertex_clamps_to_image_by_default(*, canvas: Canvas) -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(10, 10), (50, 40)], dtype=np.float64),
        closed=True,
    )

    canvas._bounded_move_vertex(
        shape=shape, vertex_index=1, pos=QPointF(150, 80), is_shift_pressed=False
    )

    x, y = shape.points[1]
    assert (x, y) == pytest.approx((75, 50))


@pytest.mark.gui
def test_bounded_move_vertex_keeps_out_of_bounds_when_enabled(
    *, canvas: Canvas
) -> None:
    canvas.set_allow_out_of_bounds_points(value=True)
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(10, 10), (50, 40)], dtype=np.float64),
        closed=True,
    )

    canvas._bounded_move_vertex(
        shape=shape, vertex_index=1, pos=QPointF(150, 80), is_shift_pressed=False
    )

    assert (shape.points[1][0], shape.points[1][1]) == pytest.approx((150, 80))


@pytest.mark.gui
def test_reproject_oriented_rectangle_skips_clip_when_out_of_bounds_allowed() -> None:
    # Same tilted shape and drag as the perpendicular-clip test above; with the
    # flag on, the moving corner stays at the raw cursor instead of being clipped.
    corners = tuple(
        QPointF(*point) for point in [(50, 30), (60, 35), (65, 25), (55, 20)]
    )

    new_corners = _reproject_oriented_rectangle_corners(
        corners=corners,
        vertex_index=2,
        pos=QPointF(95, 5),
        image_size=QSize(_WIDTH, _HEIGHT),
        allow_out_of_bounds=True,
    )

    # The moving corner lands on the raw cursor, the anchor is fixed, and the
    # shape stays a parallelogram (opposite corners share a midpoint) -- i.e. no
    # corner was pulled back to the image edge.
    assert (new_corners[2].x(), new_corners[2].y()) == pytest.approx((95, 5))
    assert (new_corners[0].x(), new_corners[0].y()) == pytest.approx((50, 30))
    assert new_corners[0].x() + new_corners[2].x() == pytest.approx(
        new_corners[1].x() + new_corners[3].x()
    )
    assert new_corners[0].y() + new_corners[2].y() == pytest.approx(
        new_corners[1].y() + new_corners[3].y()
    )


@pytest.mark.parametrize("point_first", [True, False])
@pytest.mark.parametrize(
    ("position", "expected"),
    [
        ((10, 10), QtCore.QRectF(10, 10, 60, 60)),
        ((90, 90), QtCore.QRectF(50, 50, 40, 40)),
    ],
)
def test_compute_shapes_bounds_includes_point(
    *, point_first: bool, position: tuple[int, int], expected: QtCore.QRectF
) -> None:
    point = Shape(shape_type="point", points=np.array([position], dtype=np.float64))
    rectangle = Shape(
        shape_type="rectangle",
        points=np.array([(50, 50), (70, 70)], dtype=np.float64),
        closed=True,
    )
    shapes = [point, rectangle] if point_first else [rectangle, point]

    assert _compute_shapes_bounds(shapes=shapes) == expected


@pytest.mark.gui
def test_drag_shapes_keeps_point_in_group_inside_image(*, canvas: Canvas) -> None:
    point = Shape(shape_type="point", points=np.array([(10, 10)], dtype=np.float64))
    rectangle = Shape(
        shape_type="rectangle",
        points=np.array([(50, 20), (70, 40)], dtype=np.float64),
        closed=True,
    )
    shapes = [point, rectangle]
    canvas._prev_point = QPointF(60, 30)
    canvas._record_drag_anchor(shapes=shapes, click=canvas._prev_point)

    canvas._drag_shapes(shapes=shapes, cursor=QPointF(0, 30), constrain_cursor=True)

    assert canvas._prev_point == QPointF(50, 30)
    np.testing.assert_allclose(point.points, [(0, 10)])
    np.testing.assert_allclose(rectangle.points, [(40, 20), (60, 40)])


@pytest.mark.gui
def test_drag_shapes_blocked_off_image_by_default(*, canvas: Canvas) -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(40, 20), (60, 30)], dtype=np.float64),
        closed=True,
    )
    canvas._prev_point = QPointF(50, 25)
    canvas._record_drag_anchor(shapes=[shape], click=canvas._prev_point)

    canvas._drag_shapes(shapes=[shape], cursor=QPointF(150, 80), constrain_cursor=True)

    assert canvas._prev_point == QPointF(50, 25)
    assert (shape.points[0][0], shape.points[0][1]) == pytest.approx((40, 20))
    assert (shape.points[1][0], shape.points[1][1]) == pytest.approx((60, 30))


@pytest.mark.gui
def test_drag_shapes_keeps_out_of_bounds_when_enabled(*, canvas: Canvas) -> None:
    canvas.set_allow_out_of_bounds_points(value=True)
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(40, 20), (60, 30)], dtype=np.float64),
        closed=True,
    )
    canvas._prev_point = QPointF(50, 25)
    canvas._record_drag_anchor(shapes=[shape], click=canvas._prev_point)

    canvas._drag_shapes(shapes=[shape], cursor=QPointF(150, 80), constrain_cursor=True)

    assert canvas._prev_point == QPointF(150, 80)
    assert (shape.points[0][0], shape.points[0][1]) == pytest.approx((140, 75))
    assert (shape.points[1][0], shape.points[1][1]) == pytest.approx((160, 85))


@pytest.mark.gui
def test_drag_shapes_preserves_fractional_noop_and_round_trip(
    *, canvas: Canvas
) -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array(
            [
                (8.44414798007001, 2.8813233909973786),
                (12.795045643540696, 7.5153405275769956),
            ]
        ),
    )
    original = shape.points.copy()
    click = QPointF(10.619596811805353, 5.198331959287187)
    canvas._prev_point = QPointF(click)
    canvas._record_drag_anchor(shapes=[shape], click=click)
    cursor = QPointF(48.87823985103782, 6.985739658056511)

    canvas._drag_shapes(shapes=[shape], cursor=cursor, constrain_cursor=True)
    placed = shape.points
    previous_cursor = QPointF(canvas._prev_point)
    canvas._drag_shapes(shapes=[shape], cursor=cursor, constrain_cursor=True)

    assert shape.points is placed
    assert canvas._prev_point == previous_cursor
    canvas._drag_shapes(shapes=[shape], cursor=click, constrain_cursor=True)
    np.testing.assert_array_equal(shape.points, original)


@pytest.mark.gui
@pytest.mark.parametrize("change", ["policy", "image_size"])
def test_drag_shapes_retries_clamped_request_after_limits_change(
    *, canvas: Canvas, change: str
) -> None:
    shape = Shape(shape_type="rectangle", points=np.array([(20, 20), (40, 40)]))
    canvas._prev_point = QPointF(30, 30)
    canvas._record_drag_anchor(shapes=[shape], click=canvas._prev_point)
    canvas._drag_shapes(shapes=[shape], cursor=QPointF(200, 30), constrain_cursor=False)
    np.testing.assert_array_equal(shape.points, [(80, 20), (100, 40)])

    if change == "policy":
        canvas.set_allow_out_of_bounds_points(value=True)
    else:
        canvas.pixmap = QtGui.QPixmap(300, 50)
    canvas._drag_shapes(shapes=[shape], cursor=QPointF(200, 30), constrain_cursor=False)

    np.testing.assert_array_equal(shape.points, [(190, 20), (210, 40)])


@pytest.mark.gui
def test_drag_shapes_rebases_after_edit_preview_and_cursor_reset(
    *, canvas: Canvas
) -> None:
    shape = Shape(points=np.array([(20, 20), (40, 20), (30, 30), (20, 40)]))
    canvas._prev_point = QPointF(30, 30)
    canvas._record_drag_anchor(shapes=[shape], click=canvas._prev_point)
    canvas._drag_shapes(shapes=[shape], cursor=QPointF(40, 30), constrain_cursor=True)

    shape.move_vertex(i=2, pos=(46, 36))
    edited = shape.points
    canvas._drag_shapes(shapes=[shape], cursor=QPointF(40, 30), constrain_cursor=True)
    assert shape.points is edited
    preview = shape.copy()
    canvas._drag_shapes(shapes=[preview], cursor=QPointF(45, 30), constrain_cursor=True)
    np.testing.assert_array_equal(
        shape.points, [(30, 20), (50, 20), (46, 36), (30, 40)]
    )
    np.testing.assert_array_equal(
        preview.points, [(35, 20), (55, 20), (51, 36), (35, 40)]
    )
    canvas.selected_shapes = [preview]
    canvas._prev_point = QPointF(60, 60)

    canvas._move_by_keyboard(offset=QPointF(0, 5))

    np.testing.assert_array_equal(
        preview.points, [(35, 25), (55, 25), (51, 41), (35, 45)]
    )
    assert canvas._prev_point == QPointF(60, 65)


@pytest.mark.gui
@pytest.mark.parametrize(
    "reset", ["image", "shapes", "empty_capture", "canvas", "focus"]
)
def test_drag_anchor_releases_captured_shapes_on_reset(
    *, canvas: Canvas, reset: str
) -> None:
    shape = Shape(shape_type="rectangle", points=np.array([(20, 20), (40, 40)]))
    reference = weakref.ref(shape)
    canvas._record_drag_anchor(shapes=[shape], click=QPointF(30, 30))
    del shape

    if reset == "image":
        canvas.load_pixmap(pixmap=QtGui.QPixmap(100, 50), clear_shapes=False)
    elif reset == "shapes":
        canvas.load_shapes(shapes=[])
    elif reset == "empty_capture":
        canvas._record_drag_anchor(shapes=[], click=QPointF())
    elif reset == "focus":
        canvas.focusOutEvent(QtGui.QFocusEvent(QtCore.QEvent.Type.FocusOut))
    else:
        canvas.reset_state()

    assert reference() is None


@pytest.mark.gui
@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        pytest.param(QPointF(-5, 0), [(35, 20), (55, 30)], id="left"),
        pytest.param(QPointF(0, -5), [(40, 15), (60, 25)], id="up"),
    ],
)
def test_move_by_keyboard_moves_clickless_selection(
    *, canvas: Canvas, offset: QPointF, expected: list[tuple[float, float]]
) -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(40, 20), (60, 30)], dtype=np.float64),
        closed=True,
    )
    canvas.shapes = [shape]
    canvas.selected_shapes = [shape]

    canvas._move_by_keyboard(offset=offset)

    np.testing.assert_allclose(shape.points, expected)


@pytest.mark.gui
def test_move_by_keyboard_clamps_clickless_selection_to_image(
    *, canvas: Canvas
) -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(85, 20), (95, 30)], dtype=np.float64),
        closed=True,
    )
    canvas.shapes = [shape]
    canvas.selected_shapes = [shape]

    for _ in range(3):
        canvas._move_by_keyboard(offset=QPointF(5, 0))

    np.testing.assert_allclose(shape.points, [(90, 20), (100, 30)])


@pytest.mark.gui
def test_move_by_keyboard_ignores_stale_mouse_position(*, canvas: Canvas) -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(40, 20), (60, 30)], dtype=np.float64),
        closed=True,
    )
    canvas.load_pixmap(pixmap=QtGui.QPixmap(200, 100))
    canvas._prev_point = QPointF(150, 80)
    canvas.load_pixmap(pixmap=QtGui.QPixmap(_WIDTH, _HEIGHT))
    canvas.shapes = [shape]
    canvas.selected_shapes = [shape]

    canvas._move_by_keyboard(offset=QPointF(5, 0))

    np.testing.assert_allclose(shape.points, [(45, 20), (65, 30)])


@pytest.mark.gui
def test_move_by_keyboard_rebuilds_mismatched_drag_anchor(*, canvas: Canvas) -> None:
    old_shape = Shape(
        shape_type="rectangle",
        points=np.array([(40, 20), (60, 30)], dtype=np.float64),
        closed=True,
    )
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(90, 20), (100, 30)], dtype=np.float64),
        closed=True,
    )
    canvas._prev_point = QPointF(50, 25)
    canvas.selected_shapes = [old_shape]
    canvas._record_drag_anchor(shapes=[old_shape], click=canvas._prev_point)
    canvas.shapes = [shape]
    canvas.selected_shapes = [shape]

    canvas._move_by_keyboard(offset=QPointF(5, 0))

    np.testing.assert_allclose(shape.points, [(90, 20), (100, 30)])


@pytest.mark.gui
@pytest.mark.parametrize(
    ("points", "click", "offset", "expected"),
    [
        pytest.param(
            [(-30, 20), (130, 30)],
            QPointF(50, 25),
            QPointF(5, 0),
            [(-25, 20), (135, 30)],
            id="too_wide_dragged_right",
        ),
        pytest.param(
            [(-30, 20), (130, 30)],
            QPointF(50, 25),
            QPointF(-5, 0),
            [(-35, 20), (125, 30)],
            id="too_wide_dragged_left",
        ),
        pytest.param(
            [(40, -15), (60, 65)],
            QPointF(50, 25),
            QPointF(0, 5),
            [(40, -10), (60, 70)],
            id="too_tall_dragged_down",
        ),
        pytest.param(
            [(40, -15), (60, 65)],
            QPointF(50, 25),
            QPointF(0, -5),
            [(40, -20), (60, 60)],
            id="too_tall_dragged_up",
        ),
        pytest.param(
            [(10, 20), (170, 30)],
            QPointF(50, 25),
            QPointF(-5, 0),
            [(5, 20), (165, 30)],
            id="beyond_right_bound_dragged_left",
        ),
        pytest.param(
            [(-70, 20), (90, 30)],
            QPointF(50, 25),
            QPointF(5, 0),
            [(-65, 20), (95, 30)],
            id="beyond_left_bound_dragged_right",
        ),
    ],
)
def test_drag_shapes_moves_oversized_shape_in_requested_direction(
    *,
    canvas: Canvas,
    points: list[tuple[float, float]],
    click: QPointF,
    offset: QPointF,
    expected: list[tuple[float, float]],
) -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array(points, dtype=np.float64),
        closed=True,
    )
    canvas.selected_shapes = [shape]
    canvas._prev_point = click
    canvas._record_drag_anchor(shapes=[shape], click=canvas._prev_point)

    canvas._drag_shapes(shapes=[shape], cursor=click + offset, constrain_cursor=True)

    np.testing.assert_allclose(shape.points, expected)


@pytest.mark.gui
@pytest.mark.parametrize(
    ("points", "offset"),
    [
        pytest.param([(-60, 20), (100, 30)], QPointF(-5, 0), id="left"),
        pytest.param([(0, 20), (160, 30)], QPointF(5, 0), id="right"),
        pytest.param([(40, -30), (60, 50)], QPointF(0, -5), id="top"),
        pytest.param([(40, 0), (60, 80)], QPointF(0, 5), id="bottom"),
        pytest.param([(10, 20), (170, 30)], QPointF(5, 0), id="beyond_right"),
        pytest.param([(-70, 20), (90, 30)], QPointF(-5, 0), id="beyond_left"),
    ],
)
def test_drag_shapes_stops_oversized_shape_at_symmetric_bound(
    *, canvas: Canvas, points: list[tuple[float, float]], offset: QPointF
) -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array(points, dtype=np.float64),
        closed=True,
    )
    original = shape.points.copy()
    canvas.selected_shapes = [shape]
    canvas._prev_point = QPointF(50, 25)
    canvas._record_drag_anchor(shapes=[shape], click=canvas._prev_point)

    canvas._drag_shapes(
        shapes=[shape],
        cursor=canvas._prev_point + offset,
        constrain_cursor=True,
    )

    assert canvas._prev_point == QPointF(50, 25)
    np.testing.assert_allclose(shape.points, original)


@pytest.mark.gui
def test_drag_shapes_preserves_orthogonal_out_of_bounds_position(
    *,
    canvas: Canvas,
) -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(40, 60), (60, 70)], dtype=np.float64),
        closed=True,
    )
    canvas.selected_shapes = [shape]
    canvas._prev_point = QPointF(50, 65)
    canvas._record_drag_anchor(shapes=[shape], click=canvas._prev_point)

    canvas._drag_shapes(
        shapes=[shape],
        cursor=canvas._prev_point + QPointF(5, 0),
        constrain_cursor=False,
    )

    np.testing.assert_allclose(shape.points, [(45, 60), (65, 70)])


@pytest.mark.gui
def test_should_draw_crosshair_off_image_when_out_of_bounds_allowed(
    *,
    canvas: Canvas,
) -> None:
    canvas.set_allow_out_of_bounds_points(value=True)
    canvas._crosshair[canvas._create_mode] = True
    canvas.set_editing(value=False)

    assert canvas._should_draw_crosshair(cursor=QPointF(_WIDTH + 20, _HEIGHT + 20))


@pytest.mark.gui
def test_set_shape_visible_toggles_visibility(*, canvas: Canvas) -> None:
    # Visibility is canvas state keyed by object identity.
    shape = Shape(
        label="a",
        shape_type="rectangle",
        points=np.array([(0, 0), (10, 10)], dtype=np.float64),
        closed=True,
    )
    canvas.load_shapes(shapes=[shape])

    assert canvas.shapes[0].visible is True

    canvas.set_shape_visible(shape=canvas.shapes[0], value=False)
    assert canvas.shapes[0].visible is False

    canvas.set_shape_visible(shape=canvas.shapes[0], value=True)
    assert canvas.shapes[0].visible is True


@pytest.mark.gui
def test_shape_visibility_survives_backup_and_restore(*, canvas: Canvas) -> None:
    # `visible` is the one ephemeral view flag kept on the Qt-free Shape so it
    # rides along the deepcopy-based undo/backup stack.
    shape = Shape(
        label="a",
        shape_type="rectangle",
        points=np.array([(0, 0), (10, 10)], dtype=np.float64),
        closed=True,
    )
    canvas.load_shapes(shapes=[shape])

    canvas.set_shape_visible(shape=canvas.shapes[0], value=False)
    canvas.backup_shapes()
    canvas.load_shapes(shapes=[shape.copy()])
    assert canvas.shapes[0].visible is False

    canvas.restore_last_shape()
    assert canvas.shapes[0].visible is False


def _make_rectangle(*, label: str | None) -> Shape:
    return Shape(
        label=label,
        shape_type="rectangle",
        points=np.array([(0, 0), (10, 10)], dtype=np.float64),
        closed=True,
    )


@pytest.mark.gui
def test_set_last_label_applies_only_to_trailing_unlabeled_run(
    *,
    canvas: Canvas,
) -> None:
    # After the label dialog is accepted, _app labels the batch of just-drawn
    # shapes via set_last_label. Those are the trailing run of still-unlabeled
    # shapes; the backward scan must stop at the nearest labeled shape, leaving
    # both it and any unlabeled shape before it untouched.
    stale = _make_rectangle(label=None)
    labeled = _make_rectangle(label="old")
    fresh_a = _make_rectangle(label=None)
    fresh_b = _make_rectangle(label=None)
    canvas.load_shapes(shapes=[stale, labeled, fresh_a, fresh_b])

    updated = canvas.set_last_label(text="new", flags={"occluded": True})

    assert updated == [fresh_a, fresh_b]
    assert stale.label is None
    assert labeled.label == "old"
    assert fresh_a.label == "new"
    assert fresh_b.label == "new"
    assert fresh_a.flags == {"occluded": True}
    assert fresh_b.flags == {"occluded": True}


@pytest.mark.gui
def test_set_last_label_rejects_empty_text(*, canvas: Canvas) -> None:
    with pytest.raises(ValueError, match="text must not be empty"):
        canvas.set_last_label(text="", flags={})


@pytest.mark.gui
def test_finalize_with_empty_inference_resets_state_and_notifies(
    *, canvas: Canvas, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        canvas,
        "_propose_ai_shapes",
        lambda **_: AiAssistProposal(
            new_shapes=[],
            matching_existing_shapes=[],
        ),
    )
    canvas.create_mode = "ai_segment"
    canvas._current = _DraftShape(
        shape_type="points",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(2, 3),
    )
    busy_emissions: list[bool] = []
    inference_no_shapes_emissions: list[None] = []
    canvas.busy_changed.connect(lambda: busy_emissions.append(canvas.is_busy))
    canvas.inference_produced_no_shapes.connect(
        lambda: inference_no_shapes_emissions.append(None)
    )

    canvas._finalize()

    assert busy_emissions[-1:] == [False]
    assert len(inference_no_shapes_emissions) == 1
    assert canvas._current is None
    assert canvas.shapes == []


@pytest.mark.gui
def test_existing_shape_suppression_is_disabled_by_default(
    *,
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _make_rectangle(label="existing")
    inferred = Shape(
        shape_type="rectangle",
        points=np.array([(20, 20), (30, 30)], dtype=np.float64),
        closed=True,
    )
    canvas.load_shapes(shapes=[existing])

    def propose_shapes(
        *, existing_shapes: list[Shape], **_: object
    ) -> AiAssistProposal:
        if existing_shapes:
            return AiAssistProposal(
                new_shapes=[],
                matching_existing_shapes=[existing],
            )
        return AiAssistProposal(
            new_shapes=[inferred],
            matching_existing_shapes=[],
        )

    monkeypatch.setattr(canvas._ai_assist_session, "propose_shapes", propose_shapes)
    canvas.create_mode = "ai_segment"
    canvas._current = _DraftShape(
        shape_type="points",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(2, 3),
    )

    canvas._finalize()

    assert canvas.shapes == [existing, inferred]


@pytest.mark.gui
@pytest.mark.parametrize(
    ("allow_out_of_bounds", "expected_image_size"),
    [(False, (_WIDTH, _HEIGHT)), (True, None)],
)
def test_ai_proposal_uses_out_of_bounds_setting(
    *,
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
    allow_out_of_bounds: bool,
    expected_image_size: tuple[int, int] | None,
) -> None:
    propose_shapes = Mock(
        return_value=AiAssistProposal(new_shapes=[], matching_existing_shapes=[])
    )
    monkeypatch.setattr(canvas._ai_assist_session, "propose_shapes", propose_shapes)
    canvas.set_allow_out_of_bounds_points(value=allow_out_of_bounds)

    canvas._submit_ai_job(
        channel="preview",
        prompt_kind="points",
        points=[QPointF(1, 1)],
        point_labels=[1],
    )

    assert propose_shapes.call_args.kwargs["image_size"] == expected_image_size


@pytest.mark.gui
@pytest.mark.parametrize(
    "change_setting",
    [
        pytest.param(
            lambda canvas: canvas.set_ai_model_name(model_name="efficientsam:10m"),
            id="model",
        ),
        pytest.param(
            lambda canvas: canvas.set_ai_output_format("rectangle"),
            id="output-format",
        ),
        pytest.param(
            lambda canvas: canvas.set_ai_existing_shape_suppression(enabled=True),
            id="existing-shape-suppression",
        ),
    ],
)
def test_changing_ai_assist_setting_clears_highlights(
    *,
    canvas: Canvas,
    change_setting: Callable[[Canvas], None],
) -> None:
    existing = _make_rectangle(label="existing")
    canvas._set_ai_existing_shape_highlights(shapes=[existing])

    change_setting(canvas)

    assert canvas._ai_existing_shape_highlights == []


@pytest.mark.gui
def test_changing_polygon_detail_requests_preview_repaint(
    *,
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = Mock()
    monkeypatch.setattr(canvas, "update", update)

    canvas.set_ai_polygon_detail(detail=40)

    update.assert_called_once_with()


@pytest.mark.gui
def test_delete_shape_clears_highlights(*, canvas: Canvas) -> None:
    existing = _make_rectangle(label="existing")
    canvas.load_shapes(shapes=[existing])
    canvas._set_ai_existing_shape_highlights(shapes=[existing])

    canvas.delete_shape(shape=existing)

    assert canvas._ai_existing_shape_highlights == []


@pytest.mark.gui
def test_delete_selected_clears_highlights(*, canvas: Canvas) -> None:
    existing = _make_rectangle(label="existing")
    canvas.load_shapes(shapes=[existing])
    canvas.selected_shapes.append(existing)
    canvas._set_ai_existing_shape_highlights(shapes=[existing])

    canvas.delete_selected()

    assert canvas._ai_existing_shape_highlights == []


@dataclasses.dataclass
class _AiExistingShapeHighlightHarness:
    canvas: Canvas
    existing: Shape
    new_shape_emissions: list[None]
    no_shapes_emissions: list[None]


@pytest.fixture()
def ai_existing_shape_highlight_harness(
    *,
    canvas: Canvas,
    qtbot: QtBot,
) -> _AiExistingShapeHighlightHarness:
    canvas.pixmap.fill(Qt.GlobalColor.black)
    existing = Shape(
        label="existing",
        shape_type="rectangle",
        points=np.array([[20, 10], [60, 40]], dtype=np.float64),
        visible=False,
    )
    canvas.load_shapes(shapes=[existing])
    canvas.set_ai_existing_shape_suppression(enabled=True)
    canvas.create_mode = "ai_segment"
    canvas.set_editing(value=False)
    canvas._ai_prompt_hint_due = False  # The prompts below skip the press.
    canvas._current = _DraftShape(
        shape_type="points",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(2, 3),
    )
    new_shape_emissions: list[None] = []
    no_shapes_emissions: list[None] = []
    canvas.new_shape.connect(lambda: new_shape_emissions.append(None))
    canvas.inference_produced_no_shapes.connect(
        lambda: no_shapes_emissions.append(None)
    )
    canvas.resize(_WIDTH, _HEIGHT)
    with qtbot.waitExposed(canvas):
        canvas.show()
    return _AiExistingShapeHighlightHarness(
        canvas=canvas,
        existing=existing,
        new_shape_emissions=new_shape_emissions,
        no_shapes_emissions=no_shapes_emissions,
    )


@pytest.mark.gui
@pytest.mark.parametrize("clear_action", ["edit", "pointer", "wheel", "key"])
def test_finalize_existing_only_inference_highlights_hidden_shape(
    *,
    ai_existing_shape_highlight_harness: _AiExistingShapeHighlightHarness,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    clear_action: str,
) -> None:
    harness = ai_existing_shape_highlight_harness
    canvas = harness.canvas

    def propose_shapes(
        *, existing_shapes: list[Shape], **_: object
    ) -> AiAssistProposal:
        assert existing_shapes == [harness.existing]
        return AiAssistProposal(
            new_shapes=[],
            matching_existing_shapes=[harness.existing],
        )

    monkeypatch.setattr(
        canvas._ai_assist_session,
        "propose_shapes",
        propose_shapes,
    )

    canvas._finalize()

    assert canvas.shapes == [harness.existing]
    assert canvas._current is None
    assert harness.new_shape_emissions == []
    assert harness.no_shapes_emissions == []
    highlight = canvas.grab().toImage().pixelColor(30, 20)
    assert highlight.red() > highlight.green() > highlight.blue()

    if clear_action == "edit":
        canvas.set_editing()
    elif clear_action == "pointer":
        qtbot.mouseClick(
            canvas,
            Qt.MouseButton.RightButton,
            pos=QtCore.QPoint(80, 20),
        )
    elif clear_action == "key":
        qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    else:
        canvas.wheelEvent(
            QtGui.QWheelEvent(
                QPointF(80, 20),
                QPointF(80, 20),
                QtCore.QPoint(),
                QtCore.QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,  # noqa: FBT003 -- QWheelEvent takes inverted positionally
            )
        )

    cleared = canvas.grab().toImage().pixelColor(30, 20)
    assert cleared == QtGui.QColor(Qt.GlobalColor.black)


@pytest.mark.gui
def test_finalize_mixed_inference_adds_new_and_highlights_existing(
    *,
    ai_existing_shape_highlight_harness: _AiExistingShapeHighlightHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = ai_existing_shape_highlight_harness
    canvas = harness.canvas
    inferred = Shape(
        shape_type="rectangle",
        points=np.array([[70, 20], [80, 30]], dtype=np.float64),
    )
    monkeypatch.setattr(
        canvas,
        "_propose_ai_shapes",
        lambda **_: AiAssistProposal(
            new_shapes=[inferred],
            matching_existing_shapes=[harness.existing],
        ),
    )

    canvas._finalize()

    assert canvas.shapes == [harness.existing, inferred]
    assert harness.new_shape_emissions == [None]
    assert harness.no_shapes_emissions == []
    highlight = canvas.grab().toImage().pixelColor(30, 20)
    assert highlight.red() > highlight.green() > highlight.blue()


@pytest.mark.gui
@pytest.mark.parametrize("create_mode", ["point", "ai_segment"])
def test_finalize_paints_new_shape_before_notifying(
    *,
    canvas: Canvas,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    create_mode: str,
) -> None:
    # new_shape's handler blocks on the modal label dialog, so the committed
    # shape must already be on screen when it fires. Point and AI-Segment can
    # finalize without first painting a matching preview.
    inferred = Shape(
        shape_type="polygon",
        points=np.array([(1, 1), (9, 1), (9, 9)], dtype=np.float64),
        closed=True,
    )
    monkeypatch.setattr(
        canvas,
        "_propose_ai_shapes",
        lambda **_: AiAssistProposal(
            new_shapes=[inferred],
            matching_existing_shapes=[],
        ),
    )
    with qtbot.waitExposed(canvas):
        canvas.show()

    painted_shape_counts: list[int] = []
    render_canvas = canvas._render_canvas

    def record_then_render() -> None:
        painted_shape_counts.append(len(canvas.shapes))
        render_canvas()

    monkeypatch.setattr(canvas, "_render_canvas", record_then_render)
    counts_when_notified: list[int] = []
    canvas.new_shape.connect(lambda: counts_when_notified.extend(painted_shape_counts))

    canvas.create_mode = create_mode
    if create_mode == "point":
        canvas._current = _DraftShape(
            shape_type="point",
            points=(QPointF(5, 5),),
            point_labels=(1,),
        )
    else:
        canvas._current = _DraftShape(
            shape_type="points",
            points=(QPointF(0, 0), QPointF(10, 10)),
            point_labels=(2, 3),
        )
    canvas._finalize()

    assert counts_when_notified == [1]


@pytest.mark.gui
def test_finalize_reports_inference_error_and_cancels(
    *, canvas: Canvas, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A model error while committing an AI shape must not crash _finalize: it
    # surfaces a non-fatal inference_failed signal, cancels the in-progress
    # shape, and does not masquerade as an empty-inference result.
    def _raise(**_: object) -> list[Shape]:
        raise RuntimeError("boom")

    monkeypatch.setattr(canvas, "_propose_ai_shapes", _raise)
    canvas.create_mode = "ai_segment"
    canvas._current = _DraftShape(
        shape_type="points",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(2, 3),
    )
    failed: list[str] = []
    no_shapes: list[None] = []
    canvas.inference_failed.connect(failed.append)
    canvas.inference_produced_no_shapes.connect(lambda: no_shapes.append(None))

    canvas._finalize()

    assert failed == ["RuntimeError: boom"]
    assert no_shapes == []
    assert canvas._current is None
    assert canvas.shapes == []


@pytest.mark.gui
def test_slow_finalize_rings_last_point_and_esc_drops_its_result(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    worker = _worker(canvas)
    worker.annotations = [
        osam.types.Annotation(
            bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=10, ymax=10),
            mask=np.ones((11, 11), dtype=bool),
        )
    ]
    worker.paused = True
    canvas.set_editing(value=False, create_mode="ai_segment")
    canvas._current = _DraftShape(
        shape_type="points",
        points=(QPointF(0, 0), QPointF(30, 20)),
        point_labels=(2, 3),
    )

    canvas._finalize()

    assert canvas.is_ai_finalizing
    assert canvas._ai_progress_rect() is None  # a fast answer shows no ring
    qtbot.waitUntil(lambda: canvas._ai_progress_rect() is not None, timeout=1000)
    rect = canvas._ai_progress_rect()
    assert rect is not None
    assert rect.contains(
        canvas.transform_image_point_to_widget(QPointF(30, 20)).toPoint()
    )

    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    worker.resume()

    assert canvas._ai_progress_rect() is None
    assert canvas._current is None
    assert canvas.shapes == []


@pytest.mark.gui
def test_slow_ai_segment_preview_rings_last_placed_point(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    worker = _worker(canvas)
    worker.paused = True
    canvas.set_editing(value=False, create_mode="ai_segment")
    canvas._current = _DraftShape(
        shape_type="points", points=(QPointF(30, 20),), point_labels=(1,)
    )

    canvas._refresh_ai_segment_preview()

    assert canvas._ai_progress_rect() is None  # a fast answer shows no ring
    qtbot.waitUntil(lambda: canvas._ai_progress_rect() is not None, timeout=1000)
    # A preview for the moved cursor replaces the slow one and keeps its ring.
    canvas._line = _DraftShape(
        shape_type="points", points=(QPointF(5, 5),), point_labels=(1,)
    )
    canvas._refresh_ai_segment_preview()
    rect = canvas._ai_progress_rect()
    assert rect is not None
    assert rect.contains(
        canvas.transform_image_point_to_widget(QPointF(30, 20)).toPoint()
    )

    worker.resume()

    assert canvas._ai_progress_rect() is None

    # Esc leaves a stale preview in flight; the next click still rings.
    worker.paused = True
    canvas._line = _DraftShape(
        shape_type="points", points=(QPointF(6, 6),), point_labels=(1,)
    )
    canvas._refresh_ai_segment_preview()
    assert canvas._ai_preview_job is not None
    canvas._current = None
    canvas._refresh_ai_segment_preview()
    qtbot.waitUntil(lambda: not canvas._ai_progress_timer.isActive(), timeout=1000)
    canvas._current = _DraftShape(
        shape_type="points", points=(QPointF(40, 10),), point_labels=(1,)
    )
    canvas._refresh_ai_segment_preview()
    assert canvas._ai_progress_timer.isActive()
    assert canvas._ai_progress_rect() is None  # the delay starts over
    qtbot.waitUntil(lambda: canvas._ai_progress_rect() is not None, timeout=1000)


@pytest.mark.gui
@pytest.mark.parametrize(
    "leave", [{"value": False, "create_mode": "polygon"}, {"value": True}]
)
def test_slow_ai_segment_preview_ring_ends_on_leaving_ai_segment(
    *, canvas: Canvas, qtbot: QtBot, leave: dict[str, object]
) -> None:
    _worker(canvas).paused = True
    canvas.set_editing(value=False, create_mode="ai_segment")
    canvas._current = _DraftShape(
        shape_type="points", points=(QPointF(30, 20),), point_labels=(1,)
    )
    canvas._refresh_ai_segment_preview()
    qtbot.waitUntil(lambda: canvas._ai_progress_rect() is not None, timeout=1000)

    canvas.set_editing(**leave)  # ty: ignore[invalid-argument-type]

    assert canvas._ai_progress_rect() is None
    qtbot.waitUntil(lambda: not canvas._ai_progress_timer.isActive(), timeout=1000)


@pytest.mark.gui
def test_ai_find_all_results_have_white_edge_and_examples_keep_line_color(
    *, canvas: Canvas
) -> None:
    canvas.set_editing(value=False, create_mode="ai_find_all")
    # The chips would cover the probes.
    canvas._ai_suggestion_hint = lambda: None  # ty: ignore[invalid-assignment]
    canvas._ai_prompt_hint = lambda: None  # ty: ignore[invalid-assignment]
    canvas._ai_find_all_draft = [
        Shape(shape_type="rectangle", points=np.array([[10.0, 10.0], [40.0, 40.0]]))
    ]
    canvas._ai_find_all_points = np.array([[60.0, 10.0], [90.0, 40.0]])
    canvas._ai_find_all_point_labels = np.array([2, 3])

    image = canvas.grab().toImage()

    result_edge = image.pixelColor(25, 9)  # outside the fill
    assert min(result_edge.red(), result_edge.green(), result_edge.blue()) > 200
    example_edge = image.pixelColor(75, 9)
    assert example_edge.green() > 200 > example_edge.red()


@pytest.mark.gui
@pytest.mark.parametrize(
    ("create_mode", "draft", "color"),
    [
        (
            "ai_segment",
            _DraftShape(
                shape_type="points",
                points=(QPointF(10, 10), QPointF(40, 40)),
                point_labels=(2, 3),
            ),
            (0, 255, 0),
        ),
        (
            "ai_find_all",
            _DraftShape(
                shape_type="rectangle",
                points=(QPointF(10, 10), QPointF(40, 40)),
                point_labels=(1, 1),
            ),
            (0, 255, 0),
        ),
        (
            "ai_find_all",
            _DraftShape(
                shape_type="rectangle",
                points=(QPointF(10, 10), QPointF(40, 40)),
                point_labels=(0, 0),
            ),
            (255, 0, 0),
        ),
    ],
)
def test_prompt_box_being_drawn_is_a_dashed_guide(
    *,
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
    create_mode: str,
    draft: _DraftShape,
    color: tuple[int, int, int],
) -> None:
    drawn: list[tuple[str, Qt.PenStyle, tuple[int, int, int]]] = []

    def record(*, shape: Shape, context: ShapeRenderContext, **_: object) -> None:
        line = context.palette.line
        drawn.append(
            (
                shape.shape_type,
                context.line_style,
                (line.red(), line.green(), line.blue()),
            )
        )

    monkeypatch.setattr("labelme._widgets._canvas.render_shape", record)
    canvas.set_editing(value=False, create_mode=create_mode)
    canvas._current = draft

    canvas.grab()

    assert ("rectangle", Qt.PenStyle.DashLine, color) in drawn


@pytest.mark.gui
@pytest.mark.parametrize(("label", "color"), [(2, (0, 255, 0)), (4, (255, 0, 0))])
def test_ai_find_all_example_boxes_are_dashed_and_counter_ones_red(
    *,
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
    label: int,
    color: tuple[int, int, int],
) -> None:
    drawn: list[tuple[Qt.PenStyle, tuple[int, int, int]]] = []

    def record(*, context: ShapeRenderContext, **_: object) -> None:
        line = context.palette.line
        if not context.fill:
            drawn.append((context.line_style, (line.red(), line.green(), line.blue())))

    monkeypatch.setattr("labelme._widgets._canvas.render_shape", record)
    canvas.set_editing(value=False, create_mode="ai_find_all")
    canvas._ai_find_all_draft = []
    canvas._ai_find_all_points = np.array([[60.0, 10.0], [90.0, 40.0]])
    canvas._ai_find_all_point_labels = np.array([label, label + 1])

    canvas.grab()

    assert drawn == [(Qt.PenStyle.DashLine, color)]


@pytest.mark.gui
def test_points_preview_hides_failed_and_empty_predictions(
    *,
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Repeated failed prompts report once; a successful prompt re-arms errors.
    behavior = {"fail": True}

    def _maybe_raise(**_: object) -> AiAssistProposal:
        if behavior["fail"]:
            raise RuntimeError("boom")
        return AiAssistProposal(new_shapes=[], matching_existing_shapes=[])

    monkeypatch.setattr(canvas, "_propose_ai_shapes", _maybe_raise)
    canvas.create_mode = "ai_segment"
    canvas._line = _DraftShape(
        shape_type="points", points=(QPointF(5, 5),), point_labels=(1,)
    )
    canvas._current = _DraftShape(
        shape_type="points", points=(QPointF(0, 0),), point_labels=(1,)
    )
    failed: list[str] = []
    canvas.inference_failed.connect(failed.append)

    canvas._refresh_ai_segment_preview()
    assert canvas._build_preview_shapes() == []
    canvas._line = dataclasses.replace(canvas._line, points=(QPointF(5, 6),))
    canvas._refresh_ai_segment_preview()
    assert canvas._build_preview_shapes() == []
    assert failed == ["RuntimeError: boom"]

    behavior["fail"] = False
    canvas._line = dataclasses.replace(canvas._line, points=(QPointF(6, 6),))
    canvas._refresh_ai_segment_preview()
    assert canvas._build_preview_shapes() == []
    behavior["fail"] = True
    canvas._line = dataclasses.replace(canvas._line, points=(QPointF(7, 7),))
    canvas._refresh_ai_segment_preview()
    assert canvas._build_preview_shapes() == []
    assert failed == ["RuntimeError: boom", "RuntimeError: boom"]


@pytest.mark.gui
def test_ai_segment_preview_renders_every_proposed_shape(
    *,
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previews = [
        Shape(
            shape_type="polygon",
            points=np.array(points, dtype=np.float64),
            closed=True,
        )
        for points in (
            [(10, 10), (20, 10), (20, 20)],
            [(60, 10), (70, 10), (70, 20)],
        )
    ]
    monkeypatch.setattr(
        canvas,
        "_propose_ai_shapes",
        lambda **_: AiAssistProposal(
            new_shapes=previews,
            matching_existing_shapes=[],
        ),
    )
    canvas.create_mode = "ai_segment"
    canvas._current = _DraftShape(
        shape_type="points", points=(QPointF(5, 5),), point_labels=(1,)
    )
    canvas._line = _DraftShape(
        shape_type="points", points=(QPointF(6, 6),), point_labels=(1,)
    )
    canvas._refresh_ai_segment_preview()
    image = QtGui.QImage(_WIDTH, _HEIGHT, QtGui.QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.black)
    painter = QtGui.QPainter(image)

    canvas._draw_preview_overlay_layer(painter)
    painter.end()

    for x in (15, 65):
        color = image.pixelColor(x, 10)
        assert color.green() > color.red()
        assert color.green() > color.blue()


@pytest.mark.gui
def test_load_pixmap_rearms_inference_failure_report(*, canvas: Canvas) -> None:
    # A new image is a fresh inference context: a previous image's latched
    # failure must not mute the first failure report on the new image.
    canvas._ai_inference_failed = True
    canvas.load_pixmap(pixmap=QtGui.QPixmap(_WIDTH, _HEIGHT))
    assert canvas._ai_inference_failed is False


@pytest.mark.gui
def test_load_pixmap_defers_image_hash(
    *, canvas: Canvas, monkeypatch: pytest.MonkeyPatch
) -> None:
    pixmap = QtGui.QPixmap(_WIDTH, _HEIGHT)
    monkeypatch.setattr(
        pixmap, "toImage", Mock(side_effect=AssertionError("Image converted on load"))
    )
    canvas._pixmap_rgb = (np.zeros((1, 1, 3), dtype=np.uint8), "1")
    canvas.load_pixmap(pixmap=pixmap)
    assert canvas._pixmap_rgb is None


@pytest.mark.gui
@pytest.mark.parametrize("change", ["pixels", "dimensions"])
def test_ai_image_id_is_reused_after_reloading_image(
    *, canvas: Canvas, change: str
) -> None:
    # The worker reuses its image embedding for a repeated image id.
    first = QtGui.QImage(_WIDTH, _HEIGHT, QtGui.QImage.Format.Format_RGB32)
    first.fill(Qt.GlobalColor.red)
    second = QtGui.QImage(
        _WIDTH if change == "pixels" else _HEIGHT,
        _HEIGHT if change == "pixels" else _WIDTH,
        QtGui.QImage.Format.Format_RGB32,
    )
    second.fill(Qt.GlobalColor.blue if change == "pixels" else Qt.GlobalColor.red)
    keys: list[int] = []
    for image in [first, second, first]:
        # Fresh image data, as file navigation creates, rather than a shared pixmap.
        pixmap = QtGui.QPixmap.fromImage(image.copy())
        keys.append(pixmap.cacheKey())
        canvas.reset_state()
        canvas.load_pixmap(pixmap=pixmap)
        canvas._submit_ai_job(
            channel="preview",
            prompt_kind="points",
            points=[QPointF(10, 10)],
            point_labels=[1],
        )
    first_id, second_id, reloaded_id = (r.image_id for r in _worker(canvas).requests)
    assert second_id != first_id
    assert reloaded_id == first_id
    assert len(set(keys)) == 3


@pytest.mark.gui
def test_create_mode_switch_retypes_one_point_partial(*, canvas: Canvas) -> None:
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
    *,
    canvas: Canvas,
) -> None:
    # Multi-point partial cancels, and listeners on busy_changed must
    # observe the new create_mode synchronously.
    canvas.create_mode = "polygon"
    canvas._current = _DraftShape(
        shape_type="polygon",
        points=(QPointF(10, 10), QPointF(20, 20)),
        point_labels=(1, 1),
    )
    emissions: list[bool] = []
    observed_modes: list[str] = []

    def listener() -> None:
        emissions.append(canvas.is_busy)
        observed_modes.append(canvas.create_mode)

    canvas.busy_changed.connect(listener)

    canvas.create_mode = "rectangle"

    assert canvas._current is None
    assert emissions == [False]
    assert observed_modes == ["rectangle"]


@pytest.mark.gui
def test_create_mode_switch_to_ai_target_cancels_one_point_partial(
    *,
    canvas: Canvas,
) -> None:
    # AI modes carry per-point labels, so a non-AI seed can't be
    # reinterpreted as an AI seed even with only 1 point.
    canvas.create_mode = "rectangle"
    canvas._current = _DraftShape(
        shape_type="rectangle", points=(QPointF(10, 10),), point_labels=(1,)
    )
    emissions: list[bool] = []
    canvas.busy_changed.connect(lambda: emissions.append(canvas.is_busy))

    canvas.create_mode = "ai_segment"

    assert canvas._current is None
    assert emissions == [False]


@pytest.mark.gui
def test_create_mode_switch_preserves_seed_point_label(*, canvas: Canvas) -> None:
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
    *, canvas: Canvas, to_mode: str
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
        QtCore.QEvent.Type.MouseButtonPress,
        QPointF(50, 30),
        QPointF(50, 30),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
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
    *, canvas: Canvas, to_mode: str
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
        QtCore.QEvent.Type.MouseButtonPress,
        QPointF(50, 30),
        QPointF(50, 30),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
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


def _left_press(*, pos: QPointF, modifiers: Qt.KeyboardModifier) -> QtGui.QMouseEvent:
    return QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        modifiers,
    )


def _start_open_path(*, canvas: Canvas, mode: str, cursor: QPointF) -> _DraftShape:
    canvas.create_mode = mode
    shape_type = _CREATE_MODE_TO_SHAPE_TYPE[canvas.create_mode]
    canvas._current = _DraftShape(
        shape_type=shape_type, points=(QPointF(10, 10),), point_labels=(1,)
    )
    canvas._line = _DraftShape(
        shape_type=shape_type, points=(QPointF(10, 10), cursor), point_labels=(1, 1)
    )
    return canvas._current


@pytest.mark.gui
@pytest.mark.parametrize("mode", ["polygon", "linestrip"])
def test_extend_open_path_commits_cursor_and_previews_from_it(
    *, canvas: Canvas, mode: str
) -> None:
    current = _start_open_path(canvas=canvas, mode=mode, cursor=QPointF(50, 30))

    canvas._extend_current_shape(
        current=current,
        event=_left_press(
            pos=QPointF(50, 30), modifiers=Qt.KeyboardModifier.NoModifier
        ),
    )

    assert canvas.shapes == []
    assert canvas._current is not None
    assert canvas._current.points == (QPointF(10, 10), QPointF(50, 30))
    assert canvas._line.points[0] == QPointF(50, 30)


@pytest.mark.gui
@pytest.mark.parametrize(
    "modifiers",
    [
        Qt.KeyboardModifier.ControlModifier,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    ],
    ids=["control", "control-shift"],
)
def test_extend_linestrip_with_control_click_finishes_at_cursor(
    *, canvas: Canvas, modifiers: Qt.KeyboardModifier
) -> None:
    current = _start_open_path(canvas=canvas, mode="linestrip", cursor=QPointF(50, 30))

    canvas._extend_current_shape(
        current=current, event=_left_press(pos=QPointF(50, 30), modifiers=modifiers)
    )

    assert canvas._current is None
    assert len(canvas.shapes) == 1
    assert canvas.shapes[0].shape_type == "linestrip"
    np.testing.assert_array_equal(canvas.shapes[0].points, [[10, 10], [50, 30]])


@pytest.mark.gui
def test_extend_polygon_on_first_vertex_closes_it(*, canvas: Canvas) -> None:
    canvas.create_mode = "polygon"
    points = (QPointF(10, 10), QPointF(50, 30), QPointF(30, 60))
    canvas._current = _DraftShape(
        shape_type="polygon", points=points, point_labels=(1, 1, 1)
    )
    canvas._line = _DraftShape(
        shape_type="polygon", points=(points[-1], points[0]), point_labels=(1, 1)
    )

    canvas._extend_current_shape(
        current=canvas._current,
        event=_left_press(pos=points[0], modifiers=Qt.KeyboardModifier.NoModifier),
    )

    assert canvas._current is None
    assert len(canvas.shapes) == 1
    assert canvas.shapes[0].closed
    np.testing.assert_array_equal(
        canvas.shapes[0].points, [[10, 10], [50, 30], [30, 60]]
    )


@pytest.mark.gui
def test_undo_last_line_on_point_reports_not_drawing(*, canvas: Canvas) -> None:
    canvas.create_mode = "point"
    canvas.shapes.append(
        Shape(shape_type="point", points=np.array([[10, 10]], dtype=np.float64))
    )
    emissions: list[bool] = []
    canvas.busy_changed.connect(lambda: emissions.append(canvas.is_busy))

    canvas.undo_last_line()

    assert not canvas.shapes
    assert emissions == [False]


@pytest.mark.gui
def test_undo_last_line_then_click_without_moving_recloses_polygon(
    *, canvas: Canvas
) -> None:
    canvas.create_mode = "polygon"
    canvas.shapes.append(
        Shape(
            shape_type="polygon",
            points=np.array([[10, 10], [50, 30], [30, 60]], dtype=np.float64),
            closed=True,
        )
    )

    canvas.undo_last_line()
    assert canvas._current is not None
    # The reopened preview runs back to the first vertex, so a click there
    # closes the polygon again.
    canvas._extend_current_shape(
        current=canvas._current,
        event=_left_press(
            pos=QPointF(10, 10), modifiers=Qt.KeyboardModifier.NoModifier
        ),
    )

    assert canvas._current is None
    assert len(canvas.shapes) == 1
    np.testing.assert_array_equal(
        canvas.shapes[0].points, [[10, 10], [50, 30], [30, 60]]
    )


@pytest.mark.gui
def test_extend_polygon_with_control_click_keeps_drawing(*, canvas: Canvas) -> None:
    current = _start_open_path(canvas=canvas, mode="polygon", cursor=QPointF(50, 30))

    canvas._extend_current_shape(
        current=current,
        event=_left_press(
            pos=QPointF(50, 30), modifiers=Qt.KeyboardModifier.ControlModifier
        ),
    )

    assert canvas.shapes == []
    assert canvas._current is not None
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
    *, shape_type: ShapeType, points: list[tuple[float, float]], expected: bool
) -> None:
    draft = _DraftShape(
        shape_type=shape_type,
        points=tuple(QPointF(x, y) for x, y in points),
        point_labels=tuple(1 for _ in points),
    )
    assert _is_degenerate_draft(draft) is expected


@pytest.mark.parametrize(
    "point, expected",
    [
        pytest.param((0, 0), False, id="top_left_corner_inside"),
        pytest.param((_WIDTH, _HEIGHT), False, id="bottom_right_corner_inside"),
        pytest.param((_WIDTH / 2, _HEIGHT / 2), False, id="interior_inside"),
        pytest.param((-0.1, _HEIGHT / 2), True, id="left_of_image"),
        pytest.param((_WIDTH / 2, -0.1), True, id="above_image"),
        pytest.param((_WIDTH + 0.1, _HEIGHT / 2), True, id="right_of_image"),
        pytest.param((_WIDTH / 2, _HEIGHT + 0.1), True, id="below_image"),
    ],
)
def test_is_out_of_image(*, point: tuple[float, float], expected: bool) -> None:
    # The image rect is inclusive at both edges: a point exactly on the far
    # width/height boundary counts as inside, since the clamping callers treat
    # the pixmap size as a reachable coordinate rather than an exclusive extent.
    assert _is_out_of_image(QPointF(*point), QSize(_WIDTH, _HEIGHT)) is expected


@pytest.mark.gui
@pytest.mark.parametrize("shape_type", ["rectangle", "circle", "line"])
def test_finalize_rejects_degenerate_shape(
    *, canvas: Canvas, shape_type: ShapeType
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
    *,
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


def test_add_point_appends_point_with_default_label() -> None:
    draft = _DraftShape(shape_type="polygon").add_point(QPointF(1, 2))

    assert draft.points == (QPointF(1, 2),)
    assert draft.point_labels == (1,)
    assert draft.closed is False


def test_add_point_appends_with_explicit_label() -> None:
    draft = _DraftShape(shape_type="points").add_point(QPointF(3, 4), label=0)

    assert draft.points == (QPointF(3, 4),)
    assert draft.point_labels == (0,)


def test_add_point_autoclose_closes_when_new_point_matches_first() -> None:
    start = _DraftShape(
        shape_type="polygon",
        points=(QPointF(0, 0), QPointF(10, 0), QPointF(10, 10)),
        point_labels=(1, 1, 1),
    )

    closed = start.add_point(QPointF(0, 0), autoclose=True)

    assert closed.closed is True
    assert closed.points == start.points  # first point is not re-appended
    assert closed.point_labels == start.point_labels


def test_add_point_autoclose_appends_when_new_point_differs_from_first() -> None:
    start = _DraftShape(
        shape_type="polygon",
        points=(QPointF(0, 0), QPointF(10, 0)),
        point_labels=(1, 1),
    )

    grown = start.add_point(QPointF(10, 10), autoclose=True)

    assert grown.closed is False
    assert grown.points == (QPointF(0, 0), QPointF(10, 0), QPointF(10, 10))


def test_add_point_autoclose_on_empty_draft_appends_seed_point() -> None:
    # No first point to match against, so autoclose falls through to a normal append.
    draft = _DraftShape(shape_type="polygon").add_point(QPointF(5, 5), autoclose=True)

    assert draft.closed is False
    assert draft.points == (QPointF(5, 5),)


def test_add_point_without_autoclose_appends_even_when_matching_first() -> None:
    start = _DraftShape(
        shape_type="polygon",
        points=(QPointF(0, 0), QPointF(10, 0)),
        point_labels=(1, 1),
    )

    grown = start.add_point(QPointF(0, 0))

    assert grown.closed is False
    assert grown.points == (QPointF(0, 0), QPointF(10, 0), QPointF(0, 0))


def test_pop_point_removes_last_point_and_label() -> None:
    start = _DraftShape(
        shape_type="polygon",
        points=(QPointF(0, 0), QPointF(10, 0)),
        point_labels=(1, 0),
    )

    popped = start.pop_point()

    assert popped.points == (QPointF(0, 0),)
    assert popped.point_labels == (1,)


def test_pop_point_on_empty_draft_returns_same_instance() -> None:
    draft = _DraftShape(shape_type="polygon")

    assert draft.pop_point() is draft


def test_close_and_open_toggle_closed_and_preserve_other_fields() -> None:
    draft = _DraftShape(
        shape_type="polygon",
        points=(QPointF(0, 0), QPointF(10, 0)),
        point_labels=(1, 1),
    )

    closed = draft.close()
    reopened = closed.open()

    assert closed.closed is True
    assert reopened.closed is False
    for toggled in (closed, reopened):
        assert toggled.points == draft.points
        assert toggled.point_labels == draft.point_labels
        assert toggled.shape_type == draft.shape_type


def test_draft_to_shape_carries_points_labels_and_closed() -> None:
    draft = _DraftShape(
        shape_type="polygon",
        points=(QPointF(0, 0), QPointF(10, 0), QPointF(10, 10)),
        point_labels=(1, 0, 1),
        closed=True,
    )

    shape = _draft_to_shape(draft)

    assert shape.shape_type == "polygon"
    assert shape.closed is True
    np.testing.assert_array_equal(
        shape.points, np.array([[0, 0], [10, 0], [10, 10]], dtype=np.float64)
    )
    np.testing.assert_array_equal(
        shape.point_labels, np.array([1, 0, 1], dtype=np.int_)
    )


def test_shape_to_draft_carries_points_labels_and_closed() -> None:
    shape = Shape(
        shape_type="polygon",
        points=np.array([[0, 0], [10, 0], [10, 10]], dtype=np.float64),
        point_labels=np.array([1, 0, 1], dtype=np.int_),
        closed=True,
    )

    draft = _shape_to_draft(shape)

    assert draft.shape_type == "polygon"
    assert draft.closed is True
    assert draft.points == (QPointF(0, 0), QPointF(10, 0), QPointF(10, 10))
    assert draft.point_labels == (1, 0, 1)


def test_draft_and_shape_round_trip_preserves_values() -> None:
    draft = _DraftShape(
        shape_type="points",
        points=(QPointF(1, 2), QPointF(3, 4)),
        point_labels=(1, 0),
        closed=False,
    )

    assert _shape_to_draft(_draft_to_shape(draft)) == draft


def test_converters_preserve_mismatched_points_and_labels_lengths() -> None:
    # A finalized rectangle/circle/line carries 2 points but a single point_label;
    # undo_last_line round-trips exactly such a Shape back through _shape_to_draft,
    # so the converters must not zip or pad the two to equal length.
    draft = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(1,),
    )

    shape = _draft_to_shape(draft)

    assert len(shape.points) == 2
    assert len(shape.point_labels) == 1
    assert _shape_to_draft(shape) == draft


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
        pytest.param(
            QPointF(100, 0),
            QPointF(50, -10),
            QPointF(50, 0),
            id="on_top_right_corner_dragged_left_slides_along_top_edge",
        ),
        pytest.param(
            QPointF(0, 50),
            QPointF(60, 55),
            QPointF(60, 50),
            id="on_bottom_left_corner_dragged_right_slides_along_bottom_edge",
        ),
        pytest.param(
            QPointF(100, 0),
            QPointF(120, 25),
            QPointF(100, 25),
            id="on_top_right_corner_dragged_right_slides_along_right_edge",
        ),
        pytest.param(
            QPointF(0, 0),
            QPointF(50, -10),
            QPointF(50, 0),
            id="on_top_left_corner_dragged_right_slides_along_top_edge",
        ),
        pytest.param(
            QPointF(0, 0),
            QPointF(-10, 25),
            QPointF(0, 25),
            id="on_top_left_corner_dragged_down_slides_along_left_edge",
        ),
        pytest.param(
            QPointF(0, 50),
            QPointF(-10, 25),
            QPointF(0, 25),
            id="on_bottom_left_corner_dragged_up_slides_along_left_edge",
        ),
        pytest.param(
            QPointF(100, 50),
            QPointF(50, 60),
            QPointF(50, 50),
            id="on_bottom_right_corner_dragged_left_slides_along_bottom_edge",
        ),
        pytest.param(
            QPointF(100, 50),
            QPointF(110, 25),
            QPointF(100, 25),
            id="on_bottom_right_corner_dragged_up_slides_along_right_edge",
        ),
        pytest.param(
            QPointF(100, 0),
            QPointF(110, -5),
            QPointF(100, 0),
            id="on_top_right_corner_pushed_diagonally_out_stays",
        ),
        pytest.param(
            QPointF(0, 50),
            QPointF(-5, 55),
            QPointF(0, 50),
            id="on_bottom_left_corner_pushed_diagonally_out_stays",
        ),
    ],
)
def test_compute_intersection_edges_image(
    *, p1: QPointF, p2: QPointF, expected: QPointF
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
    *, p1: QPointF, p2: QPointF
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


def test_reproject_oriented_rectangle_clips_degenerate_projection() -> None:
    corners = tuple(
        QPointF(*point) for point in [(20, 10), (30, 20), (20, 30), (10, 20)]
    )

    new_corners = _reproject_oriented_rectangle_corners(
        corners=corners,
        vertex_index=1,
        pos=QPointF(-30, 0),
        image_size=QSize(_WIDTH, _HEIGHT),
        allow_out_of_bounds=False,
    )

    for corner in new_corners:
        assert 0 <= corner.x() <= _WIDTH
        assert 0 <= corner.y() <= _HEIGHT


def test_should_reselect_on_right_press_with_empty_selection() -> None:
    # Empty selection reselects even when hovering nothing; without the guard this
    # input would fall through to `hovered_shape is None` and wrongly return False.
    assert _should_reselect_on_right_press(selected_shapes=[], hovered_shape=None)


def test_should_reselect_on_right_press_keeps_selection_when_hovering_nothing() -> None:
    selected = [Shape()]
    assert not _should_reselect_on_right_press(
        selected_shapes=selected, hovered_shape=None
    )


def test_should_reselect_on_right_press_when_hovering_outside_selection() -> None:
    assert _should_reselect_on_right_press(
        selected_shapes=[Shape()], hovered_shape=Shape()
    )


def test_should_reselect_on_right_press_keeps_selection_hovering_selected() -> None:
    hovered = Shape()
    assert not _should_reselect_on_right_press(
        selected_shapes=[Shape(), hovered], hovered_shape=hovered
    )


@pytest.mark.parametrize(
    ("pos", "opposite_vertex", "expected"),
    [
        pytest.param((10, 4), (0, 0), (4.0, 4.0), id="wider_than_tall_snaps_to_height"),
        pytest.param((4, 10), (0, 0), (4.0, 4.0), id="taller_than_wide_snaps_to_width"),
        pytest.param((-10, 4), (0, 0), (-4.0, 4.0), id="preserves_negative_x_sign"),
        pytest.param((10, -4), (0, 0), (4.0, -4.0), id="preserves_negative_y_sign"),
        pytest.param((-10, -4), (0, 0), (-4.0, -4.0), id="preserves_both_signs"),
        pytest.param((5, 5), (2, 3), (4.0, 5.0), id="offsets_from_opposite_vertex"),
        pytest.param((6, 6), (2, 2), (6.0, 6.0), id="already_square_is_unchanged"),
        pytest.param((0, 5), (0, 0), (0.0, 0.0), id="collapses_when_one_axis_is_zero"),
        pytest.param((0, 0), (0, 0), (0.0, 0.0), id="zero_delta_stays_put"),
        pytest.param((5, 0), (0, 0), (0.0, 0.0), id="horizontal_collapses"),
        pytest.param((7.75, -2.5), (1.25, 3.25), (7.0, -2.5), id="fractional"),
    ],
)
def test_snap_cursor_pos_for_square(
    *,
    pos: tuple[float, float],
    opposite_vertex: tuple[float, float],
    expected: tuple[float, float],
) -> None:
    result = _snap_cursor_pos_for_square(
        pos=QPointF(*pos), opposite_vertex=QPointF(*opposite_vertex)
    )
    assert (result.x(), result.y()) == pytest.approx(expected)


def _make_polygon() -> Shape:
    return Shape(
        shape_type="polygon",
        points=np.array([(10, 10), (40, 10), (40, 40), (10, 40)], dtype=np.float64),
        closed=True,
    )


@pytest.mark.gui
def test_add_point_to_edge_repaints(
    *, canvas: Canvas, monkeypatch: pytest.MonkeyPatch
) -> None:
    shape = _make_polygon()
    canvas.load_shapes(shapes=[shape])
    canvas._last_hovered_shape = shape
    canvas._last_hovered_edge = 0
    canvas._prev_move_point = QPointF(25, 10)
    update = Mock()
    monkeypatch.setattr(canvas, "update", update)

    n_before = len(shape.points)
    canvas.add_point_to_edge()

    assert len(shape.points) == n_before + 1
    update.assert_called_once()  # repaint now, not only on the next mouse move (#890)


@pytest.mark.gui
def test_remove_selected_point_repaints(
    *, canvas: Canvas, monkeypatch: pytest.MonkeyPatch
) -> None:
    shape = _make_polygon()
    canvas.load_shapes(shapes=[shape])
    canvas._last_hovered_shape = shape
    canvas._last_hovered_vertex = 1
    update = Mock()
    monkeypatch.setattr(canvas, "update", update)

    n_before = len(shape.points)
    canvas.remove_selected_point()

    assert len(shape.points) == n_before - 1
    update.assert_called_once()  # repaint now, not only on the next mouse move (#890)


@pytest.mark.gui
def test_reset_view_offset_repaints(
    *, canvas: Canvas, monkeypatch: pytest.MonkeyPatch
) -> None:
    canvas._view_offset = QPointF(17, 23)
    update = Mock()
    monkeypatch.setattr(canvas, "update", update)

    canvas.reset_view_offset()

    assert canvas.get_view_offset().isNull()
    update.assert_called_once()


@pytest.mark.gui
def test_reset_state_clears_view_offset(*, canvas: Canvas) -> None:
    canvas._view_offset = QPointF(17, 23)

    canvas.reset_state()

    assert canvas.get_view_offset().isNull()


@pytest.mark.gui
def test_remove_selected_point_deselects_vertex(*, canvas: Canvas) -> None:
    shape = _make_polygon()
    canvas.load_shapes(shapes=[shape])
    canvas._last_hovered_shape = shape
    canvas._last_hovered_vertex = 1
    canvas._hovered_vertex = 1

    canvas.remove_selected_point()

    assert len(shape.points) == 3  # the point was removed
    # Vertex is no longer selected, so the next move won't drag the neighbor (#968).
    assert not canvas._is_vertex_selected()


def _drag(
    *,
    qtbot: QtBot,
    canvas: Canvas,
    start: QtCore.QPoint,
    end: QtCore.QPoint,
    release: QtCore.QPoint | None = None,
    modifier: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, modifier, pos=start)
    canvas.mouseMoveEvent(
        QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseMove,
            QPointF(end),
            QPointF(end),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            modifier,
        )
    )
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, modifier, pos=release or end)


@pytest.mark.gui
@pytest.mark.parametrize("model_name", ["sam2:small", "sam3:latest"])
def test_ai_segment_combines_clicks_and_one_dragged_box(
    *, canvas: Canvas, qtbot: QtBot, model_name: str
) -> None:
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.set_ai_model_name(model_name=model_name)
    canvas.scale = 1.0
    canvas.set_editing(value=False, create_mode="ai_segment")

    _drag(
        qtbot=qtbot,
        canvas=canvas,
        start=QtCore.QPoint(10, 10),
        end=QtCore.QPoint(70, 30),
    )
    assert canvas._current is not None
    assert canvas._current.point_labels == (2, 3)
    # A press that moves less than the drag distance is a click.
    _drag(
        qtbot=qtbot,
        canvas=canvas,
        start=QtCore.QPoint(40, 20),
        end=QtCore.QPoint(41, 20),
    )
    qtbot.mouseClick(
        canvas,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        pos=QtCore.QPoint(60, 25),
    )
    assert canvas._current.point_labels == (2, 3, 1, 0)
    # A new box replaces the old one; the points stay.
    _drag(
        qtbot=qtbot,
        canvas=canvas,
        start=QtCore.QPoint(80, 40),
        end=QtCore.QPoint(20, 5),
    )
    assert _worker(canvas).requests == []

    qtbot.keyClick(canvas, Qt.Key.Key_Return)

    (request,) = _worker(canvas).requests
    assert request.points is not None
    assert request.point_labels is not None
    np.testing.assert_array_equal(
        request.points, [[40, 20], [60, 25], [20, 5], [80, 40]]
    )
    assert request.point_labels.tolist() == [1, 0, 2, 3]


@pytest.mark.gui
def test_ai_segment_undo_removes_the_last_input(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.set_ai_model_name(model_name="sam2:small")
    canvas.scale = 1.0
    canvas.set_editing(value=False, create_mode="ai_segment")
    _drag(
        qtbot=qtbot,
        canvas=canvas,
        start=QtCore.QPoint(10, 10),
        end=QtCore.QPoint(70, 30),
    )
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(40, 20))

    canvas.undo_last_point()
    assert canvas._current is not None
    assert canvas._current.point_labels == (2, 3)
    canvas.undo_last_point()
    assert canvas._current is None


@pytest.mark.gui
def test_ai_segment_box_ends_where_the_mouse_is_released(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.set_ai_model_name(model_name="sam2:small")
    canvas.scale = 1.0
    canvas.set_editing(value=False, create_mode="ai_segment")

    # The last move stops short of the release.
    _drag(
        qtbot=qtbot,
        canvas=canvas,
        start=QtCore.QPoint(10, 10),
        end=QtCore.QPoint(40, 20),
        release=QtCore.QPoint(70, 30),
    )

    assert canvas._current is not None
    assert canvas._current.points == (QPointF(10, 10), QPointF(70, 30))


@pytest.mark.gui
def test_ai_segment_escape_mid_drag_drops_the_box(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.set_ai_model_name(model_name="sam2:small")
    canvas.scale = 1.0
    canvas.set_editing(value=False, create_mode="ai_segment")
    end = QtCore.QPoint(70, 30)
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
    canvas.mouseMoveEvent(
        QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseMove,
            QPointF(end),
            QPointF(end),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    qtbot.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)

    assert canvas._current is None


@pytest.mark.gui
def test_ai_preview_follows_input_without_inference_during_paint(
    *, canvas: Canvas, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts: list[list[list[float]]] = []
    pending_previews: list[list[Shape]] = []
    proposal = AiAssistProposal(
        new_shapes=[
            Shape(
                shape_type="polygon",
                points=np.array([[10, 10], [30, 10], [30, 30]]),
                closed=True,
            )
        ],
        matching_existing_shapes=[],
    )

    def propose_shapes(*, points: np.ndarray, **_: object) -> AiAssistProposal:
        assert not canvas._painter.isActive()
        pending_previews.append(canvas._build_preview_shapes())
        prompts.append(points.tolist())
        return proposal

    monkeypatch.setattr(canvas._ai_assist_session, "propose_shapes", propose_shapes)
    monkeypatch.setattr(canvas, "ensure_ai_model_ready", lambda _: True)
    canvas.set_editing(value=False, create_mode="ai_segment")
    canvas.show()
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
    qtbot.waitUntil(lambda: len(prompts) == 1)
    assert prompts[-1] == [[10, 10]]
    assert canvas._build_preview_shapes() == proposal.new_shapes

    for _ in range(3):
        canvas.grab()
        canvas.update()
        QtCore.QCoreApplication.processEvents()
    canvas.scale = 2
    canvas.grab()
    QtCore.QCoreApplication.processEvents()
    assert len(prompts) == 1

    qtbot.mouseMove(canvas, QtCore.QPoint(40, 40))
    qtbot.waitUntil(lambda: len(prompts) == 2)
    assert prompts[-1] == [[10, 10], [20, 20]]
    assert pending_previews[-1] == proposal.new_shapes

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(40, 40))
    qtbot.waitUntil(lambda: len(prompts) == 3)
    assert prompts[-1] == [[10, 10], [20, 20]]
    canvas.undo_last_point()
    qtbot.waitUntil(lambda: len(prompts) == 4)
    assert prompts[-1] == [[10, 10]]

    # Cancel before queued work runs: no proposal may revive the discarded draft.
    canvas.set_ai_polygon_detail(detail=50)
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    QtCore.QCoreApplication.processEvents()
    canvas.grab()
    assert len(prompts) == 4
    assert canvas._build_preview_shapes() == []


@pytest.mark.gui
@pytest.mark.parametrize(
    "change",
    [
        "model",
        "format",
        "detail",
        "suppression",
        "bounds",
        "brightness",
        "hidden",
        "shapes",
    ],
)
def test_ai_preview_refreshes_when_proposal_inputs_change(
    *,
    canvas: Canvas,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    requests: list[dict[str, object]] = []

    def propose_shapes(**kwargs: object) -> AiAssistProposal:
        requests.append(kwargs)
        return AiAssistProposal(new_shapes=[], matching_existing_shapes=[])

    monkeypatch.setattr(canvas._ai_assist_session, "propose_shapes", propose_shapes)
    monkeypatch.setattr(canvas, "ensure_ai_model_ready", lambda _: True)
    canvas.set_editing(value=False, create_mode="ai_segment")
    canvas.show()
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
    qtbot.waitUntil(lambda: len(requests) == 1)

    if change == "model":
        canvas.set_ai_model_name(model_name="sam:vit_b")
    elif change == "format":
        canvas.set_ai_output_format("mask")
    elif change == "detail":
        canvas.set_ai_polygon_detail(detail=50)
    elif change == "suppression":
        canvas.set_ai_existing_shape_suppression(enabled=True)
    elif change == "bounds":
        canvas.set_allow_out_of_bounds_points(value=True)
    elif change == "shapes":
        canvas.shapes.append(
            Shape(shape_type="rectangle", points=np.array([[0, 0], [10, 10]]))
        )
        canvas.update()
    elif change == "hidden":
        canvas.hide()
        canvas.set_ai_polygon_detail(detail=50)
        canvas.show()
    else:
        pixmap = QtGui.QPixmap(_WIDTH, _HEIGHT)
        pixmap.fill(Qt.GlobalColor.white)
        canvas.load_pixmap(pixmap=pixmap, clear_shapes=False)
    qtbot.waitUntil(lambda: len(requests) == 2)
    if change == "bounds":
        assert requests[-1]["image_size"] is None
    canvas.grab()
    assert len(requests) == 2


@pytest.mark.gui
@pytest.mark.parametrize("outcome", ["empty", "error", "cancel", "reset"])
def test_ai_preview_clears_when_replacement_is_unavailable(
    *, canvas: Canvas, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    proposal = AiAssistProposal(
        new_shapes=[
            Shape(
                shape_type="polygon",
                points=np.array([[10, 10], [30, 10], [30, 30]]),
                closed=True,
            )
        ],
        matching_existing_shapes=[],
    )
    fail = False

    def propose_shapes(**_: object) -> AiAssistProposal:
        if fail:
            raise RuntimeError("inference failed")
        return proposal

    monkeypatch.setattr(canvas._ai_assist_session, "propose_shapes", propose_shapes)
    monkeypatch.setattr(canvas, "ensure_ai_model_ready", lambda _: True)
    canvas.set_editing(value=False, create_mode="ai_segment")
    canvas.show()
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
    qtbot.waitUntil(lambda: bool(canvas._build_preview_shapes()))

    assert canvas._build_preview_shapes() == proposal.new_shapes
    if outcome == "cancel":
        qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    elif outcome == "reset":
        canvas.reset_state()
    else:
        fail = outcome == "error"
        proposal = AiAssistProposal(new_shapes=[], matching_existing_shapes=[])
        canvas.mouseMoveEvent(
            QtGui.QMouseEvent(
                QtCore.QEvent.Type.MouseMove,
                QPointF(20, 20),
                QPointF(20, 20),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        qtbot.waitUntil(lambda: not canvas._build_preview_shapes())
    assert canvas._build_preview_shapes() == []


@pytest.mark.gui
@pytest.mark.parametrize("clear_action", ["empty", "leave", "create"])
def test_hover_transitions_repaint(
    *, canvas: Canvas, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, clear_action: str
) -> None:
    polygon = _make_polygon()
    rotated = _make_oriented_rectangle(
        corners=[(60, 10), (100, 10), (100, 40), (60, 40)]
    )
    canvas.pixmap = QtGui.QPixmap(140, 60)
    canvas.pixmap.fill(Qt.GlobalColor.white)
    canvas.load_shapes(shapes=[polygon, rotated])
    # Keep the desktop pointer from overwriting the scripted hover targets.
    canvas.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    canvas.show()
    qtbot.waitExposed(canvas)
    qtbot.wait(20)
    painted = []
    paint_event = canvas.paintEvent

    def record_paint(event: QtGui.QPaintEvent, /) -> None:
        paint_event(event)
        painted.append(
            tuple(
                canvas._render_context(
                    shape=shape, highlighted=shape is canvas.hovered_shape
                )
                for shape in (polygon, rotated)
            )
        )

    monkeypatch.setattr(canvas, "paintEvent", record_paint)
    for point, shape_index, vertex, rotation in [
        (QPointF(10, 10), 0, 0, None),
        (QPointF(25, 10), 0, None, None),
        (QPointF(25, 25), 0, None, None),
        (QPointF(80, 10), 1, None, 1),
        (QPointF(100, 40), 1, 2, None),
    ]:
        painted.clear()
        canvas._refresh_hover_state(pos=point)
        qtbot.waitUntil(lambda: bool(painted))
        active = painted[-1][shape_index]
        inactive = painted[-1][1 - shape_index]
        assert active.fill
        assert (active.highlight.index if active.highlight else None) == vertex
        assert (
            active.rotation_highlight.index if active.rotation_highlight else None
        ) == rotation
        assert not inactive.fill
        assert inactive.highlight is None
        assert inactive.rotation_highlight is None

    painted.clear()
    if clear_action == "empty":
        canvas._refresh_hover_state(pos=QPointF(130, 50))
    elif clear_action == "leave":
        canvas.leaveEvent(QtCore.QEvent(QtCore.QEvent.Type.Leave))
    else:
        canvas.set_editing(value=False)
    qtbot.waitUntil(lambda: bool(painted))
    assert all(
        not context.fill
        and context.highlight is None
        and context.rotation_highlight is None
        for context in painted[-1]
    )
    if clear_action == "empty":
        painted.clear()
        canvas._refresh_hover_state(pos=QPointF(125, 50))
        qtbot.wait(20)
        assert not painted
    if clear_action == "create":
        painted.clear()
        canvas.set_editing(value=True)
        qtbot.waitUntil(lambda: bool(painted))


def _double_click_canvas(
    *,
    qtbot: QtBot,
    canvas: Canvas,
    image_pos: QPointF,
    button: Qt.MouseButton,
) -> None:
    # A real double-click arrives as press, release, double-click, release.
    pos = canvas.transform_image_point_to_widget(image_pos).toPoint()
    qtbot.mouseMove(canvas, pos)
    qtbot.mouseClick(canvas, button, pos=pos)
    qtbot.mouseDClick(canvas, button, pos=pos)
    qtbot.mouseRelease(canvas, button, pos=pos)


@pytest.fixture()
def editing_canvas(*, qtbot: QtBot, canvas: Canvas) -> Canvas:
    # Hovering needs mouse-move events, which only a shown widget receives.
    with qtbot.waitExposed(canvas):
        canvas.show()
    canvas.load_shapes(shapes=[_make_polygon()])
    # The main window owns the selection and writes it back like this.
    canvas.selection_changed.connect(
        lambda shapes: setattr(canvas, "selected_shapes", shapes)
    )
    return canvas


@pytest.mark.gui
@pytest.mark.parametrize(
    "image_pos",
    [
        pytest.param(QPointF(20.0, 20.0), id="inside"),
        # Just outside the outline, so only the hovered vertex finds the shape.
        pytest.param(QPointF(9.0, 9.0), id="vertex"),
    ],
)
@pytest.mark.parametrize("is_selected", [False, True])
def test_double_click_shape_selects_it_and_emits_signal(
    *, qtbot: QtBot, editing_canvas: Canvas, image_pos: QPointF, is_selected: bool
) -> None:
    canvas = editing_canvas
    shape = canvas.shapes[0]
    if is_selected:
        canvas.select_shapes(shapes=[shape])
    emitted = Mock()
    canvas.shape_double_clicked.connect(emitted)

    _double_click_canvas(
        qtbot=qtbot,
        canvas=canvas,
        image_pos=image_pos,
        button=Qt.MouseButton.LeftButton,
    )

    emitted.assert_called_once_with()
    assert canvas.selected_shapes == [shape]


@pytest.mark.gui
def test_double_click_vertex_selects_its_shape_not_the_enclosing_one(
    *, qtbot: QtBot, editing_canvas: Canvas
) -> None:
    canvas = editing_canvas
    inner = _make_polygon()
    outer = Shape(
        shape_type="rectangle",
        points=np.array([(0, 0), (50, 50)], dtype=np.float64),
        closed=True,
    )
    canvas.load_shapes(shapes=[inner, outer])

    _double_click_canvas(
        qtbot=qtbot,
        canvas=canvas,
        image_pos=QPointF(10.0, 10.0),
        button=Qt.MouseButton.LeftButton,
    )

    assert canvas.selected_shapes == [inner]


@pytest.mark.gui
@pytest.mark.parametrize(
    ("image_pos", "button"),
    [
        pytest.param(QPointF(80.0, 40.0), Qt.MouseButton.LeftButton, id="empty"),
        pytest.param(QPointF(20.0, 20.0), Qt.MouseButton.MiddleButton, id="middle"),
    ],
)
def test_double_click_does_not_emit_signal(
    *,
    qtbot: QtBot,
    editing_canvas: Canvas,
    image_pos: QPointF,
    button: Qt.MouseButton,
) -> None:
    canvas = editing_canvas
    emitted = Mock()
    canvas.shape_double_clicked.connect(emitted)

    _double_click_canvas(qtbot=qtbot, canvas=canvas, image_pos=image_pos, button=button)

    emitted.assert_not_called()


@pytest.mark.gui
def test_double_click_in_create_mode_finalizes_shape(
    *, qtbot: QtBot, canvas: Canvas
) -> None:
    canvas.set_editing(value=False)
    canvas.create_mode = "polygon"
    canvas._current = _DraftShape(
        points=(QPointF(10.0, 10.0), QPointF(30.0, 10.0), QPointF(20.0, 30.0)),
        point_labels=(1, 1, 1),
    )
    emitted = Mock()
    canvas.shape_double_clicked.connect(emitted)

    pos = canvas.transform_image_point_to_widget(QPointF(20.0, 30.0)).toPoint()
    qtbot.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=pos)

    emitted.assert_not_called()
    assert canvas._current is None
    assert len(canvas.shapes) == 1


def _mouse_event(
    *,
    canvas: Canvas,
    kind: QtCore.QEvent.Type,
    image_pos: QPointF,
    buttons: Qt.MouseButton,
) -> QtGui.QMouseEvent:
    pos = canvas.transform_image_point_to_widget(image_pos)
    button = Qt.MouseButton.NoButton
    if kind != QtCore.QEvent.Type.MouseMove:
        button = Qt.MouseButton.LeftButton
    return QtGui.QMouseEvent(
        kind, pos, pos, button, buttons, Qt.KeyboardModifier.NoModifier
    )


@pytest.mark.gui
def test_dragging_point_inside_box_commits_move(*, editing_canvas: Canvas) -> None:
    canvas = editing_canvas
    box = Shape(
        shape_type="rectangle",
        points=np.array([(5, 5), (80, 45)], dtype=np.float64),
    )
    point = Shape(shape_type="point", points=np.array([(40, 25)], dtype=np.float64))
    canvas.load_shapes(shapes=[box, point])
    moved = Mock()
    canvas.shape_moved.connect(moved)

    move = QtCore.QEvent.Type.MouseMove
    no_button = Qt.MouseButton.NoButton
    left = Qt.MouseButton.LeftButton
    # Entering the point from the box body hovers the point, not the box.
    canvas.mouseMoveEvent(
        _mouse_event(
            canvas=canvas, kind=move, image_pos=QPointF(20, 20), buttons=no_button
        )
    )
    assert canvas.hovered_shape is box
    canvas.mouseMoveEvent(
        _mouse_event(
            canvas=canvas, kind=move, image_pos=QPointF(40, 25), buttons=no_button
        )
    )
    assert canvas.hovered_shape is point
    canvas.mousePressEvent(
        _mouse_event(
            canvas=canvas,
            kind=QtCore.QEvent.Type.MouseButtonPress,
            image_pos=QPointF(40, 25),
            buttons=left,
        )
    )
    canvas.mouseMoveEvent(
        _mouse_event(canvas=canvas, kind=move, image_pos=QPointF(90, 40), buttons=left)
    )
    canvas.mouseReleaseEvent(
        _mouse_event(
            canvas=canvas,
            kind=QtCore.QEvent.Type.MouseButtonRelease,
            image_pos=QPointF(90, 40),
            buttons=no_button,
        )
    )

    np.testing.assert_array_equal(point.points, [[90, 40]])
    moved.assert_called_once()
    np.testing.assert_array_equal(canvas.shape_backups[-1][1].points, [[90, 40]])


@pytest.mark.gui
@pytest.mark.parametrize(
    "kind",
    [QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseButtonDblClick],
    ids=["press", "double_click"],
)
def test_click_on_rotation_handle_selects_its_shape(
    *, editing_canvas: Canvas, kind: QtCore.QEvent.Type
) -> None:
    canvas = editing_canvas
    # The point sits under the rectangle's top rotation handle at (50, 10).
    point = Shape(shape_type="point", points=np.array([(50, 12)], dtype=np.float64))
    rectangle = _make_oriented_rectangle(
        corners=[(20, 10), (80, 10), (80, 40), (20, 40)]
    )
    canvas.load_shapes(shapes=[point, rectangle])
    handle = QPointF(50, 10)
    canvas.mouseMoveEvent(
        _mouse_event(
            canvas=canvas,
            kind=QtCore.QEvent.Type.MouseMove,
            image_pos=handle,
            buttons=Qt.MouseButton.NoButton,
        )
    )
    assert canvas.hovered_shape is rectangle
    assert canvas._hovered_rotation is not None

    event = _mouse_event(
        canvas=canvas,
        kind=kind,
        image_pos=handle,
        buttons=Qt.MouseButton.LeftButton,
    )
    if kind == QtCore.QEvent.Type.MouseButtonDblClick:
        canvas.mouseDoubleClickEvent(event)
    else:
        canvas.mousePressEvent(event)

    assert canvas.selected_shapes == [rectangle]


def _start_ai_box_finalize(canvas: Canvas, /) -> _DraftShape:
    canvas.set_ai_output_format("rectangle")
    _worker(canvas).annotations = [
        osam.types.Annotation(
            score=0.9,
            bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=10, ymax=10),
        )
    ]
    _worker(canvas).paused = True
    canvas.set_editing(value=False, create_mode="ai_segment")
    draft = _DraftShape(
        shape_type="points",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(2, 3),
    )
    canvas._current = draft
    canvas._finalize()
    return draft


@pytest.mark.gui
def test_ai_finalize_ignores_input_until_the_result_lands(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    draft = _start_ai_box_finalize(canvas)
    new_shapes: list[None] = []
    canvas.new_shape.connect(lambda: new_shapes.append(None))

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(50, 50))

    assert canvas.is_ai_finalizing
    assert canvas._current is draft
    assert canvas.shapes == []
    _worker(canvas).resume()
    assert not canvas.is_ai_finalizing
    assert [shape.shape_type for shape in canvas.shapes] == ["rectangle"]
    assert new_shapes == [None]


@pytest.mark.gui
@pytest.mark.parametrize("abandon", ["escape", "reset"])
def test_ai_finalize_drops_a_result_for_an_abandoned_draft(
    *, canvas: Canvas, qtbot: QtBot, abandon: str
) -> None:
    _start_ai_box_finalize(canvas)
    if abandon == "escape":
        qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    else:
        canvas.reset_state()

    assert not canvas.is_ai_finalizing
    _worker(canvas).resume()
    assert canvas.shapes == []


@pytest.mark.gui
def test_ai_finalize_cancels_its_draft_when_the_pixmap_changes(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    _start_ai_box_finalize(canvas)
    canvas.load_pixmap(pixmap=QtGui.QPixmap(100, 50), clear_shapes=False)

    _worker(canvas).resume()

    assert canvas.shapes == []
    assert canvas._current is None
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.show()
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(5, 5))
    assert canvas._current is not None
    assert len(canvas._current.points) == 1


@pytest.mark.gui
def test_ai_finalize_reports_drawing_and_unblocks_when_its_draft_drops(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    drawing: list[bool] = []
    canvas.busy_changed.connect(lambda: drawing.append(canvas.is_busy))
    _start_ai_box_finalize(canvas)
    assert drawing == [True]  # the app disables Undo from here

    canvas.load_shapes(shapes=[])  # what Undo does, had it stayed enabled

    assert not canvas.is_ai_finalizing
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.show()
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(5, 5))
    assert canvas._current is not None
    _worker(canvas).resume()
    assert canvas.shapes == []


@pytest.mark.gui
def test_ai_finalize_ignores_undo_last_point(*, canvas: Canvas) -> None:
    # The Undo Last Point action calls this directly, past the input guards.
    draft = _start_ai_box_finalize(canvas)

    canvas.undo_last_point()

    assert canvas._current is draft
    _worker(canvas).resume()
    assert [shape.shape_type for shape in canvas.shapes] == ["rectangle"]


@pytest.mark.gui
def test_ai_preview_drops_a_result_for_old_inputs(
    *, canvas: Canvas, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[object] = []

    def propose(*, job: object, **_: object) -> AiAssistProposal:
        shown.append(getattr(job, "preview_key"))  # noqa: B009 -- job is typed object
        return AiAssistProposal(new_shapes=[], matching_existing_shapes=[])

    monkeypatch.setattr(canvas, "_propose_ai_shapes", propose)
    _worker(canvas).paused = True
    canvas.create_mode = "ai_segment"
    canvas._current = _DraftShape(
        shape_type="polygon", points=(QPointF(1, 1),), point_labels=(1,)
    )
    for x in (5, 6):
        canvas._line = _DraftShape(
            shape_type="polygon",
            points=(QPointF(1, 1), QPointF(x, x)),
            point_labels=(1, 1),
        )
        canvas._refresh_ai_segment_preview()

    _worker(canvas).resume()

    assert shown == [canvas._ai_segment_preview_key]


@pytest.mark.gui
def test_ai_segment_preview_waits_while_finalizing(*, canvas: Canvas) -> None:
    # A Ctrl+click finalizes on the first point, before any preview segment.
    _worker(canvas).paused = True
    canvas.set_editing(value=False, create_mode="ai_segment")
    canvas._current = _DraftShape(
        shape_type="polygon", points=(QPointF(1, 1),), point_labels=(1,)
    )
    canvas._line = _DraftShape(shape_type="polygon")
    canvas._finalize()

    canvas._refresh_ai_segment_preview()

    assert len(_worker(canvas).requests) == 1


@pytest.mark.gui
def test_ai_find_all_box_rejects_text_only_model_before_loading(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    loaded: list[str] = []
    canvas.ensure_ai_model_ready = lambda name: loaded.append(name) or True
    canvas.get_ai_find_all_model_name = lambda: "yoloworld:latest"
    canvas.set_editing(value=False, create_mode="ai_find_all")
    canvas.show()

    with qtbot.waitSignal(canvas.example_box_unsupported):
        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))

    assert loaded == []
    assert canvas._current is None
    assert _worker(canvas).requests == []


@pytest.mark.gui
def test_ai_find_all_box_uses_the_ai_find_all_model(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    loaded: list[str] = []
    canvas.ensure_ai_model_ready = lambda name: loaded.append(name) or True
    canvas.get_ai_find_all_model_name = lambda: "sam3:latest"
    canvas.set_editing(value=False, create_mode="ai_find_all")
    canvas.show()

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(40, 40))

    assert loaded == ["sam3:latest"]
    qtbot.waitUntil(lambda: bool(_worker(canvas).requests))
    assert {r.model_name for r in _worker(canvas).requests} == {"sam3:latest"}
    point_labels = _worker(canvas).requests[-1].point_labels
    assert point_labels is not None
    assert point_labels.tolist() == [2, 3]
    assert _worker(canvas).requests[-1].texts == ["visual"]


@pytest.mark.gui
def test_ai_find_all_box_rechecks_the_model_at_the_second_corner(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    model_name = "sam3:latest"
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.get_ai_find_all_model_name = lambda: model_name
    canvas.set_editing(value=False, create_mode="ai_find_all")
    canvas.show()
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))

    model_name = "yoloworld:latest"
    with qtbot.waitSignal(canvas.example_box_unsupported):
        qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(40, 40))

    assert canvas._current is None
    assert _worker(canvas).requests == []


@pytest.mark.gui
def test_ai_find_all_box_applies_the_score_threshold(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.get_ai_find_all_model_name = lambda: "sam3:latest"
    canvas.get_ai_find_all_thresholds = lambda: (0.5, 0.5)
    canvas.set_ai_output_format("rectangle")
    _worker(canvas).annotations = [
        osam.types.Annotation(
            bounding_box=osam.types.BoundingBox(xmin=x, ymin=5, xmax=x + 10, ymax=20),
            score=score,
        )
        for x, score in [(5, 0.9), (40, 0.1)]
    ]
    canvas.set_editing(value=False, create_mode="ai_find_all")
    canvas.show()

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(5, 5))
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(15, 20))

    assert len(canvas._ai_find_all_draft) == 1


@pytest.mark.gui
def test_ai_box_sends_the_box_without_text(*, canvas: Canvas, qtbot: QtBot) -> None:
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.set_editing(value=False, create_mode="ai_segment")
    canvas.show()

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(40, 40))

    qtbot.waitUntil(lambda: bool(_worker(canvas).requests))
    assert _worker(canvas).requests[-1].texts is None


@pytest.mark.gui
def test_ai_find_all_box_detects_with_the_query(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.get_ai_find_all_model_name = lambda: "sam3:latest"
    canvas.get_ai_find_all_query = lambda: "dog"
    canvas.set_editing(value=False, create_mode="ai_find_all")
    canvas.show()

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(40, 40))

    assert _worker(canvas).requests[-1].texts == ["dog"]


@pytest.mark.gui
def test_ai_find_all_box_labels_results_with_the_query_it_sent(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.get_ai_find_all_model_name = lambda: "sam3:latest"
    canvas.get_ai_find_all_query = lambda: "person"
    canvas.set_ai_output_format("rectangle")
    canvas.set_editing(value=False, create_mode="ai_find_all")
    canvas.show()
    worker = _worker(canvas)
    worker.annotations = [
        osam.types.Annotation(
            bounding_box=osam.types.BoundingBox(xmin=10, ymin=10, xmax=40, ymax=40),
            score=0.9,
        )
    ]
    worker.paused = True
    queries: list[str] = []
    canvas.ai_find_all_draft_committed.connect(
        lambda _shapes, _propose, query: queries.append(query)
    )

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(40, 40))
    canvas.get_ai_find_all_query = lambda: "dog"  # Edited during inference.
    worker.resume()
    qtbot.keyClick(canvas, Qt.Key.Key_Return)

    assert queries == ["person"]


def _ai_find_all_canvas(canvas: Canvas, /) -> Canvas:
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.get_ai_find_all_model_name = lambda: "sam3:latest"
    canvas.set_ai_output_format("rectangle")
    _worker(canvas).annotations = [
        osam.types.Annotation(
            bounding_box=osam.types.BoundingBox(xmin=x, ymin=5, xmax=x + 10, ymax=20),
            score=0.9,
        )
        for x in (5, 40)
    ]
    canvas.set_editing(value=False, create_mode="ai_find_all")
    canvas.show()
    return canvas


def _draw_box(
    canvas: Canvas,
    /,
    *,
    corners: tuple[tuple[int, int], tuple[int, int]],
    modifier: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    # Delivered directly: a synthesized move can land after the click under
    # load, and the box takes its second corner from the last move.
    for x, y in corners:
        pos = QPointF(x, y)
        for kind, button, buttons, handler in (
            (
                QtCore.QEvent.Type.MouseMove,
                Qt.MouseButton.NoButton,
                Qt.MouseButton.NoButton,
                canvas.mouseMoveEvent,
            ),
            (
                QtCore.QEvent.Type.MouseButtonPress,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                canvas.mousePressEvent,
            ),
            (
                QtCore.QEvent.Type.MouseButtonRelease,
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                canvas.mouseReleaseEvent,
            ),
        ):
            handler(QtGui.QMouseEvent(kind, pos, pos, button, buttons, modifier))


@pytest.mark.gui
def test_ai_find_all_counter_example_reruns_with_every_box(*, canvas: Canvas) -> None:
    _ai_find_all_canvas(canvas)

    _draw_box(canvas, corners=((5, 5), (15, 20)))
    _draw_box(
        canvas,
        corners=((50, 20), (40, 5)),
        modifier=Qt.KeyboardModifier.ShiftModifier,
    )

    request = _worker(canvas).requests[-1]
    assert request.points is not None
    assert request.point_labels is not None
    assert request.texts == ["visual"]
    assert request.point_labels.tolist() == [2, 3, 4, 5]
    assert request.points.tolist() == [[5, 5], [15, 20], [40, 5], [50, 20]]
    assert canvas.shapes == []
    assert len(canvas._ai_find_all_draft) == 2  # The latest run replaced the first.


@pytest.mark.gui
def test_ai_find_all_takes_dragged_boxes(*, canvas: Canvas, qtbot: QtBot) -> None:
    _ai_find_all_canvas(canvas)

    # The release lands past the last move and sets the opposite corner.
    _drag(
        qtbot=qtbot,
        canvas=canvas,
        start=QtCore.QPoint(5, 5),
        end=QtCore.QPoint(12, 15),
        release=QtCore.QPoint(15, 20),
    )
    _drag(
        qtbot=qtbot,
        canvas=canvas,
        start=QtCore.QPoint(40, 5),
        end=QtCore.QPoint(50, 20),
        modifier=Qt.KeyboardModifier.ShiftModifier,
    )

    request = _worker(canvas).requests[-1]
    assert request.points is not None
    assert request.point_labels is not None
    assert request.point_labels.tolist() == [2, 3, 4, 5]
    assert request.points.tolist() == [[5, 5], [15, 20], [40, 5], [50, 20]]
    assert canvas._current is None


@pytest.mark.gui
def test_ai_find_all_drag_past_the_image_edge_finishes_the_box(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    _ai_find_all_canvas(canvas)

    # The corner stops at the edge, but the pointer moved past the drag distance.
    _drag(
        qtbot=qtbot,
        canvas=canvas,
        start=QtCore.QPoint(_WIDTH - 2, 5),
        end=QtCore.QPoint(_WIDTH + 50, 40),
    )

    assert canvas._current is None
    assert _worker(canvas).requests


@pytest.mark.gui
def test_ai_find_all_click_waits_for_the_second_corner(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    _ai_find_all_canvas(canvas)

    # A press that moves less than the drag distance is a click.
    _drag(
        qtbot=qtbot, canvas=canvas, start=QtCore.QPoint(5, 5), end=QtCore.QPoint(6, 5)
    )

    assert canvas._current is not None
    assert _worker(canvas).requests == []


@pytest.mark.gui
def test_ai_find_all_enter_commits_the_draft_as_one_step(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    _ai_find_all_canvas(canvas)
    backups = len(canvas.shape_backups)
    queries: list[str] = []

    def add(
        draft: list[Shape], propose: Callable[[str], list[Shape]], query: str
    ) -> None:
        queries.append(query)
        assert len(propose("dog")) == len(draft)  # No "dog" Shapes yet.
        canvas.load_shapes(shapes=propose("dog"), replace=False)  # As the app does.

    canvas.ai_find_all_draft_committed.connect(add)

    _draw_box(canvas, corners=((5, 5), (15, 20)))
    qtbot.keyClick(canvas, Qt.Key.Key_Return)

    assert len(canvas.shapes) == 2
    assert len(canvas.shape_backups) == backups + 1
    assert queries == [""]
    assert not canvas.has_ai_find_all_draft


def _commit_draft_proposals(
    canvas: Canvas, qtbot: QtBot, /, *, label: str
) -> list[Shape]:
    proposed: list[Shape] = []
    canvas.ai_find_all_draft_committed.connect(
        lambda _draft, propose, _query: proposed.extend(propose(label))
    )
    qtbot.keyClick(canvas, Qt.Key.Key_Return)
    return proposed


@pytest.mark.gui
def test_ai_find_all_commit_keeps_the_settings_the_draft_showed(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    _ai_find_all_canvas(canvas)
    _draw_box(canvas, corners=((5, 5), (15, 20)))

    canvas.set_ai_output_format("polygon")  # Changed with the draft shown.

    proposed = _commit_draft_proposals(canvas, qtbot, label="dog")
    assert [s.shape_type for s in proposed] == ["rectangle", "rectangle"]


@pytest.mark.gui
def test_ai_find_all_commit_skips_only_the_label_and_output_it_covers(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    _ai_find_all_canvas(canvas)
    for label, shape_type in (("dog", "polygon"), ("cat", "rectangle")):
        canvas.shapes.append(
            Shape(
                label=label,
                shape_type=shape_type,
                points=np.array([(5.0, 5.0), (15.0, 5.0), (15.0, 20.0), (5.0, 20.0)])
                if shape_type == "polygon"
                else np.array([(5.0, 5.0), (15.0, 20.0)]),
            )
        )
    canvas.shapes.append(
        Shape(
            label="dog",
            shape_type="rectangle",
            points=np.array([(40.0, 5.0), (50.0, 20.0)]),
        )
    )
    _draw_box(canvas, corners=((5, 5), (15, 20)))

    proposed = _commit_draft_proposals(canvas, qtbot, label="dog")
    # Only the dog rectangle covers; the dog polygon and the cat do not.
    assert [s.points[0, 0] for s in proposed] == [5]


@pytest.mark.gui
def test_ai_find_all_escape_discards_the_draft(*, canvas: Canvas, qtbot: QtBot) -> None:
    _ai_find_all_canvas(canvas)

    _draw_box(canvas, corners=((5, 5), (15, 20)))
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)

    assert canvas.shapes == []
    assert not canvas.has_ai_find_all_draft


@pytest.mark.gui
def test_ai_find_all_draft_clears_on_image_change(*, canvas: Canvas) -> None:
    _ai_find_all_canvas(canvas)
    _draw_box(canvas, corners=((5, 5), (15, 20)))

    canvas.load_pixmap(pixmap=QtGui.QPixmap(_WIDTH, _HEIGHT))
    _draw_box(canvas, corners=((5, 5), (15, 20)))

    point_labels = _worker(canvas).requests[-1].point_labels
    assert point_labels is not None
    assert point_labels.tolist() == [2, 3]


@pytest.mark.gui
def test_ai_find_all_rerun_replaces_the_draft_with_the_current_query(
    *, canvas: Canvas
) -> None:
    _ai_find_all_canvas(canvas)
    _draw_box(canvas, corners=((5, 5), (15, 20)))
    canvas.get_ai_find_all_query = lambda: "person"
    _worker(canvas).annotations = _worker(canvas).annotations[:1]

    canvas.rerun_ai_find_all_draft()

    request = _worker(canvas).requests[-1]
    assert request.texts == ["person"]
    assert request.point_labels is not None
    assert request.point_labels.tolist() == [2, 3]
    assert canvas.shapes == []
    assert len(canvas._ai_find_all_draft) == 1


@pytest.mark.gui
def test_ai_find_all_rerun_result_is_dropped_after_a_tool_switch(
    *, canvas: Canvas
) -> None:
    _ai_find_all_canvas(canvas)
    _draw_box(canvas, corners=((5, 5), (15, 20)))
    _worker(canvas).paused = True
    canvas.rerun_ai_find_all_draft()

    canvas.set_editing(value=False, create_mode="rectangle")
    _worker(canvas).resume()

    assert not canvas.has_ai_find_all_draft
    assert not canvas.is_ai_finalizing


@pytest.mark.gui
def test_ai_find_all_draft_holds_other_shape_changes(*, canvas: Canvas) -> None:
    _ai_find_all_canvas(canvas)

    _draw_box(canvas, corners=((5, 5), (15, 20)))

    assert canvas.is_interacting


@pytest.mark.gui
def test_ai_find_all_escape_discards_the_draft_during_a_rerun(
    *, canvas: Canvas, qtbot: QtBot
) -> None:
    _ai_find_all_canvas(canvas)
    _draw_box(canvas, corners=((5, 5), (15, 20)))
    _worker(canvas).paused = True
    canvas.rerun_ai_find_all_draft()

    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    _worker(canvas).resume()

    assert not canvas.has_ai_find_all_draft
    assert not canvas.is_ai_finalizing


@pytest.mark.gui
def test_ai_find_all_draft_is_discarded_when_shapes_change(*, canvas: Canvas) -> None:
    _ai_find_all_canvas(canvas)
    canvas.shapes.append(
        Shape(shape_type="rectangle", points=np.array([(0.0, 0.0), (1.0, 1.0)]))
    )
    canvas.backup_shapes()
    canvas.backup_shapes()
    _draw_box(canvas, corners=((5, 5), (15, 20)))
    assert canvas.has_ai_find_all_draft

    canvas.restore_last_shape()

    assert not canvas.has_ai_find_all_draft


@pytest.mark.gui
def test_ai_find_all_clearing_the_draft_drops_a_pending_box(*, canvas: Canvas) -> None:
    _ai_find_all_canvas(canvas)
    _draw_box(canvas, corners=((5, 5), (15, 20)))
    _worker(canvas).paused = True
    _draw_box(canvas, corners=((40, 5), (50, 20)))

    canvas.backup_shapes()  # Any Shape change, such as toggling visibility.
    _worker(canvas).resume()

    assert not canvas.has_ai_find_all_draft
    assert not canvas.is_ai_finalizing
    assert not canvas.is_drawing


def _hint_texts(canvas: Canvas, /) -> list[list[str]] | None:
    hint = canvas._ai_suggestion_hint()
    if hint is None:
        return None
    return [[item.text for item in row] for row in hint[1]]


@pytest.mark.gui
def test_ai_segment_hint_shows_while_a_suggestion_waits(*, canvas: Canvas) -> None:
    canvas.set_editing(value=False, create_mode="ai_segment")
    canvas._current = _DraftShape(
        shape_type="points", points=(QPointF(20, 20),), point_labels=(1,)
    )
    assert _hint_texts(canvas) is None  # The first preview has not landed.

    canvas._ai_segment_preview = [
        Shape(
            shape_type="polygon",
            points=np.array([[10, 10], [30, 10], [30, 30]], dtype=np.float64),
            closed=True,
        )
    ]
    assert _hint_texts(canvas) == [
        ["Add", "Discard"],
        ["Click to include", "Click to exclude"],
    ]

    canvas._ai_segment_dragging = True
    assert _hint_texts(canvas) is None
    canvas._ai_segment_dragging = False

    canvas.set_editing(value=False, create_mode="polygon")
    assert _hint_texts(canvas) is None


@pytest.mark.gui
def test_ai_find_all_hint_counts_the_results(*, canvas: Canvas) -> None:
    _ai_find_all_canvas(canvas)
    assert _hint_texts(canvas) is None

    _draw_box(canvas, corners=((5, 5), (15, 20)))

    assert _hint_texts(canvas) == [["Add 2", "Discard"], ["Drag to exclude"]]
    canvas._current = _DraftShape(
        shape_type="rectangle", points=(QPointF(40, 5),), point_labels=(1,)
    )
    assert _hint_texts(canvas) is None  # A box being drawn.
    canvas._current = None
    canvas.set_ai_find_all_pending(canvas._ai_find_all_draft)
    assert _hint_texts(canvas) is None  # The label dialog is open.


@pytest.mark.gui
def test_ai_hint_stays_in_the_visible_part_of_a_zoomed_canvas(
    *, canvas: Canvas, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    rects: list[QtCore.QRectF] = []
    monkeypatch.setattr(
        "labelme._widgets._canvas.paint_hint_chip",
        lambda _painter, *, rect, **_: rects.append(rect),
    )
    scroll = QtWidgets.QScrollArea()
    qtbot.addWidget(scroll)
    scroll.setWidget(canvas)
    scroll.resize(300, 200)
    canvas.scale = 10.0  # The 100x50 image is 1000x500 on screen.
    canvas.adjustSize()
    scroll.show()
    canvas.set_editing(value=False, create_mode="ai_segment")
    canvas._current = _DraftShape(
        shape_type="points", points=(QPointF(5, 5),), point_labels=(1,)
    )
    # The suggestion's bottom edge sits at the bottom of the visible part.
    canvas._ai_segment_preview = [
        Shape(
            shape_type="polygon",
            points=np.array([[2, 2], [10, 2], [10, 18]], dtype=np.float64),
            closed=True,
        )
    ]

    qtbot.waitExposed(scroll)
    canvas.grab()

    visible = QtCore.QRectF(canvas.visibleRegion().boundingRect())
    assert visible.height() < canvas.height()
    assert rects
    assert visible.contains(rects[-1])
    scroll.takeWidget()  # The fixture owns the canvas.


@pytest.mark.gui
@pytest.mark.parametrize("mode", ["ai_segment", "ai_find_all"])
def test_ai_hint_anchors_under_the_drawn_circle(*, canvas: Canvas, mode: str) -> None:
    canvas.set_editing(value=False, create_mode=mode)
    # Center (50, 20), rim (60, 20): the circle reaches down to y=30.
    circle = Shape(shape_type="circle", points=np.array([[50.0, 20.0], [60.0, 20.0]]))
    if mode == "ai_segment":
        canvas._current = _DraftShape(
            shape_type="points", points=(QPointF(50, 20),), point_labels=(1,)
        )
        canvas._ai_segment_preview = [circle]
    else:
        canvas._ai_find_all_draft = [circle]
        canvas._ai_find_all_points = np.array([[45.0, 15.0], [55.0, 25.0]])
        canvas._ai_find_all_point_labels = np.array([2, 3])

    hint = canvas._ai_suggestion_hint()

    assert hint is not None
    (_, top), (_, bottom) = ((p.x(), p.y()) for p in hint[0])
    assert (top, bottom) == pytest.approx((10.0, 30.0))


def _painted_hint_texts(
    canvas: Canvas, monkeypatch: pytest.MonkeyPatch, /
) -> list[list[str]] | None:
    painted: list[list[list[str]]] = []
    monkeypatch.setattr(
        "labelme._widgets._canvas.paint_hint_chip",
        lambda _painter, *, lines, **_: painted.append(
            [[item.text for line in row for item in line] for row in lines]
        ),
    )
    canvas.grab()
    return painted[-1] if painted else None


@pytest.mark.gui
@pytest.mark.parametrize(
    ("mode", "texts"),
    [
        ("ai_segment", [["Click to include", "Click to exclude", "Drag a box"]]),
        ("ai_find_all", [["Drag around one example"]]),
    ],
)
def test_ai_prompt_hint_shows_until_the_first_prompt(
    *,
    canvas: Canvas,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    texts: list[list[str]],
) -> None:
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.resize(640, 400)  # Wide enough for one line in any font.
    canvas.show()
    canvas.set_editing(value=False, create_mode=mode)
    assert _painted_hint_texts(canvas, monkeypatch) == texts

    pos = canvas.transform_image_point_to_widget(QPointF(20, 20)).toPoint()
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=pos)
    assert _painted_hint_texts(canvas, monkeypatch) is None

    canvas.set_editing(value=False, create_mode="polygon")
    assert _painted_hint_texts(canvas, monkeypatch) is None
    canvas.set_editing(value=False, create_mode=mode)
    assert _painted_hint_texts(canvas, monkeypatch) == texts


@pytest.mark.gui
def test_ai_prompt_hint_yields_to_a_waiting_suggestion(
    *, canvas: Canvas, monkeypatch: pytest.MonkeyPatch
) -> None:
    canvas.set_editing(value=False, create_mode="ai_segment")
    canvas._current = _DraftShape(
        shape_type="points", points=(QPointF(20, 20),), point_labels=(1,)
    )
    canvas._ai_segment_preview = [
        Shape(
            shape_type="polygon",
            points=np.array([[10, 10], [30, 10], [30, 30]], dtype=np.float64),
            closed=True,
        )
    ]

    hint = _painted_hint_texts(canvas, monkeypatch)
    assert hint is not None
    assert hint[0] == ["Add", "Discard"]


@pytest.mark.gui
def test_ai_prompt_hint_wraps_inside_a_narrow_view(
    *, canvas: Canvas, monkeypatch: pytest.MonkeyPatch
) -> None:
    rects: list[QtCore.QRectF] = []
    monkeypatch.setattr(
        "labelme._widgets._canvas.paint_hint_chip",
        lambda _painter, *, rect, **_: rects.append(rect),
    )
    canvas.resize(240, 240)  # Narrow, but tall enough for the wrapped lines.
    canvas.set_editing(value=False, create_mode="ai_segment")

    canvas.grab()

    assert rects
    assert QtCore.QRectF(canvas.rect()).contains(rects[-1])


@pytest.mark.gui
def test_ai_prompt_hint_repaints_when_the_tool_is_picked_again(
    *, canvas: Canvas, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    canvas.ensure_ai_model_ready = lambda _: True
    canvas.show()
    qtbot.waitExposed(canvas)
    canvas.set_editing(value=False, create_mode="ai_segment")
    qtbot.mousePress(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(20, 20))
    qtbot.keyClick(canvas, Qt.Key.Key_Escape)
    QtWidgets.QApplication.processEvents()
    painted: list[QtGui.QPaintEvent] = []
    monkeypatch.setattr(canvas, "paintEvent", painted.append)

    canvas.set_editing(value=False, create_mode="ai_segment")

    qtbot.waitUntil(lambda: bool(painted))


@pytest.mark.gui
@pytest.mark.parametrize("mode", ["ai_segment", "ai_find_all"])
def test_ai_prompt_hint_fits_a_narrow_view_in_a_long_translation(
    *, canvas: Canvas, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    translator = QtCore.QTranslator()
    assert translator.load(
        str(Path(labelme.__file__).parent / "translate" / "pl_PL.qm")
    )
    QtCore.QCoreApplication.installTranslator(translator)
    rects: list[QtCore.QRectF] = []
    monkeypatch.setattr(
        "labelme._widgets._canvas.paint_hint_chip",
        lambda _painter, *, rect, **_: rects.append(rect),
    )
    canvas.resize(240, 240)  # Narrow, but tall enough for the wrapped lines.
    canvas.set_editing(value=False, create_mode=mode)

    try:
        canvas.grab()
    finally:
        QtCore.QCoreApplication.removeTranslator(translator)

    assert rects
    assert QtCore.QRectF(canvas.rect()).contains(rects[-1])
