from __future__ import annotations

import dataclasses
import math
from typing import Final
from unittest.mock import Mock

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
from labelme.widgets.canvas import _reproject_oriented_rectangle_corners

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
def test_bounded_move_vertex_clamps_to_image_by_default(canvas: Canvas) -> None:
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
def test_bounded_move_vertex_keeps_out_of_bounds_when_enabled(canvas: Canvas) -> None:
    canvas.set_allow_out_of_bounds_points(True)
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


@pytest.mark.gui
def test_drag_shapes_blocked_off_image_by_default(canvas: Canvas) -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(40, 20), (60, 30)], dtype=np.float64),
        closed=True,
    )
    canvas._prev_point = QPointF(50, 25)
    canvas._drag_anchor = (QPointF(0, 0), QtCore.QRectF(40, 20, 20, 10))

    moved = canvas._drag_shapes(shapes=[shape], cursor=QPointF(150, 80))

    assert moved is False
    assert (shape.points[0][0], shape.points[0][1]) == pytest.approx((40, 20))
    assert (shape.points[1][0], shape.points[1][1]) == pytest.approx((60, 30))


@pytest.mark.gui
def test_drag_shapes_keeps_out_of_bounds_when_enabled(canvas: Canvas) -> None:
    canvas.set_allow_out_of_bounds_points(True)
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(40, 20), (60, 30)], dtype=np.float64),
        closed=True,
    )
    canvas._prev_point = QPointF(50, 25)
    canvas._drag_anchor = (QPointF(0, 0), QtCore.QRectF(40, 20, 20, 10))

    moved = canvas._drag_shapes(shapes=[shape], cursor=QPointF(150, 80))

    assert moved is True
    assert (shape.points[0][0], shape.points[0][1]) == pytest.approx((140, 75))
    assert (shape.points[1][0], shape.points[1][1]) == pytest.approx((160, 85))


@pytest.mark.gui
def test_should_draw_crosshair_off_image_when_out_of_bounds_allowed(
    canvas: Canvas,
) -> None:
    canvas.set_allow_out_of_bounds_points(True)
    canvas._crosshair[canvas._create_mode] = True
    canvas.set_editing(False)

    assert canvas._should_draw_crosshair(cursor=QPointF(_WIDTH + 20, _HEIGHT + 20))


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
    monkeypatch.setattr(canvas, "_build_new_shapes_from_ai_inference", lambda: [])
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


def _raise_inference_error(**_: object) -> list[Shape]:
    raise RuntimeError("broken model")


@pytest.fixture()
def broken_inference(
    canvas: Canvas, monkeypatch: pytest.MonkeyPatch
) -> tuple[Canvas, list[str]]:
    monkeypatch.setattr(
        canvas._ai_assist_session, "propose_shapes", _raise_inference_error
    )
    failures: list[str] = []
    canvas.inference_failed.connect(failures.append)
    return canvas, failures


def _drive_ai_preview(canvas: Canvas) -> Shape:
    # The hover preview runs inference inside paintEvent via this method; drive
    # it directly so the tests exercise the real per-repaint code path.
    canvas._line = _DraftShape(
        shape_type="points",
        points=(QPointF(0, 0), QPointF(1, 1)),
        point_labels=(1, 1),
    )
    return canvas._build_ai_points_preview(
        current=_DraftShape(
            shape_type="points", points=(QPointF(0, 0),), point_labels=(1,)
        )
    )


@pytest.mark.gui
def test_preview_swallows_inference_error(
    broken_inference: tuple[Canvas, list[str]],
) -> None:
    # A model/runtime error during inference must not propagate (it would crash
    # the app, since the preview path runs inference inside paintEvent). The
    # preview falls back to the raw draft and reports the failure once.
    canvas, failures = broken_inference

    preview = _drive_ai_preview(canvas)

    assert preview is not None
    assert failures == ["RuntimeError: broken model"]


@pytest.mark.gui
def test_repeated_identical_inference_error_reported_once(
    broken_inference: tuple[Canvas, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The hover preview re-runs inference on every repaint; an identical failure
    # must be reported once until inference recovers, not spammed per repaint.
    canvas, failures = broken_inference

    for _ in range(3):
        _drive_ai_preview(canvas)
    assert len(failures) == 1

    # A successful inference clears the latch so the next failure is reported.
    monkeypatch.setattr(canvas._ai_assist_session, "propose_shapes", lambda **_: [])
    _drive_ai_preview(canvas)
    monkeypatch.setattr(
        canvas._ai_assist_session, "propose_shapes", _raise_inference_error
    )
    _drive_ai_preview(canvas)
    assert len(failures) == 2


@pytest.mark.gui
@pytest.mark.parametrize("create_mode", ["ai_box_to_shape", "ai_points_to_shape"])
def test_finalize_after_inference_error_resets_without_no_shapes_notice(
    broken_inference: tuple[Canvas, list[str]],
    create_mode: str,
) -> None:
    # When finalize yields no shapes because inference *failed*, the user has
    # already seen the failure message, so the misleading "produced no new
    # annotation" notice must be suppressed while state still resets.
    canvas, failures = broken_inference
    canvas.create_mode = create_mode
    canvas._current = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(1, 1),
    )
    no_shapes_emissions: list[None] = []
    canvas.inference_produced_no_shapes.connect(
        lambda: no_shapes_emissions.append(None)
    )

    canvas._finalize()

    assert no_shapes_emissions == []
    assert failures == ["RuntimeError: broken model"]
    assert canvas._current is None
    assert canvas.shapes == []


@pytest.mark.gui
def test_commit_after_preview_error_reports_failure_again(
    broken_inference: tuple[Canvas, list[str]],
) -> None:
    # The hover preview already reported the failure once. Committing re-runs the
    # same failing inference; that explicit click must surface its own error
    # instead of being swallowed by the preview dedup latch (which would leave
    # the click with no feedback at all).
    canvas, failures = broken_inference
    canvas.create_mode = "ai_points_to_shape"

    _drive_ai_preview(canvas)
    assert len(failures) == 1

    canvas._current = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(1, 1),
    )
    no_shapes_emissions: list[None] = []
    canvas.inference_produced_no_shapes.connect(
        lambda: no_shapes_emissions.append(None)
    )

    canvas._finalize()

    assert len(failures) == 2
    assert no_shapes_emissions == []
    assert canvas._current is None


@pytest.mark.gui
def test_load_pixmap_resets_inference_error_latch(
    broken_inference: tuple[Canvas, list[str]],
) -> None:
    # The dedup latch is per-image; loading a new image is a new inference
    # context whose first identical failure must surface, not be suppressed.
    canvas, failures = broken_inference

    _drive_ai_preview(canvas)
    assert len(failures) == 1

    canvas.load_pixmap(QtGui.QPixmap(_WIDTH, _HEIGHT))
    _drive_ai_preview(canvas)
    assert len(failures) == 2


@pytest.mark.gui
def test_entering_ai_mode_resets_inference_error_latch(
    broken_inference: tuple[Canvas, list[str]],
) -> None:
    # Re-entering an AI mode is a fresh inference intent; the first failure after
    # the switch must surface instead of being suppressed as a repeat.
    canvas, failures = broken_inference
    canvas.create_mode = "ai_points_to_shape"

    _drive_ai_preview(canvas)
    assert len(failures) == 1

    canvas.create_mode = "polygon"
    canvas.create_mode = "ai_points_to_shape"
    _drive_ai_preview(canvas)
    assert len(failures) == 2


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


def _make_polygon() -> Shape:
    return Shape(
        shape_type="polygon",
        points=np.array([(10, 10), (40, 10), (40, 40), (10, 40)], dtype=np.float64),
        closed=True,
    )


@pytest.mark.gui
def test_add_point_to_edge_repaints(
    canvas: Canvas, monkeypatch: pytest.MonkeyPatch
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
    canvas: Canvas, monkeypatch: pytest.MonkeyPatch
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
def test_remove_selected_point_deselects_vertex(canvas: Canvas) -> None:
    shape = _make_polygon()
    canvas.load_shapes(shapes=[shape])
    canvas._last_hovered_shape = shape
    canvas._last_hovered_vertex = 1
    canvas._hovered_vertex = 1

    canvas.remove_selected_point()

    assert len(shape.points) == 3  # the point was removed
    # Vertex is no longer selected, so the next move won't drag the neighbor (#968).
    assert not canvas._is_vertex_selected()
