from __future__ import annotations

import math
from typing import Final

import pytest
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import QPointF
from PyQt5.QtCore import QSize
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme.widgets.canvas import Canvas
from labelme.widgets.canvas import _compute_intersection_edges_image
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
    shape = Shape(shape_type="oriented_rectangle")
    for x, y in corners:
        shape.add_point(QPointF(x, y))
    shape.close()
    return shape


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
        assert canvas.shapes[0].points[i].x() == pytest.approx(x)
        assert canvas.shapes[0].points[i].y() == pytest.approx(y)


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
        assert (shape.points[i].x(), shape.points[i].y()) == pytest.approx((x, y))


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
        assert (shape.points[i].x(), shape.points[i].y()) == pytest.approx((x, y))


@pytest.mark.gui
def test_shape_visibility_survives_backup_and_restore(canvas: Canvas) -> None:
    shape = Shape(label="a", shape_type="rectangle")
    shape.add_point(QPointF(0, 0))
    shape.add_point(QPointF(10, 10))
    shape.close()
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
    canvas._current = Shape(shape_type="rectangle")
    # ai_box_to_shape normalizes the two bbox corners before delegating to the
    # (monkeypatched) inference call, so the in-progress shape needs 2 points.
    canvas._current.add_point(QPointF(0, 0))
    canvas._current.add_point(QPointF(10, 10))
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


_VIEWPORT_SIZE: Final[QSize] = QSize(400, 300)


@pytest.fixture()
def scrolled_canvas(qtbot: QtBot) -> Canvas:
    scroll_area = QtWidgets.QScrollArea()
    scroll_area.viewport().setFixedSize(_VIEWPORT_SIZE)
    canvas = Canvas()
    canvas.pixmap = QtGui.QPixmap(_WIDTH, _HEIGHT)
    scroll_area.setWidget(canvas)
    qtbot.addWidget(scroll_area)
    # Keep a Python reference on the canvas so the scroll area survives the
    # fixture's local scope; otherwise GC drops it and its C++ child canvas
    # is destroyed before the test body runs.
    canvas._test_scroll_area_keepalive = scroll_area  # ty: ignore[unresolved-attribute]
    return canvas


@pytest.mark.gui
def test_compute_canvas_size_is_continuous_through_overflow_threshold(
    scrolled_canvas: Canvas,
) -> None:
    # Pre-fix the slack jumped from 0 to V/2 the instant scaled_w crossed the
    # viewport width, shifting the centered image by V/4 in one zoom step.
    # Adjacent scales straddling the threshold should now differ only by
    # rounding noise (pre-fix the gap was ~V/2, here ~2).
    viewport_w: Final[int] = _VIEWPORT_SIZE.width()
    pixmap_w: Final[int] = scrolled_canvas.pixmap.width()

    scrolled_canvas.scale = (viewport_w - 1) / pixmap_w
    just_below = scrolled_canvas._compute_canvas_size().width()
    scrolled_canvas.scale = (viewport_w + 1) / pixmap_w
    just_above = scrolled_canvas._compute_canvas_size().width()

    assert just_above - just_below <= 3


@pytest.mark.gui
def test_compute_canvas_size_caps_overscroll_at_half_viewport(
    scrolled_canvas: Canvas,
) -> None:
    # Slack saturates at V/2 so each image edge can be panned to the viewport
    # center but no further. Sampling at the exact saturation point (1.5V)
    # locks both the cap value and the scale at which it engages.
    viewport_w: Final[int] = _VIEWPORT_SIZE.width()
    pixmap_w: Final[int] = scrolled_canvas.pixmap.width()

    scrolled_canvas.scale = 1.5 * viewport_w / pixmap_w
    scaled_w = int(pixmap_w * scrolled_canvas.scale)
    assert scrolled_canvas._compute_canvas_size().width() == scaled_w + viewport_w // 2
