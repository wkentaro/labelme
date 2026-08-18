from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable
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

from labelme._automation._ai_assist import AiAssistProposal
from labelme._shape import Shape
from labelme._shape import ShapeType
from labelme._widgets.canvas import Canvas
from labelme._widgets.canvas import _compute_intersection_edges_image
from labelme._widgets.canvas import _compute_overscroll_slack
from labelme._widgets.canvas import _draft_to_shape
from labelme._widgets.canvas import _DraftShape
from labelme._widgets.canvas import _is_degenerate_draft
from labelme._widgets.canvas import _is_out_of_image
from labelme._widgets.canvas import _normalize_bbox_points
from labelme._widgets.canvas import _opposite_corner_in_parallelogram
from labelme._widgets.canvas import _pick_pending_moved_shape
from labelme._widgets.canvas import _project_oriented_rectangle_corners
from labelme._widgets.canvas import _reproject_oriented_rectangle_corners
from labelme._widgets.canvas import _shape_to_draft
from labelme._widgets.canvas import _should_reselect_on_right_press
from labelme._widgets.canvas import _snap_cursor_pos_for_square

_WIDTH: Final[int] = 100
_HEIGHT: Final[int] = 50


@pytest.fixture()
def canvas(qtbot: QtBot) -> Canvas:
    canvas = Canvas()
    canvas.pixmap = QtGui.QPixmap(_WIDTH, _HEIGHT)
    qtbot.addWidget(canvas)
    return canvas


@pytest.mark.gui
def test_propose_ai_shapes_passes_rgb_image_to_model(
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canvas.pixmap.fill(QtGui.QColor(10, 20, 30))
    captured_images: list[np.ndarray] = []

    def propose_shapes(*, image: np.ndarray, **_: object) -> AiAssistProposal:
        captured_images.append(image)
        return AiAssistProposal(new_shapes=[], matching_existing_shapes=[])

    monkeypatch.setattr(canvas._ai_assist_session, "propose_shapes", propose_shapes)

    canvas._propose_ai_shapes(prompt_kind="points", points=[], point_labels=[])

    np.testing.assert_array_equal(captured_images[0][0, 0], [10, 20, 30])


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

    moved = canvas._drag_shapes(
        shapes=[shape], cursor=QPointF(150, 80), constrain_cursor=True
    )

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

    moved = canvas._drag_shapes(
        shapes=[shape], cursor=QPointF(150, 80), constrain_cursor=True
    )

    assert moved is True
    assert (shape.points[0][0], shape.points[0][1]) == pytest.approx((140, 75))
    assert (shape.points[1][0], shape.points[1][1]) == pytest.approx((160, 85))


@pytest.mark.gui
@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        pytest.param(QPointF(-5, 0), [(35, 20), (55, 30)], id="left"),
        pytest.param(QPointF(0, -5), [(40, 15), (60, 25)], id="up"),
    ],
)
def test_move_by_keyboard_moves_clickless_selection(
    canvas: Canvas, offset: QPointF, expected: list[tuple[float, float]]
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
def test_move_by_keyboard_clamps_clickless_selection_to_image(canvas: Canvas) -> None:
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
def test_move_by_keyboard_ignores_stale_mouse_position(canvas: Canvas) -> None:
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(40, 20), (60, 30)], dtype=np.float64),
        closed=True,
    )
    canvas.load_pixmap(QtGui.QPixmap(200, 100))
    canvas._prev_point = QPointF(150, 80)
    canvas.load_pixmap(QtGui.QPixmap(_WIDTH, _HEIGHT))
    canvas.shapes = [shape]
    canvas.selected_shapes = [shape]

    canvas._move_by_keyboard(offset=QPointF(5, 0))

    np.testing.assert_allclose(shape.points, [(45, 20), (65, 30)])


@pytest.mark.gui
def test_move_by_keyboard_rebuilds_mismatched_drag_anchor(canvas: Canvas) -> None:
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

    moved = canvas._drag_shapes(
        shapes=[shape], cursor=click + offset, constrain_cursor=True
    )

    assert moved is True
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
    canvas: Canvas, points: list[tuple[float, float]], offset: QPointF
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

    moved = canvas._drag_shapes(
        shapes=[shape],
        cursor=canvas._prev_point + offset,
        constrain_cursor=True,
    )

    assert moved is False
    np.testing.assert_allclose(shape.points, original)


@pytest.mark.gui
def test_drag_shapes_preserves_orthogonal_out_of_bounds_position(
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

    moved = canvas._drag_shapes(
        shapes=[shape],
        cursor=canvas._prev_point + QPointF(5, 0),
        constrain_cursor=False,
    )

    assert moved is True
    np.testing.assert_allclose(shape.points, [(45, 60), (65, 70)])


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


def _make_rectangle(label: str | None) -> Shape:
    return Shape(
        label=label,
        shape_type="rectangle",
        points=np.array([(0, 0), (10, 10)], dtype=np.float64),
        closed=True,
    )


@pytest.mark.gui
def test_set_last_label_applies_only_to_trailing_unlabeled_run(
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
    canvas.load_shapes([stale, labeled, fresh_a, fresh_b])

    updated = canvas.set_last_label("new", {"occluded": True})

    assert updated == [fresh_a, fresh_b]
    assert stale.label is None
    assert labeled.label == "old"
    assert fresh_a.label == "new"
    assert fresh_b.label == "new"
    assert fresh_a.flags == {"occluded": True}
    assert fresh_b.flags == {"occluded": True}


@pytest.mark.gui
def test_set_last_label_rejects_empty_text(canvas: Canvas) -> None:
    with pytest.raises(ValueError, match="text must not be empty"):
        canvas.set_last_label("", {})


@pytest.mark.gui
@pytest.mark.parametrize("create_mode", ["ai_box_to_shape", "ai_points_to_shape"])
def test_finalize_with_empty_inference_resets_state_and_notifies(
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
    create_mode: str,
) -> None:
    monkeypatch.setattr(
        canvas,
        "_propose_ai_shapes",
        lambda **_: AiAssistProposal(
            new_shapes=[],
            matching_existing_shapes=[],
        ),
    )
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
def test_existing_shape_suppression_is_disabled_by_default(
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _make_rectangle(label="existing")
    inferred = Shape(
        shape_type="rectangle",
        points=np.array([(20, 20), (30, 30)], dtype=np.float64),
        closed=True,
    )
    canvas.load_shapes([existing])

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
    canvas.create_mode = "ai_box_to_shape"
    canvas._current = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(1, 1),
    )

    canvas._finalize()

    assert canvas.shapes == [existing, inferred]


@pytest.mark.gui
@pytest.mark.parametrize(
    ("allow_out_of_bounds", "expected_image_size"),
    [(False, (_WIDTH, _HEIGHT)), (True, None)],
)
def test_ai_proposal_uses_out_of_bounds_setting(
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
    allow_out_of_bounds: bool,
    expected_image_size: tuple[int, int] | None,
) -> None:
    propose_shapes = Mock(
        return_value=AiAssistProposal(new_shapes=[], matching_existing_shapes=[])
    )
    monkeypatch.setattr(canvas._ai_assist_session, "propose_shapes", propose_shapes)
    canvas.set_allow_out_of_bounds_points(allow_out_of_bounds)

    canvas._propose_ai_shapes(
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
            lambda canvas: canvas.set_ai_model_name("efficientsam:10m"),
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
    canvas: Canvas,
    change_setting: Callable[[Canvas], None],
) -> None:
    existing = _make_rectangle(label="existing")
    canvas._set_ai_existing_shape_highlights(shapes=[existing])

    change_setting(canvas)

    assert canvas._ai_existing_shape_highlights == []


@pytest.mark.gui
def test_delete_shape_clears_highlights(canvas: Canvas) -> None:
    existing = _make_rectangle(label="existing")
    canvas.load_shapes([existing])
    canvas._set_ai_existing_shape_highlights(shapes=[existing])

    canvas.delete_shape(existing)

    assert canvas._ai_existing_shape_highlights == []


@pytest.mark.gui
def test_delete_selected_clears_highlights(canvas: Canvas) -> None:
    existing = _make_rectangle(label="existing")
    canvas.load_shapes([existing])
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
    canvas.load_shapes([existing])
    canvas.set_ai_existing_shape_suppression(enabled=True)
    canvas.create_mode = "ai_box_to_shape"
    canvas.set_editing(False)
    canvas._current = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(1, 1),
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
                False,
            )
        )

    cleared = canvas.grab().toImage().pixelColor(30, 20)
    assert cleared == QtGui.QColor(Qt.GlobalColor.black)


@pytest.mark.gui
def test_finalize_mixed_inference_adds_new_and_highlights_existing(
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
@pytest.mark.parametrize(
    "create_mode", ["point", "ai_box_to_shape", "ai_points_to_shape"]
)
def test_finalize_paints_new_shape_before_notifying(
    canvas: Canvas,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    create_mode: str,
) -> None:
    # new_shape's handler blocks on the modal label dialog, so the committed
    # shape must already be on screen when it fires. Point and AI-Box can
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
            shape_type="rectangle",
            points=(QPointF(0, 0), QPointF(10, 10)),
            point_labels=(1, 1),
        )
    canvas._finalize()

    assert counts_when_notified == [1]


@dataclasses.dataclass
class _AiPointsTestHarness:
    canvas: Canvas
    downloads: list[str]
    rejected_models: list[str]


@pytest.fixture()
def ai_points_harness(
    canvas: Canvas,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> _AiPointsTestHarness:
    downloads: list[str] = []
    rejected_models: list[str] = []

    def _download_ai_model(*, model_name: str, parent: Canvas) -> bool:
        del parent
        downloads.append(model_name)
        return True

    monkeypatch.setattr("labelme._widgets.canvas.download_ai_model", _download_ai_model)
    canvas.point_prompt_rejected.connect(rejected_models.append)
    canvas.resize(_WIDTH, _HEIGHT)
    canvas.set_editing(False)
    canvas.create_mode = "ai_points_to_shape"
    with qtbot.waitExposed(canvas):
        canvas.show()
    return _AiPointsTestHarness(
        canvas=canvas,
        downloads=downloads,
        rejected_models=rejected_models,
    )


@pytest.mark.gui
def test_ai_points_rejects_incompatible_model_before_download(
    ai_points_harness: _AiPointsTestHarness,
    qtbot: QtBot,
) -> None:
    canvas = ai_points_harness.canvas
    canvas.set_ai_model_name("sam3:latest")

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))

    assert ai_points_harness.rejected_models == ["sam3:latest"]
    assert ai_points_harness.downloads == []
    assert canvas._current is None


@pytest.mark.gui
def test_ai_points_rejects_incompatible_model_after_draft_started(
    ai_points_harness: _AiPointsTestHarness,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canvas = ai_points_harness.canvas
    proposal_model_names: list[str] = []

    def _propose_ai_shapes(**_: object) -> list[Shape]:
        proposal_model_names.append(canvas.get_ai_model_name())
        return []

    monkeypatch.setattr(canvas, "_propose_ai_shapes", _propose_ai_shapes)
    canvas.point_prompt_rejected.connect(lambda _: canvas.repaint())
    canvas.set_ai_model_name("sam2:latest")

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
    draft_before_rejection = canvas._current
    assert draft_before_rejection is not None
    canvas.set_ai_model_name("sam3:latest")

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(20, 20))

    assert ai_points_harness.rejected_models == ["sam3:latest"]
    assert ai_points_harness.downloads == ["sam2:latest"]
    assert "sam3:latest" not in proposal_model_names
    assert canvas._current == draft_before_rejection


@pytest.mark.gui
def test_ai_points_rejects_incompatible_model_on_finalize(
    ai_points_harness: _AiPointsTestHarness,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canvas = ai_points_harness.canvas
    proposal_model_names: list[str] = []
    inference_failures: list[str] = []

    def _propose_ai_shapes(**_: object) -> list[Shape]:
        proposal_model_names.append(canvas.get_ai_model_name())
        return []

    monkeypatch.setattr(canvas, "_propose_ai_shapes", _propose_ai_shapes)
    canvas.point_prompt_rejected.connect(lambda _: canvas.repaint())
    canvas.inference_failed.connect(inference_failures.append)
    canvas.set_ai_model_name("sam2:latest")

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(10, 10))
    draft_before_rejection = canvas._current
    assert draft_before_rejection is not None
    canvas.set_ai_model_name("sam3:latest")

    qtbot.keyClick(canvas, Qt.Key.Key_Return)

    assert ai_points_harness.rejected_models == ["sam3:latest"]
    assert ai_points_harness.downloads == ["sam2:latest"]
    assert "sam3:latest" not in proposal_model_names
    assert inference_failures == []
    assert canvas._current == draft_before_rejection


@pytest.mark.gui
def test_ai_points_ignores_incompatible_first_click_outside_image(
    ai_points_harness: _AiPointsTestHarness,
    qtbot: QtBot,
) -> None:
    canvas = ai_points_harness.canvas
    canvas.resize(_WIDTH * 2, _HEIGHT * 2)
    canvas.set_ai_model_name("sam3:latest")

    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QtCore.QPoint(1, 1))

    assert ai_points_harness.rejected_models == []
    assert ai_points_harness.downloads == []
    assert canvas._current is None


@pytest.mark.gui
@pytest.mark.parametrize("create_mode", ["ai_box_to_shape", "ai_points_to_shape"])
def test_finalize_reports_inference_error_and_cancels(
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
    create_mode: str,
) -> None:
    # A model error while committing an AI shape must not crash _finalize: it
    # surfaces a non-fatal inference_failed signal, cancels the in-progress
    # shape, and does not masquerade as an empty-inference result.
    def _raise(**_: object) -> list[Shape]:
        raise RuntimeError("boom")

    monkeypatch.setattr(canvas, "_propose_ai_shapes", _raise)
    canvas.create_mode = create_mode
    canvas._current = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(0, 0), QPointF(10, 10)),
        point_labels=(1, 1),
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
def test_points_preview_hides_failed_and_empty_predictions(
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The points preview re-runs inference on every repaint, so a persistently
    # failing model must report once, not once per frame. A later success
    # re-arms the report so a fresh failure surfaces again.
    behavior = {"fail": True}

    def _maybe_raise(**_: object) -> AiAssistProposal:
        if behavior["fail"]:
            raise RuntimeError("boom")
        return AiAssistProposal(new_shapes=[], matching_existing_shapes=[])

    monkeypatch.setattr(canvas, "_propose_ai_shapes", _maybe_raise)
    canvas.create_mode = "ai_points_to_shape"
    canvas._line = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(0, 0), QPointF(5, 5)),
        point_labels=(1, 1),
    )
    current = _DraftShape(
        shape_type="rectangle",
        points=(QPointF(0, 0),),
        point_labels=(1,),
    )
    failed: list[str] = []
    canvas.inference_failed.connect(failed.append)

    assert canvas._build_ai_points_preview(current=current) is None
    assert canvas._build_ai_points_preview(current=current) is None
    assert failed == ["RuntimeError: boom"]

    behavior["fail"] = False
    assert canvas._build_ai_points_preview(current=current) is None
    behavior["fail"] = True
    assert canvas._build_ai_points_preview(current=current) is None
    assert failed == ["RuntimeError: boom", "RuntimeError: boom"]


@pytest.mark.gui
def test_load_pixmap_rearms_inference_failure_report(canvas: Canvas) -> None:
    # A new image is a fresh inference context: a previous image's latched
    # failure must not mute the first failure report on the new image.
    canvas._ai_inference_failed = True
    canvas.load_pixmap(QtGui.QPixmap(_WIDTH, _HEIGHT))
    assert canvas._ai_inference_failed is False


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
def test_is_out_of_image(point: tuple[float, float], expected: bool) -> None:
    # The image rect is inclusive at both edges: a point exactly on the far
    # width/height boundary counts as inside, since the clamping callers treat
    # the pixmap size as a reachable coordinate rather than an exclusive extent.
    assert _is_out_of_image(QPointF(*point), QSize(_WIDTH, _HEIGHT)) is expected


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


def test_pick_pending_moved_shape_none_when_not_moving() -> None:
    hovered = Shape()
    assert (
        _pick_pending_moved_shape(
            is_moving_shape=False, hovered_shape=hovered, shapes=[hovered]
        )
        is None
    )


def test_pick_pending_moved_shape_none_when_hovering_nothing() -> None:
    assert (
        _pick_pending_moved_shape(
            is_moving_shape=True, hovered_shape=None, shapes=[Shape()]
        )
        is None
    )


def test_pick_pending_moved_shape_none_when_hovered_absent_from_shapes() -> None:
    assert (
        _pick_pending_moved_shape(
            is_moving_shape=True, hovered_shape=Shape(), shapes=[Shape()]
        )
        is None
    )


def test_pick_pending_moved_shape_returns_hovered_when_present() -> None:
    hovered = Shape()
    assert (
        _pick_pending_moved_shape(
            is_moving_shape=True, hovered_shape=hovered, shapes=[Shape(), hovered]
        )
        is hovered
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
    ],
)
def test_snap_cursor_pos_for_square(
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


@pytest.mark.gui
def test_end_move_in_place_copies_points(canvas: Canvas) -> None:
    shape = _make_polygon()
    canvas.load_shapes(shapes=[shape])
    canvas.selected_shapes = [shape]
    clone = shape.copy()
    clone.translate(offset=(5, -5))
    canvas._selected_shapes_copy = [clone]

    canvas.end_move(copy=False)

    assert np.array_equal(shape.points, clone.points)
    assert not np.shares_memory(shape.points, clone.points)
