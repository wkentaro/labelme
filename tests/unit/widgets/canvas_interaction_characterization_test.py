from __future__ import annotations

from collections.abc import Generator

import numpy as np
import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme._widgets.canvas import Canvas
from labelme._widgets.canvas import _DraftShape

# Default epsilon in Canvas (screen-pixel hit radius).
_EPSILON: float = 10.0

# Pixmap dimensions used across all tests.
_W: int = 200
_H: int = 100


@pytest.fixture(autouse=True)
def _isolated_override_cursor_stack() -> Generator[None, None, None]:
    # The override-cursor stack is process-global; an earlier GUI test can leave
    # an override pushed. These tests assert on absolute override-cursor state,
    # so drain the stack around each test to keep that state self-contained.
    while QtWidgets.QApplication.overrideCursor() is not None:
        QtWidgets.QApplication.restoreOverrideCursor()
    yield
    while QtWidgets.QApplication.overrideCursor() is not None:
        QtWidgets.QApplication.restoreOverrideCursor()


@pytest.fixture()
def canvas(qtbot: QtBot) -> Canvas:
    c = Canvas()
    c.pixmap = QtGui.QPixmap(_W, _H)
    # Resize to exactly the pixmap dimensions so the image-origin offset is
    # zero and widget coordinates equal image coordinates at scale=1.0.
    c.resize(_W, _H)
    qtbot.addWidget(c)
    return c


def _make_move_event(pos: QPointF) -> QtGui.QMouseEvent:
    return QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseMove,
        pos,
        pos,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _make_press_event(
    pos: QPointF,
    button: Qt.MouseButton = Qt.MouseButton.RightButton,
) -> QtGui.QMouseEvent:
    return QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonPress,
        pos,
        pos,
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )


def _make_release_event(
    pos: QPointF,
    button: Qt.MouseButton = Qt.MouseButton.RightButton,
) -> QtGui.QMouseEvent:
    return QtGui.QMouseEvent(
        QtCore.QEvent.Type.MouseButtonRelease,
        pos,
        pos,
        button,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _image_to_widget(canvas: Canvas, img_x: float, img_y: float) -> QPointF:
    """Convert image-space coordinates to widget-space coordinates."""
    origin = canvas._compute_image_origin_offset()
    wx = (img_x + origin.x()) * canvas.scale
    wy = (img_y + origin.y()) * canvas.scale
    return QPointF(wx, wy)


def _clear_cursor_override(canvas: Canvas) -> None:
    """Remove any outstanding override cursor pushed by the canvas."""
    canvas._release_cursor()


# ---------------------------------------------------------------------------
# Cursor shape -- create (drawing) mode
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_cursor_is_cross_when_hovering_in_create_mode(canvas: Canvas) -> None:
    # Any mouse move in CREATE mode should engage CrossCursor.
    canvas.set_editing(value=False)
    canvas.create_mode = "rectangle"
    pos = _image_to_widget(canvas=canvas, img_x=50, img_y=25)

    canvas.mouseMoveEvent(_make_move_event(pos=pos))

    override = QtWidgets.QApplication.overrideCursor()
    assert override is not None
    assert override.shape() == Qt.CursorShape.CrossCursor
    _clear_cursor_override(canvas=canvas)


@pytest.mark.gui
def test_cursor_reverts_to_no_override_after_cursor_cleared(canvas: Canvas) -> None:
    # After _release_cursor the override stack is empty; callers treat that
    # as ArrowCursor.
    canvas.set_editing(value=False)
    canvas.create_mode = "polygon"
    pos = _image_to_widget(canvas=canvas, img_x=50, img_y=25)
    canvas.mouseMoveEvent(_make_move_event(pos=pos))
    assert QtWidgets.QApplication.overrideCursor() is not None  # sanity

    _clear_cursor_override(canvas=canvas)

    assert QtWidgets.QApplication.overrideCursor() is None


# ---------------------------------------------------------------------------
# Cursor shape -- edit mode, empty canvas
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_cursor_is_arrow_when_hovering_empty_canvas_in_edit_mode(
    canvas: Canvas,
) -> None:
    # Moving over blank canvas area (no shapes) leaves no override cursor.
    canvas.set_editing(value=True)
    canvas.scale = 1.0
    pos = _image_to_widget(canvas=canvas, img_x=100, img_y=50)

    canvas.mouseMoveEvent(_make_move_event(pos=pos))

    assert QtWidgets.QApplication.overrideCursor() is None


# ---------------------------------------------------------------------------
# Cursor shape -- edit mode, shape-body hover
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_cursor_is_open_hand_when_hovering_shape_body_in_edit_mode(
    canvas: Canvas,
) -> None:
    # Hovering the interior of a shape (not near a vertex or edge) uses
    # OpenHandCursor to signal the shape is draggable.
    shape = Shape(
        shape_type="polygon",
        points=np.array([(10, 10), (40, 10), (40, 40), (10, 40)], dtype=np.float64),
        closed=True,
    )
    canvas.load_shapes(shapes=[shape])
    canvas.set_editing(value=True)
    canvas.scale = 1.0
    # (25, 25) is the centroid, well away from every vertex and edge.
    pos = _image_to_widget(canvas=canvas, img_x=25, img_y=25)

    canvas.mouseMoveEvent(_make_move_event(pos=pos))

    override = QtWidgets.QApplication.overrideCursor()
    assert override is not None
    assert override.shape() == Qt.CursorShape.OpenHandCursor
    _clear_cursor_override(canvas=canvas)


# ---------------------------------------------------------------------------
# Cursor shape -- edit mode, vertex hover
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_cursor_is_pointing_hand_when_hovering_vertex_in_edit_mode(
    canvas: Canvas,
) -> None:
    # Hovering a vertex in EDIT mode engages PointingHandCursor.
    shape = Shape(
        shape_type="polygon",
        points=np.array([(10, 10), (40, 10), (40, 40), (10, 40)], dtype=np.float64),
        closed=True,
    )
    canvas.load_shapes(shapes=[shape])
    canvas.set_editing(value=True)
    canvas.scale = 1.0
    pos = _image_to_widget(canvas=canvas, img_x=10, img_y=10)

    canvas.mouseMoveEvent(_make_move_event(pos=pos))

    override = QtWidgets.QApplication.overrideCursor()
    assert override is not None
    assert override.shape() == Qt.CursorShape.PointingHandCursor
    _clear_cursor_override(canvas=canvas)


# ---------------------------------------------------------------------------
# Cursor shape -- edit mode, edge hover
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_cursor_is_pointing_hand_when_hovering_edge_in_edit_mode(
    canvas: Canvas,
) -> None:
    # Hovering an edge midpoint of a polygon (but not near a vertex) also
    # uses PointingHandCursor because clicking inserts a vertex.
    shape = Shape(
        shape_type="polygon",
        points=np.array([(10, 10), (90, 10), (90, 40), (10, 40)], dtype=np.float64),
        closed=True,
    )
    canvas.load_shapes(shapes=[shape])
    canvas.set_editing(value=True)
    canvas.scale = 1.0
    # (50, 10) is the midpoint of the top edge, not near any vertex.
    pos = _image_to_widget(canvas=canvas, img_x=50, img_y=10)

    canvas.mouseMoveEvent(_make_move_event(pos=pos))

    override = QtWidgets.QApplication.overrideCursor()
    assert override is not None
    assert override.shape() == Qt.CursorShape.PointingHandCursor
    _clear_cursor_override(canvas=canvas)


# ---------------------------------------------------------------------------
# Cursor shape -- create mode, polygon-origin snap
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_cursor_is_pointing_hand_when_snapping_to_polygon_origin(
    canvas: Canvas,
) -> None:
    # While drawing a polygon with 3+ points, approaching the first point
    # within epsilon switches from CrossCursor to PointingHandCursor.
    canvas.set_editing(value=False)
    canvas.create_mode = "polygon"
    canvas.scale = 1.0
    canvas._current = _DraftShape(
        shape_type="polygon",
        points=(QPointF(10, 10), QPointF(40, 10), QPointF(40, 40)),
        point_labels=(1, 1, 1),
    )
    # Hover exactly on the polygon's first point (the snap target).
    pos = _image_to_widget(canvas=canvas, img_x=10, img_y=10)

    canvas.mouseMoveEvent(_make_move_event(pos=pos))

    override = QtWidgets.QApplication.overrideCursor()
    assert override is not None
    assert override.shape() == Qt.CursorShape.PointingHandCursor
    _clear_cursor_override(canvas=canvas)


@pytest.mark.gui
def test_cursor_is_cross_when_far_from_polygon_origin(canvas: Canvas) -> None:
    # When the cursor is more than epsilon/scale away from the polygon origin,
    # CrossCursor is kept (no snap engagement).
    canvas.set_editing(value=False)
    canvas.create_mode = "polygon"
    canvas.scale = 1.0
    canvas._current = _DraftShape(
        shape_type="polygon",
        points=(QPointF(10, 10), QPointF(40, 10), QPointF(40, 40)),
        point_labels=(1, 1, 1),
    )
    # (80, 50) is well beyond epsilon=10 from origin (10, 10).
    pos = _image_to_widget(canvas=canvas, img_x=80, img_y=50)

    canvas.mouseMoveEvent(_make_move_event(pos=pos))

    override = QtWidgets.QApplication.overrideCursor()
    assert override is not None
    assert override.shape() == Qt.CursorShape.CrossCursor
    _clear_cursor_override(canvas=canvas)


# ---------------------------------------------------------------------------
# Context-menu selection
# ---------------------------------------------------------------------------


@pytest.mark.gui
def test_context_menus_pair_holds_two_menus(canvas: Canvas) -> None:
    # The public context_menus pair exposes a no-selection menu and a
    # selection menu as named QMenu attributes.
    assert isinstance(canvas.context_menus.without_selection, QtWidgets.QMenu)
    assert isinstance(canvas.context_menus.with_selection, QtWidgets.QMenu)


@pytest.mark.gui
def test_right_release_without_selection_copy_executes_menus_0(
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Without a dragged copy (_selected_shapes_copy empty), the no-selection
    # context menu (index 0) is executed.
    canvas.set_editing(value=True)
    canvas.scale = 1.0
    calls: list[int] = []
    monkeypatch.setattr(
        canvas.context_menus.without_selection, "exec", lambda pos=None: calls.append(0)
    )
    monkeypatch.setattr(
        canvas.context_menus.with_selection, "exec", lambda pos=None: calls.append(1)
    )
    pos = _image_to_widget(canvas=canvas, img_x=50, img_y=25)

    canvas.mousePressEvent(_make_press_event(pos=pos))
    canvas.mouseReleaseEvent(_make_release_event(pos=pos))

    assert calls == [0]


@pytest.mark.gui
def test_right_release_with_selection_copy_executes_menus_1(
    canvas: Canvas,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # When selected shapes have been right-drag-copied (_selected_shapes_copy
    # non-empty), the with-selection context menu (index 1) is executed.
    shape = Shape(
        shape_type="rectangle",
        points=np.array([(10, 10), (50, 40)], dtype=np.float64),
        closed=True,
    )
    canvas.load_shapes(shapes=[shape])
    canvas.set_editing(value=True)
    canvas.scale = 1.0
    canvas.selected_shapes = [shape]
    canvas._selected_shapes_copy = [shape.copy()]
    calls: list[int] = []
    monkeypatch.setattr(
        canvas.context_menus.without_selection, "exec", lambda pos=None: calls.append(0)
    )
    monkeypatch.setattr(
        canvas.context_menus.with_selection, "exec", lambda pos=None: calls.append(1)
    )
    pos = _image_to_widget(canvas=canvas, img_x=30, img_y=25)

    canvas.mousePressEvent(_make_press_event(pos=pos))
    canvas.mouseReleaseEvent(_make_release_event(pos=pos))

    assert calls == [1]


# ---------------------------------------------------------------------------
# Vertex hover-highlight + snapping parity across zoom (scale) levels
#
# Proximity formula (from _shape.nearest_vertex_index):
#   screen_distance = euclidean_distance(image_point, vertex) * scale
#   hit iff screen_distance <= epsilon          (epsilon default = 10.0)
#
# Equivalently: image_distance <= epsilon / scale
#
# The polygon below has a vertex at image-center (100, 50) and the other
# vertices at the image periphery.  Test points are displaced along X only
# from (100, 50) so no polygon edge passes through the test coordinate.
# ---------------------------------------------------------------------------


def _make_center_polygon() -> Shape:
    """Polygon with a vertex at image-center (100, 50), others at corners."""
    return Shape(
        shape_type="polygon",
        points=np.array(
            [(100, 50), (30, 30), (170, 30), (170, 70), (30, 70)],
            dtype=np.float64,
        ),
        closed=True,
    )


@pytest.mark.gui
@pytest.mark.parametrize(
    "scale",
    [0.5, 1.0, 2.0],
    ids=["scale_0.5", "scale_1.0", "scale_2.0"],
)
def test_vertex_hover_within_epsilon_screen_pixels_gives_pointing_hand(
    qtbot: QtBot,
    scale: float,
) -> None:
    # A hover that is 7 SCREEN pixels from the vertex must always give
    # PointingHandCursor regardless of zoom level because 7 < epsilon=10.
    canvas = Canvas()
    canvas.pixmap = QtGui.QPixmap(_W, _H)
    canvas.resize(int(_W * scale), int(_H * scale))
    canvas.scale = scale
    qtbot.addWidget(canvas)

    shape = _make_center_polygon()
    canvas.load_shapes(shapes=[shape])
    canvas.set_editing(value=True)

    # 7 screen pixels at this scale equals 7/scale image pixels.
    image_offset_px = 7.0 / scale
    img_x = 100.0 + image_offset_px
    pos = _image_to_widget(canvas=canvas, img_x=img_x, img_y=50.0)

    canvas.mouseMoveEvent(_make_move_event(pos=pos))

    override = QtWidgets.QApplication.overrideCursor()
    assert override is not None, (
        f"scale={scale}: expected a cursor override (7 screen px from vertex)"
    )
    assert override.shape() == Qt.CursorShape.PointingHandCursor, (
        f"scale={scale}: expected PointingHandCursor at 7 screen px from vertex"
    )
    _clear_cursor_override(canvas=canvas)


@pytest.mark.gui
@pytest.mark.parametrize(
    "scale",
    [0.5, 1.0, 2.0],
    ids=["scale_0.5", "scale_1.0", "scale_2.0"],
)
def test_vertex_hover_beyond_epsilon_screen_pixels_does_not_select_vertex(
    qtbot: QtBot,
    scale: float,
) -> None:
    # A hover that is 12 SCREEN pixels from the vertex is outside epsilon=10
    # and must NOT register as a vertex hit (_hovered_vertex stays None).
    canvas = Canvas()
    canvas.pixmap = QtGui.QPixmap(_W, _H)
    canvas.resize(int(_W * scale), int(_H * scale))
    canvas.scale = scale
    qtbot.addWidget(canvas)

    shape = _make_center_polygon()
    canvas.load_shapes(shapes=[shape])
    canvas.set_editing(value=True)

    # 12 screen pixels at this scale equals 12/scale image pixels.
    image_offset_px = 12.0 / scale
    img_x = 100.0 + image_offset_px
    pos = _image_to_widget(canvas=canvas, img_x=img_x, img_y=50.0)

    canvas.mouseMoveEvent(_make_move_event(pos=pos))

    assert canvas._hovered_vertex is None, (
        f"scale={scale}: expected no vertex hit at 12 screen px from vertex "
        f"(image_offset={image_offset_px:.2f}px, epsilon={_EPSILON})"
    )
    _clear_cursor_override(canvas=canvas)


@pytest.mark.gui
def test_screen_pixel_hit_radius_is_constant_across_scale_levels(
    qtbot: QtBot,
) -> None:
    # Confirm parity: a fixed 7-screen-pixel offset from the vertex always
    # triggers a vertex hit across three representative scale levels.
    screen_offset_px: float = 7.0  # < epsilon=10, so always within hit range

    for scale in (0.5, 1.0, 2.0):
        canvas = Canvas()
        canvas.pixmap = QtGui.QPixmap(_W, _H)
        canvas.resize(int(_W * scale), int(_H * scale))
        canvas.scale = scale
        qtbot.addWidget(canvas)

        shape = _make_center_polygon()
        canvas.load_shapes(shapes=[shape])
        canvas.set_editing(value=True)

        image_offset_px = screen_offset_px / scale
        img_x = 100.0 + image_offset_px
        pos = _image_to_widget(canvas=canvas, img_x=img_x, img_y=50.0)

        canvas.mouseMoveEvent(_make_move_event(pos=pos))

        assert canvas._hovered_vertex is not None, (
            f"scale={scale}: vertex should be hit at {screen_offset_px} screen px "
            f"(image_offset={image_offset_px:.2f}px)"
        )
        override = QtWidgets.QApplication.overrideCursor()
        assert override is not None, f"scale={scale}: expected cursor override"
        assert override.shape() == Qt.CursorShape.PointingHandCursor, (
            f"scale={scale}: expected PointingHandCursor"
        )
        _clear_cursor_override(canvas=canvas)
