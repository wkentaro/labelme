from __future__ import annotations

import collections
import enum
from collections.abc import Callable
from typing import Any
from typing import Final
from typing import Literal

import imgviz
import numpy as np
import osam
from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import QPointF
from PyQt5.QtCore import Qt

import labelme.utils
from labelme._automation import OsamSession
from labelme._automation import polygon_from_mask
from labelme.shape import Shape

from .download import download_ai_model

CURSOR_DEFAULT = Qt.ArrowCursor
CURSOR_POINT = Qt.PointingHandCursor
CURSOR_DRAW = Qt.CrossCursor
CURSOR_MOVE = Qt.ClosedHandCursor
CURSOR_GRAB = Qt.OpenHandCursor

MOVE_SPEED: float = 5.0


class CanvasMode(enum.Enum):
    CREATE = enum.auto()
    EDIT = enum.auto()


class Canvas(QtWidgets.QWidget):
    pixmap: QtGui.QPixmap
    _pixmap_hash: int | None
    _cursor: QtCore.Qt.CursorShape
    shapes: list[Shape]
    shape_backups: collections.deque[list[Shape]]
    is_moving_shape: bool
    selected_shapes: list[Shape]
    selected_shapes_copy: list[Shape]
    current: Shape | None
    hovered_shape: Shape | None
    _last_hovered_shape: Shape | None
    hovered_vertex: int | None
    _last_hovered_vertex: int | None
    hovered_edge: int | None
    _last_hovered_edge: int | None

    zoom_request = QtCore.pyqtSignal(int, QPointF)
    scroll_request = QtCore.pyqtSignal(int, int)
    pan_request = QtCore.pyqtSignal(QPoint)
    new_shape = QtCore.pyqtSignal()
    selection_changed = QtCore.pyqtSignal(list)
    shape_moved = QtCore.pyqtSignal()
    drawing_polygon = QtCore.pyqtSignal(bool)
    vertex_selected = QtCore.pyqtSignal(bool)
    mouse_moved = QtCore.pyqtSignal(QPointF)
    status_updated = QtCore.pyqtSignal(str)

    mode: CanvasMode = CanvasMode.EDIT

    # polygon, rectangle, line, or point
    _create_mode = "polygon"

    _fill_drawing = False

    prev_point: QPointF
    prev_move_point: QPointF
    offsets: tuple[QPointF, QPointF]

    _pan_anchor: QPointF | None

    _osam_session_model_name: str = "sam2:latest"
    _osam_session: OsamSession | None
    _ai_output_format: Literal["polygon", "mask"] = "polygon"

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        self.epsilon: float = kwargs.pop("epsilon", 10.0)
        self.double_click = kwargs.pop("double_click", "close")
        if self.double_click not in [None, "close"]:
            raise ValueError(
                f"Unexpected value for double_click event: {self.double_click}"
            )
        self.num_backups = kwargs.pop("num_backups", 10)
        self._crosshair = kwargs.pop(
            "crosshair",
            {
                "polygon": False,
                "rectangle": True,
                "circle": False,
                "line": False,
                "point": False,
                "linestrip": False,
                "ai_points_to_shape": False,
                "ai_box_to_shape": True,
            },
        )
        super().__init__(*args, **kwargs)

        self._cursor = CURSOR_DEFAULT
        self.reset_state()

        # self.line represents:
        #   - create_mode == 'polygon': edge from last point to current
        #   - create_mode == 'rectangle': diagonal line of the rectangle
        #   - create_mode == 'line': the line
        #   - create_mode == 'point': the point
        self.line = Shape()
        self.prev_point = QPointF()
        self.prev_move_point = QPointF()
        self.offsets = QPointF(), QPointF()
        self.scale: float = 1.0
        self._osam_session = None
        self.visible: dict = {}
        self._hide_background: bool = False
        self.hide_background: bool = False
        self.snapping = True
        self.hovered_shape_is_selected: bool = False
        self._painter = QtGui.QPainter()
        self._pan_anchor = None
        # Menus:
        # 0: right-click without selection and dragging of shapes
        # 1: right-click with selection and dragging of shapes
        self.menus = (QtWidgets.QMenu(), QtWidgets.QMenu())
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.WheelFocus)

    def fill_drawing(self) -> bool:
        return self._fill_drawing

    def set_fill_drawing(self, value: bool) -> None:
        self._fill_drawing = value

    @property
    def create_mode(self) -> str:
        return self._create_mode

    @create_mode.setter
    def create_mode(self, value: str) -> None:
        if value not in [
            "polygon",
            "rectangle",
            "circle",
            "line",
            "point",
            "linestrip",
            "ai_points_to_shape",
            "ai_box_to_shape",
        ]:
            raise ValueError(f"Unsupported create_mode: {value}")
        self._create_mode = value

    def get_ai_model_name(self) -> str:
        return self._osam_session_model_name

    def set_ai_model_name(self, model_name: str) -> None:
        self._osam_session_model_name = model_name

    def set_ai_output_format(self, output_format: Literal["polygon", "mask"]) -> None:
        self._ai_output_format = output_format

    def _get_osam_session(self) -> OsamSession:
        if (
            self._osam_session is None
            or self._osam_session.model_name != self._osam_session_model_name
        ):
            self._osam_session = OsamSession(model_name=self._osam_session_model_name)
        return self._osam_session

    def _shapes_from_points_ai(
        self, points: list[QPointF], point_labels: list[int]
    ) -> list[Shape]:
        image: np.ndarray = labelme.utils.img_qt_to_arr(img_qt=self.pixmap.toImage())
        response: osam.types.GenerateResponse = self._get_osam_session().run(
            image=imgviz.asrgb(image),  # type: ignore[arg-type]
            image_id=str(self._pixmap_hash),
            points=np.array([[p.x(), p.y()] for p in points]),
            point_labels=np.array(point_labels),
        )
        return _shapes_from_ai_response(
            response=response,
            output_format=self._ai_output_format,
        )

    def _shapes_from_bbox_ai(self, bbox_points: list[QPointF]) -> list[Shape]:
        if len(bbox_points) != 2:
            raise ValueError(f"Expected 2 points for bbox AI, got {len(bbox_points)}")
        image: np.ndarray = labelme.utils.img_qt_to_arr(img_qt=self.pixmap.toImage())
        response: osam.types.GenerateResponse = self._get_osam_session().run(
            image=imgviz.asrgb(image),  # type: ignore[arg-type]
            image_id=str(self._pixmap_hash),
            points=np.array([[p.x(), p.y()] for p in bbox_points]),
            # point_labels: 2=box corner, 3=opposite box corner (SAM convention)
            point_labels=np.array([2, 3]),
        )
        return _shapes_from_ai_response(
            response=response,
            output_format=self._ai_output_format,
        )

    def backup_shapes(self) -> None:
        self.shape_backups.append([s.copy() for s in self.shapes])

    @property
    def can_restore_shape(self) -> bool:
        # We save the state AFTER each edit (not before) so for an
        # edit to be undoable, we expect the CURRENT and the PREVIOUS state
        # to be in the undo stack.
        if len(self.shape_backups) < 2:
            return False
        return True

    def restore_last_shape(self) -> None:
        # This does _part_ of the job of restoring shapes.
        # The complete process is also done in app.py::undo_shape_edit
        # and app.py::load_shapes and our own Canvas::load_shapes function.
        if not self.can_restore_shape:
            return
        self.shape_backups.pop()  # latest

        # The application will eventually call Canvas.load_shapes which will
        # push this right back onto the stack.
        self.shapes = self.shape_backups.pop()
        for shape in self.shapes:
            shape.selected = False
        self.selected_shapes.clear()
        self.update()

    def enterEvent(self, a0: QtCore.QEvent) -> None:
        self._apply_cursor(self._cursor)
        self._update_status()

    def leaveEvent(self, a0: QtCore.QEvent) -> None:
        if self._set_highlight(
            hovered_shape=None, hovered_edge=None, hovered_vertex=None
        ):
            self.update()
        self._release_cursor()
        self._update_status()

    def focusOutEvent(self, a0: QtGui.QFocusEvent) -> None:
        self._release_cursor()
        self._update_status()

    def is_shape_visible(self, shape: Shape) -> bool:
        return self.visible.get(shape, True)

    def drawing(self) -> bool:
        return self.mode == CanvasMode.CREATE

    def editing(self) -> bool:
        return self.mode == CanvasMode.EDIT

    def set_editing(self, value: bool = True) -> None:
        self.mode = CanvasMode.EDIT if value else CanvasMode.CREATE
        if self.mode == CanvasMode.EDIT:
            # CREATE -> EDIT
            self.update()  # clear crosshair
        else:
            # EDIT -> CREATE
            need_update: bool = self._set_highlight(
                hovered_shape=None, hovered_edge=None, hovered_vertex=None
            )
            need_update |= self.deselect_shape()
            if need_update:
                self.update()

    def _set_highlight(
        self,
        hovered_shape: Shape | None,
        hovered_edge: int | None,
        hovered_vertex: int | None,
    ) -> bool:
        previous_shape: Shape | None = self.hovered_shape
        need_update: bool = hovered_shape is not None
        if previous_shape is not None:
            previous_shape.clear_highlight()
            need_update = True
        # NOTE: Store last highlighted for adding/removing points.
        self._last_hovered_shape = (
            previous_shape if hovered_shape is None else hovered_shape
        )
        self._last_hovered_vertex = (
            self.hovered_vertex if hovered_vertex is None else hovered_vertex
        )
        self._last_hovered_edge = (
            self.hovered_edge if hovered_edge is None else hovered_edge
        )
        self.hovered_shape = hovered_shape
        self.hovered_vertex = hovered_vertex
        self.hovered_edge = hovered_edge
        return need_update

    def is_vertex_selected(self) -> bool:
        return self.hovered_vertex is not None

    def is_edge_selected(self) -> bool:
        return self.hovered_edge is not None

    def _update_status(self, extra_messages: list[str] | None = None) -> None:
        messages: list[str] = []
        if self.drawing():
            messages.append(self.tr("Creating %r") % self.create_mode)
            messages.append(self._get_create_mode_message())
            if self.current:
                messages.append(self.tr("ESC to cancel"))
            if self.can_close_shape():
                messages.append(self.tr("Enter or Space to finalize"))
        else:
            assert self.editing()
            messages.append(self.tr("Editing shapes"))
        if extra_messages:
            messages.extend(extra_messages)
        self.status_updated.emit(" • ".join(messages))

    def _get_create_mode_message(self) -> str:
        assert self.drawing()
        is_new: bool = self.current is None
        if self.create_mode == "ai_points_to_shape":
            return self.tr(
                "Click points to include or Shift+Click to exclude."
                " Ctrl+LeftClick ends creation."
            )
        if self.create_mode == "ai_box_to_shape":
            if is_new:
                return self.tr("Click first corner of bbox for AI segmentation")
            else:
                return self.tr("Click opposite corner to segment object")
        if self.create_mode == "line":
            if is_new:
                return self.tr("Click start point for line")
            else:
                return self.tr("Click end point for line")
        if self.create_mode == "linestrip":
            if is_new:
                return self.tr("Click start point for linestrip")
            else:
                return self.tr(
                    "Click next point or finish by Ctrl/Cmd+Click for linestrip"
                )
        if self.create_mode == "circle":
            if is_new:
                return self.tr("Click center point for circle")
            else:
                return self.tr("Click point on circumference for circle")
        if self.create_mode == "rectangle":
            if is_new:
                return self.tr("Click first corner for rectangle")
            else:
                return self.tr("Click opposite corner for rectangle (Shift for square)")
        return self.tr("Click to add point")

    def mouseMoveEvent(self, a0: QtGui.QMouseEvent) -> None:
        try:
            pos = self._transform_point_widget_to_image(a0.localPos())
        except AttributeError:
            return
        self.mouse_moved.emit(pos)
        self.prev_move_point = pos
        self._dispatch_pointer_move(pos=pos, event=a0)

    def _dispatch_pointer_move(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        if self._pan_anchor is not None:
            self._advance_pan(event=event)
            return
        if self.drawing():
            self._track_drawing_cursor(pos=pos, event=event)
            return
        buttons = event.buttons()
        if buttons & Qt.RightButton:
            self._continue_right_button_drag(pos=pos)
            return
        if buttons & Qt.LeftButton:
            self._continue_left_button_drag(pos=pos, event=event)
            return
        self._refresh_hover_state(pos=pos)

    def _advance_pan(self, event: QtGui.QMouseEvent) -> None:
        assert self._pan_anchor is not None
        # Use screen coordinates so the anchor does not drift when our own
        # pan emit shifts the canvas widget under the scroll area — a
        # widget-local frame would oscillate and cause juggling.
        cursor: QPointF = QPointF(self.mapToGlobal(event.pos()))
        step: QPointF = cursor - self._pan_anchor
        self._pan_anchor = cursor
        self.pan_request.emit(QPoint(int(step.x()), int(step.y())))

    def _track_drawing_cursor(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        LINE_SHAPE_TYPE_OVERRIDES: Final[dict[str, str]] = {
            "ai_points_to_shape": "points",
            "ai_box_to_shape": "rectangle",
        }
        self.line.shape_type = LINE_SHAPE_TYPE_OVERRIDES.get(
            self.create_mode, self.create_mode
        )
        self._apply_cursor(CURSOR_DRAW)
        if self.current is None:
            self.update()
            self._update_status()
            return
        is_shift_pressed = bool(event.modifiers() & Qt.ShiftModifier)
        pos = self._project_drawing_pos_into_image(pos=pos)
        self._update_drawing_line(pos=pos, is_shift_pressed=is_shift_pressed)
        assert len(self.line.points) == len(self.line.point_labels)
        self.update()
        self._update_status()

    def _project_drawing_pos_into_image(self, pos: QPointF) -> QPointF:
        current = self.current
        assert current is not None
        if self.is_out_of_pixmap(pos):
            return _compute_intersection_edges_image(
                current[-1], pos, image_size=self.pixmap.size()
            )
        if not self._cursor_should_snap_to_polygon_origin(pos=pos):
            return pos
        self._apply_cursor(CURSOR_POINT)
        current.highlight_vertex(i=0, action=Shape.NEAR_VERTEX)
        return current[0]

    def _cursor_should_snap_to_polygon_origin(self, pos: QPointF) -> bool:
        if not self.snapping:
            return False
        if self.create_mode != "polygon":
            return False
        current = self.current
        if current is None or len(current) <= 1:
            return False
        return self.is_close_enough(pos, current[0])

    def _refresh_hover_state(self, pos: QPointF) -> None:
        status_messages: list[str] = []
        self._highlight_hover_shape(pos=pos, status_messages=status_messages)
        self.vertex_selected.emit(self.hovered_vertex is not None)
        self._update_status(extra_messages=status_messages)

    def _update_drawing_line(self, pos: QPointF, is_shift_pressed: bool) -> QPointF:
        current = self.current
        assert current is not None
        mode = self.create_mode
        if mode in ("polygon", "linestrip"):
            self.line.points = [current[-1], pos]
            self.line.point_labels = [1, 1]
        elif mode == "ai_points_to_shape":
            self.line.points = [current.points[-1], pos]
            self.line.point_labels = [
                current.point_labels[-1],
                0 if is_shift_pressed else 1,
            ]
        elif mode in ("rectangle", "ai_box_to_shape"):
            if is_shift_pressed:
                pos = _snap_cursor_pos_for_square(pos=pos, opposite_vertex=current[0])
                self.prev_move_point = pos
            self.line.points = [current[0], pos]
            self.line.point_labels = [1, 1]
            self.line.close()
        elif mode == "circle":
            self.line.points = [current[0], pos]
            self.line.point_labels = [1, 1]
            self.line.shape_type = "circle"
        elif mode == "line":
            self.line.points = [current[0], pos]
            self.line.point_labels = [1, 1]
            self.line.close()
        elif mode == "point":
            self.line.points = [current[0]]
            self.line.point_labels = [1]
            self.line.close()
        return pos

    def _continue_right_button_drag(self, pos: QPointF) -> None:
        if self.selected_shapes_copy:
            self._apply_cursor(CURSOR_MOVE)
            self.bounded_move_shapes(shapes=self.selected_shapes_copy, pos=pos)
            self.update()
        elif self.selected_shapes:
            self.selected_shapes_copy = [s.copy() for s in self.selected_shapes]
            self.update()
        self._update_status()

    def _continue_left_button_drag(
        self, pos: QPointF, event: QtGui.QMouseEvent
    ) -> None:
        is_shift_pressed = bool(event.modifiers() & Qt.ShiftModifier)
        if self.is_vertex_selected():
            self._drag_hovered_vertex(pos=pos, is_shift_pressed=is_shift_pressed)
            return
        if not self.selected_shapes:
            return
        self._drag_selected_shapes(pos=pos)

    def _drag_hovered_vertex(self, pos: QPointF, is_shift_pressed: bool) -> None:
        assert self.hovered_vertex is not None
        assert self.hovered_shape is not None
        self.bounded_move_vertex(
            self.hovered_shape,
            self.hovered_vertex,
            pos,
            is_shift_pressed=is_shift_pressed,
        )
        self.update()
        self.is_moving_shape = True

    def _drag_selected_shapes(self, pos: QPointF) -> None:
        self._apply_cursor(CURSOR_MOVE)
        self.bounded_move_shapes(shapes=self.selected_shapes, pos=pos)
        self.update()
        self.is_moving_shape = True

    def _highlight_hover_shape(self, pos: QPointF, status_messages: list[str]) -> None:
        ordered_shapes: list[Shape] = (
            [self.hovered_shape] if self.hovered_shape else []
        ) + [
            s
            for s in reversed(self.shapes)
            if self.is_shape_visible(s) and s != self.hovered_shape
        ]

        for shape in ordered_shapes:
            index: int | None = shape.nearest_vertex(pos, self.epsilon)
            if index is not None:
                self._set_highlight(
                    hovered_shape=shape, hovered_edge=None, hovered_vertex=index
                )
                shape.highlight_vertex(i=index, action=shape.MOVE_VERTEX)
                self._apply_cursor(CURSOR_POINT)
                status_messages.append(self.tr("Click & drag to move point"))
                if shape.can_remove_point():
                    status_messages.append(
                        self.tr("ALT + SHIFT + Click to delete point")
                    )
                self.update()
                return

        for shape in ordered_shapes:
            index_edge: int | None = shape.nearest_edge(pos, self.epsilon)
            if index_edge is not None and shape.can_add_point():
                self._set_highlight(
                    hovered_shape=shape, hovered_edge=index_edge, hovered_vertex=None
                )
                self._apply_cursor(CURSOR_POINT)
                status_messages.append(self.tr("ALT + Click to create point on shape"))
                self.update()
                return

        for shape in ordered_shapes:
            if shape.contains_point(pos):
                self._set_highlight(
                    hovered_shape=shape, hovered_edge=None, hovered_vertex=None
                )
                status_messages.extend(
                    [
                        self.tr("Click & drag to move shape"),
                        self.tr("Right-click & drag to copy shape"),
                    ]
                )
                self._apply_cursor(CURSOR_GRAB)
                self.update()
                return

        self._release_cursor()
        if self._set_highlight(
            hovered_shape=None, hovered_edge=None, hovered_vertex=None
        ):
            self.update()

    def add_point_to_edge(self) -> None:
        shape = self._last_hovered_shape
        index = self._last_hovered_edge
        point = self.prev_move_point
        if shape is None or index is None or point is None:
            return
        shape.insert_point(index, point)
        shape.highlight_vertex(i=index, action=shape.MOVE_VERTEX)
        self.hovered_shape = shape
        self.hovered_vertex = index
        self.hovered_edge = None
        self.is_moving_shape = True

    def remove_selected_point(self) -> None:
        shape = self._last_hovered_shape
        index = self._last_hovered_vertex
        if shape is None or index is None:
            return
        shape.remove_point(index)
        shape.clear_highlight()
        self.hovered_shape = shape
        self._last_hovered_vertex = None
        self.is_moving_shape = True  # Save changes

    def mousePressEvent(self, a0: QtGui.QMouseEvent) -> None:
        pos: QPointF = self._transform_point_widget_to_image(a0.localPos())
        self._dispatch_pointer_press(pos=pos, event=a0)
        self._update_status()

    def _dispatch_pointer_press(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        button = event.button()
        if button == Qt.LeftButton:
            self._press_left(pos=pos, event=event)
            return
        if button == Qt.RightButton and self.editing():
            self._press_right(pos=pos, event=event)
            return
        if button == Qt.MiddleButton and self._is_image_overflowing_viewport():
            self._begin_pan(event=event)

    def _press_left(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        is_shift_pressed = bool(event.modifiers() & Qt.ShiftModifier)
        if self.drawing():
            self._press_left_while_drawing(
                pos=pos, event=event, is_shift_pressed=is_shift_pressed
            )
            return
        if self.editing():
            self._press_left_while_editing(pos=pos, event=event)

    def _press_left_while_drawing(
        self,
        pos: QPointF,
        event: QtGui.QMouseEvent,
        is_shift_pressed: bool,
    ) -> None:
        if self.current is not None:
            self._extend_current_shape(current=self.current, event=event)
            return
        if self.is_out_of_pixmap(pos):
            return
        self._start_new_shape(pos=pos, event=event, is_shift_pressed=is_shift_pressed)

    def _extend_current_shape(self, current: Shape, event: QtGui.QMouseEvent) -> None:
        mode = self.create_mode
        modifiers = event.modifiers()
        if mode == "polygon":
            current.add_point(self.line[1])
            self.line[0] = current[-1]
            if current.is_closed():
                self.finalise()
        elif mode in ("rectangle", "circle", "line", "ai_box_to_shape"):
            assert len(current.points) == 1
            current.points = self.line.points
            self.finalise()
        elif mode == "linestrip":
            current.add_point(self.line[1])
            self.line[0] = current[-1]
            if int(modifiers) == Qt.ControlModifier:
                self.finalise()
        elif mode == "ai_points_to_shape":
            current.add_point(
                self.line.points[1],
                label=self.line.point_labels[1],
            )
            self.line.points[0] = current.points[-1]
            self.line.point_labels[0] = current.point_labels[-1]
            if modifiers & Qt.ControlModifier:
                self.finalise()

    def _start_new_shape(
        self,
        pos: QPointF,
        event: QtGui.QMouseEvent,
        is_shift_pressed: bool,
    ) -> None:
        mode = self.create_mode
        if mode in ("ai_points_to_shape", "ai_box_to_shape") and not download_ai_model(
            model_name=self._osam_session_model_name, parent=self
        ):
            return

        initial_shape_type = {
            "ai_points_to_shape": "points",
            "ai_box_to_shape": "rectangle",
        }.get(mode, mode)
        new_shape = Shape(shape_type=initial_shape_type)
        new_shape.add_point(pos, label=0 if is_shift_pressed else 1)
        self.current = new_shape

        if mode == "point":
            self.finalise()
            return
        if mode == "ai_points_to_shape" and event.modifiers() & Qt.ControlModifier:
            self.finalise()
            return

        if mode == "circle":
            new_shape.shape_type = "circle"
        self.line.points = [pos, pos]
        self.line.point_labels = (
            [0, 0] if mode == "ai_points_to_shape" and is_shift_pressed else [1, 1]
        )
        self.set_hide_background()
        self.drawing_polygon.emit(True)
        self.update()

    def _press_left_while_editing(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        modifiers = event.modifiers()
        self._maybe_modify_polygon_topology(modifiers=modifiers)
        self.select_shape_point(
            pos,
            multiple_selection_mode=int(modifiers) == Qt.ControlModifier,
        )
        self.prev_point = pos
        self.update()

    def _maybe_modify_polygon_topology(self, modifiers: Qt.KeyboardModifiers) -> None:
        if self.is_edge_selected() and modifiers == Qt.AltModifier:
            self.add_point_to_edge()
            return
        if self.is_vertex_selected() and modifiers == (
            Qt.AltModifier | Qt.ShiftModifier
        ):
            self.remove_selected_point()

    def _press_right(self, pos: QPointF, event: QtGui.QMouseEvent) -> None:
        if _should_reselect_on_right_press(
            selected_shapes=self.selected_shapes, hovered_shape=self.hovered_shape
        ):
            self.select_shape_point(
                pos,
                multiple_selection_mode=int(event.modifiers()) == Qt.ControlModifier,
            )
            self.update()
        self.prev_point = pos

    def _begin_pan(self, event: QtGui.QMouseEvent) -> None:
        self._apply_cursor(CURSOR_GRAB)
        self._pan_anchor = QPointF(self.mapToGlobal(event.pos()))

    def mouseReleaseEvent(self, a0: QtGui.QMouseEvent) -> None:
        self._dispatch_pointer_release(event=a0)
        self._commit_pending_shape_move()
        self._update_status()

    def _dispatch_pointer_release(self, event: QtGui.QMouseEvent) -> None:
        button = event.button()
        if button == Qt.RightButton:
            self._release_right(event=event)
            return
        if button == Qt.LeftButton:
            self._release_left()
            return
        if button == Qt.MiddleButton:
            self._finish_pan()

    def _release_right(self, event: QtGui.QMouseEvent) -> None:
        menu = self.menus[len(self.selected_shapes_copy) > 0]
        self._release_cursor()
        if menu.exec_(self.mapToGlobal(event.pos())):  # type: ignore
            return
        if not self.selected_shapes_copy:
            return
        self.selected_shapes_copy.clear()
        self.update()

    def _release_left(self) -> None:
        if not self.editing():
            return
        if self.hovered_shape is None:
            return
        if not self.hovered_shape_is_selected:
            return
        if self.is_moving_shape:
            return
        self.selection_changed.emit(
            [s for s in self.selected_shapes if s != self.hovered_shape]
        )

    def _finish_pan(self) -> None:
        # Reset state and cursor unconditionally so a stray middle-button
        # release can never leave a grab cursor stuck on screen.
        self._pan_anchor = None
        self._release_cursor()

    def _is_image_overflowing_viewport(self) -> bool:
        if self.pixmap.isNull():
            return False
        viewport = self._scroll_viewport()
        if viewport is None:
            return False
        scaled_w = self.pixmap.width() * self.scale
        scaled_h = self.pixmap.height() * self.scale
        return scaled_w > viewport.width() or scaled_h > viewport.height()

    def _scroll_viewport(self) -> QtWidgets.QWidget | None:
        # Walk up the parent chain to the enclosing scroll area and return
        # its viewport. Returning None when no scroll area is found lets
        # callers degrade gracefully if the canvas is reparented (e.g. into
        # a splitter or a test harness).
        node: QtWidgets.QWidget | None = self.parentWidget()
        while node is not None:
            if isinstance(node, QtWidgets.QAbstractScrollArea):
                return node.viewport()
            node = node.parentWidget()
        return None

    def _commit_pending_shape_move(self) -> None:
        moved = _pick_pending_moved_shape(
            is_moving_shape=self.is_moving_shape,
            hovered_shape=self.hovered_shape,
            shapes=self.shapes,
        )
        if moved is None:
            return
        index = self.shapes.index(moved)
        if self.shape_backups[-1][index].points != self.shapes[index].points:
            self.backup_shapes()
            self.shape_moved.emit()
        self.is_moving_shape = False

    def end_move(self, copy: bool) -> bool:
        assert self.selected_shapes and self.selected_shapes_copy
        assert len(self.selected_shapes_copy) == len(self.selected_shapes)
        if copy:
            self._apply_copy_move()
        else:
            self._apply_in_place_move()
        self.selected_shapes_copy.clear()
        self.update()
        self.backup_shapes()
        return True

    def _apply_copy_move(self) -> None:
        for i, (original, copy) in enumerate(
            zip(self.selected_shapes, self.selected_shapes_copy)
        ):
            self.shapes.append(copy)
            original.selected = False
            self.selected_shapes[i] = copy

    def _apply_in_place_move(self) -> None:
        for original, copy in zip(self.selected_shapes, self.selected_shapes_copy):
            original.points = copy.points

    def hide_background_shapes(self, value: bool) -> None:
        self.hide_background = value
        if not self.selected_shapes:
            return
        self.set_hide_background(True)
        self.update()

    def set_hide_background(self, enable: bool = True) -> None:
        self._hide_background = self.hide_background if enable else False

    def can_close_shape(self) -> bool:
        if not self.drawing():
            return False
        if not self.current:
            return False
        if self.create_mode == "ai_points_to_shape":
            return True
        if self.create_mode == "linestrip":
            return len(self.current) >= 2
        return len(self.current) >= 3

    def mouseDoubleClickEvent(self, a0: QtGui.QMouseEvent) -> None:
        if self.double_click != "close":
            return
        if not self.can_close_shape():
            return
        self.finalise()

    def select_shapes(self, shapes: list[Shape]) -> None:
        self.set_hide_background()
        self.selection_changed.emit(shapes)
        self.update()

    def select_shape_point(self, point: QPointF, multiple_selection_mode: bool) -> None:
        """Select the first shape created which contains this point."""
        if self.hovered_vertex is not None:
            assert self.hovered_shape is not None
            self.hovered_shape.highlight_vertex(
                i=self.hovered_vertex, action=self.hovered_shape.MOVE_VERTEX
            )
            if self.deselect_shape():
                self.update()
            return

        clicked_shape = self._find_shape_at_point(point)
        if clicked_shape is None:
            if self.deselect_shape():
                self.update()
            return

        self.set_hide_background()
        already_selected = clicked_shape in self.selected_shapes
        if already_selected:
            self.hovered_shape_is_selected = True
        else:
            new_selection = (
                self.selected_shapes + [clicked_shape]
                if multiple_selection_mode
                else [clicked_shape]
            )
            self.selection_changed.emit(new_selection)
            self.hovered_shape_is_selected = False
        self.calculate_offsets(point)

    def _find_shape_at_point(self, point: QPointF) -> Shape | None:
        for shape in reversed(self.shapes):
            if self.is_shape_visible(shape) and shape.contains_point(point):
                return shape
        return None

    def calculate_offsets(self, point: QPointF) -> None:
        if not self.selected_shapes:
            self.offsets = QPointF(0.0, 0.0), QPointF(0.0, 0.0)
            return

        rects = [s.bounding_rect() for s in self.selected_shapes]
        left = min(r.left() for r in rects)
        top = min(r.top() for r in rects)
        right = max(r.right() for r in rects)
        bottom = max(r.bottom() for r in rects)

        self.offsets = (
            QPointF(left - point.x(), top - point.y()),
            QPointF(right - point.x(), bottom - point.y()),
        )

    def bounded_move_vertex(
        self, shape: Shape, vertex_index: int, pos: QPointF, is_shift_pressed: bool
    ) -> None:
        if vertex_index >= len(shape.points):
            logger.warning(
                "vertex_index is out of range: vertex_index={:d}, len(points)={:d}",
                vertex_index,
                len(shape.points),
            )
            return

        if self.is_out_of_pixmap(pos):
            pos = _compute_intersection_edges_image(
                shape[vertex_index], pos, image_size=self.pixmap.size()
            )

        if is_shift_pressed and shape.shape_type == "rectangle":
            pos = _snap_cursor_pos_for_square(
                pos=pos, opposite_vertex=shape[1 - vertex_index]
            )

        shape.move_vertex(i=vertex_index, pos=pos)

    def bounded_move_shapes(self, shapes: list[Shape], pos: QPointF) -> bool:
        if self.is_out_of_pixmap(pos):
            return False

        tl = pos + self.offsets[0]
        if self.is_out_of_pixmap(tl):
            pos -= QPointF(min(0, tl.x()), min(0, tl.y()))

        br = pos + self.offsets[1]
        if self.is_out_of_pixmap(br):
            pos += QPointF(
                min(0, self.pixmap.width() - br.x()),
                min(0, self.pixmap.height() - br.y()),
            )

        dp = pos - self.prev_point
        if dp.isNull():
            return False

        for shape in shapes:
            shape.move_by(dp)
        self.prev_point = pos
        return True

    def deselect_shape(self) -> bool:
        if not self.selected_shapes:
            return False
        self.set_hide_background(False)
        self.selection_changed.emit([])
        self.hovered_shape_is_selected = False
        return True

    def delete_selected(self) -> list[Shape]:
        if not self.selected_shapes:
            return []
        removed = list(self.selected_shapes)
        self.shapes = [s for s in self.shapes if s not in self.selected_shapes]
        self.backup_shapes()
        self.selected_shapes.clear()
        self.update()
        return removed

    def delete_shape(self, shape: Shape) -> None:
        if shape in self.selected_shapes:
            self.selected_shapes.remove(shape)
        self.shapes = [s for s in self.shapes if s is not shape]
        self.backup_shapes()
        self.update()

    def paintEvent(self, a0: QtGui.QPaintEvent) -> None:
        if self.pixmap.isNull():
            super().paintEvent(a0)
            return
        self._render_canvas()
        if self.current is not None:
            self.current.clear_highlight()

    def _render_canvas(self) -> None:
        painter: QtGui.QPainter = self._painter
        painter.begin(self)
        try:
            self._setup_world_transform(painter=painter)
            for layer in self._render_layers():
                layer(painter)
        finally:
            painter.end()

    def _setup_world_transform(self, painter: QtGui.QPainter) -> None:
        for hint in (
            QtGui.QPainter.Antialiasing,
            QtGui.QPainter.HighQualityAntialiasing,
            QtGui.QPainter.SmoothPixmapTransform,
        ):
            painter.setRenderHint(hint)
        painter.translate(self._compute_image_origin_offset() * self.scale)
        Shape.scale = self.scale

    def _render_layers(self) -> tuple[Callable[[QtGui.QPainter], None], ...]:
        # Order is z-order, back-to-front.
        return (
            self._draw_pixmap_layer,
            self._draw_crosshair_layer,
            self._draw_committed_shapes_layer,
            self._draw_active_shape_layer,
            self._draw_drag_copy_layer,
            self._draw_preview_overlay_layer,
        )

    def _draw_pixmap_layer(self, painter: QtGui.QPainter) -> None:
        target = QtCore.QRectF(
            0.0,
            0.0,
            self.pixmap.width() * self.scale,
            self.pixmap.height() * self.scale,
        )
        painter.drawPixmap(target, self.pixmap, QtCore.QRectF(self.pixmap.rect()))

    def _draw_crosshair_layer(self, painter: QtGui.QPainter) -> None:
        cursor: QPointF | None = self.prev_move_point
        if not self._should_draw_crosshair(cursor=cursor):
            return
        assert cursor is not None
        painter.setPen(QtGui.QColor(0, 0, 0))
        cx = int(cursor.x() * self.scale)
        cy = int(cursor.y() * self.scale)
        max_x = int(self.pixmap.width() * self.scale) - 1
        max_y = int(self.pixmap.height() * self.scale) - 1
        painter.drawLine(0, cy, max_x, cy)
        painter.drawLine(cx, 0, cx, max_y)

    def _should_draw_crosshair(self, cursor: QPointF | None) -> bool:
        if not self.drawing():
            return False
        if not self._crosshair[self._create_mode]:
            return False
        if cursor is None:
            return False
        return not self.is_out_of_pixmap(cursor)

    def _draw_committed_shapes_layer(self, painter: QtGui.QPainter) -> None:
        for shape in self.shapes:
            if not _is_shape_paintable(
                shape=shape,
                visible=self.is_shape_visible(shape),
                hide_background=self._hide_background,
            ):
                continue
            shape.fill = _is_shape_filled(shape=shape, hovered_shape=self.hovered_shape)
            shape.paint(painter)

    def _draw_active_shape_layer(self, painter: QtGui.QPainter) -> None:
        if self.current is None:
            return
        self.current.paint(painter)
        assert len(self.line.points) == len(self.line.point_labels)
        self.line.paint(painter)

    def _draw_drag_copy_layer(self, painter: QtGui.QPainter) -> None:
        for copy_shape in self.selected_shapes_copy:
            copy_shape.paint(painter)

    def _draw_preview_overlay_layer(self, painter: QtGui.QPainter) -> None:
        preview = self._build_preview_shape()
        if preview is None:
            return
        preview.fill = self.fill_drawing()
        preview.selected = self.fill_drawing()
        preview.paint(painter)

    def _build_preview_shape(self) -> Shape | None:
        if self.current is None:
            return None
        if self.create_mode == "polygon":
            return self._build_polygon_preview(current=self.current)
        if self.create_mode == "ai_points_to_shape":
            return self._build_ai_points_preview(current=self.current)
        return None

    def _build_polygon_preview(self, current: Shape) -> Shape:
        preview: Shape = current.copy()
        if not self.fill_drawing():
            return preview
        if len(preview.points) < 2:
            return preview
        assert preview.fill_color is not None
        if preview.fill_color.getRgb()[3] == 0:
            logger.warning(
                "fill_drawing=true, but fill_color is transparent,"
                " so forcing to be opaque."
            )
            preview.fill_color.setAlpha(64)
        preview.add_point(point=self.line[1])
        return preview

    def _build_ai_points_preview(self, current: Shape) -> Shape:
        preview: Shape = current.copy()
        preview.add_point(
            point=self.line.points[1],
            label=self.line.point_labels[1],
        )
        ai_shapes = self._shapes_from_points_ai(
            points=preview.points,
            point_labels=preview.point_labels,
        )
        if ai_shapes:
            return ai_shapes[0]
        return preview

    def _transform_point_widget_to_image(self, point: QPointF) -> QPointF:
        return point / self.scale - self._compute_image_origin_offset()

    def _compute_image_origin_offset(self) -> QPointF:
        area = super().size()
        scaled_w = self.pixmap.width() * self.scale
        scaled_h = self.pixmap.height() * self.scale
        slack_w = max(area.width() - scaled_w, 0.0)
        slack_h = max(area.height() - scaled_h, 0.0)
        return QPointF(slack_w, slack_h) / (2.0 * self.scale)

    def is_out_of_pixmap(self, p: QPointF) -> bool:
        w = self.pixmap.width()
        h = self.pixmap.height()
        return not (0 <= p.x() <= w and 0 <= p.y() <= h)

    def finalise(self) -> None:
        assert self.current is not None
        new_shapes: list[Shape] = self._build_new_shapes_from_current()
        if not new_shapes:
            self.current = None
            return
        self.shapes.extend(new_shapes)
        self.backup_shapes()
        self._reset_after_shape_creation()

    def _build_new_shapes_from_current(self) -> list[Shape]:
        assert self.current is not None
        if self.create_mode == "ai_points_to_shape":
            return self._shapes_from_points_ai(
                points=self.current.points,
                point_labels=self.current.point_labels,
            )
        if self.create_mode == "ai_box_to_shape":
            return self._shapes_from_bbox_ai(bbox_points=self.current.points)
        self.current.close()
        return [self.current]

    def _reset_after_shape_creation(self) -> None:
        self.current = None
        self.set_hide_background(False)
        self.new_shape.emit()
        self.update()

    def _cancel_current_shape(self) -> None:
        self.current = None
        self.drawing_polygon.emit(False)
        self.update()

    def is_close_enough(self, p1: QPointF, p2: QPointF) -> bool:
        # d = distance(p1 - p2)
        # m = (p1-p2).manhattanLength()
        # print "d %.2f, m %d, %.2f" % (d, m, d - m)
        # divide by scale to allow more precision when zoomed in
        return labelme.utils.distance(p1 - p2) < (self.epsilon / self.scale)

    # Required by QScrollArea: it queries these to compute the
    # scrollable viewport whenever adjustSize() is called.
    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSizeHint()

    def minimumSizeHint(self) -> QtCore.QSize:
        if self.pixmap.isNull():
            return super().minimumSizeHint()
        scaled_w = int(self.pixmap.width() * self.scale)
        scaled_h = int(self.pixmap.height() * self.scale)
        viewport = self._scroll_viewport()
        if viewport is None:
            return QtCore.QSize(scaled_w, scaled_h)
        # Overscroll only along axes where the image actually overflows the
        # viewport. Half a viewport of slack (split evenly around the centred
        # image) lets each edge be panned a quarter-viewport past the viewport
        # boundary, derived from the viewport rather than a fixed multiplier.
        slack_w = viewport.width() // 2 if scaled_w > viewport.width() else 0
        slack_h = viewport.height() // 2 if scaled_h > viewport.height() else 0
        return QtCore.QSize(scaled_w + slack_w, scaled_h + slack_h)

    def wheelEvent(self, a0: QtGui.QWheelEvent) -> None:
        mods: Qt.KeyboardModifiers = a0.modifiers()
        delta: QPoint = a0.angleDelta()
        if Qt.ControlModifier == int(mods):
            # with Ctrl/Command key
            # zoom
            self.zoom_request.emit(delta.y(), a0.posF())
        elif int(mods) == int(Qt.ShiftModifier) and delta.x() == 0:
            # Shift+wheel scrolls horizontally. macOS swaps the axis for us,
            # but Linux/Windows deliver the delta on y and expect the app to
            # remap it.
            self.scroll_request.emit(delta.y(), Qt.Horizontal)
        else:
            # scroll
            self.scroll_request.emit(delta.x(), Qt.Horizontal)
            self.scroll_request.emit(delta.y(), Qt.Vertical)
        a0.accept()

    def move_by_keyboard(self, offset: QPointF) -> None:
        if not self.selected_shapes:
            return
        self.bounded_move_shapes(
            shapes=self.selected_shapes, pos=self.prev_point + offset
        )
        self.update()
        self.is_moving_shape = True

    def keyPressEvent(self, a0: QtGui.QKeyEvent) -> None:
        modifiers = a0.modifiers()
        key = a0.key()
        if self.drawing():
            if key == Qt.Key_Escape and self.current:
                self._cancel_current_shape()
            elif (
                key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Space)
                and self.can_close_shape()
            ):
                self.finalise()
            elif modifiers == Qt.AltModifier:
                self.snapping = False
        elif self.editing():
            if key == Qt.Key_Up:
                self.move_by_keyboard(QPointF(0.0, -MOVE_SPEED))
            elif key == Qt.Key_Down:
                self.move_by_keyboard(QPointF(0.0, MOVE_SPEED))
            elif key == Qt.Key_Left:
                self.move_by_keyboard(QPointF(-MOVE_SPEED, 0.0))
            elif key == Qt.Key_Right:
                self.move_by_keyboard(QPointF(MOVE_SPEED, 0.0))
            elif a0.matches(QtGui.QKeySequence.SelectAll):
                self.select_shapes(shapes=self.shapes[:])
        self._update_status()

    def keyReleaseEvent(self, a0: QtGui.QKeyEvent) -> None:
        modifiers = a0.modifiers()
        if self.drawing():
            if int(modifiers) == 0:
                self.snapping = True
        elif self.editing():
            if (
                self.is_moving_shape
                and self.selected_shapes
                and self.selected_shapes[0] in self.shapes
            ):
                index = self.shapes.index(self.selected_shapes[0])
                if self.shape_backups[-1][index].points != self.shapes[index].points:
                    self.backup_shapes()
                    self.shape_moved.emit()

                self.is_moving_shape = False

    def set_last_label(self, text: str, flags: dict[str, bool]) -> list[Shape]:
        if not text:
            raise ValueError("text must not be empty")
        shapes = []
        for shape in reversed(self.shapes):
            if shape.label is not None:
                break
            shapes.append(shape)
        shapes.reverse()
        for shape in shapes:
            shape.label = text
            shape.flags = flags
        self.shape_backups.pop()
        self.backup_shapes()
        return shapes

    def undo_last_line(self) -> None:
        assert self.shapes
        if self.create_mode in ("ai_points_to_shape", "ai_box_to_shape"):
            # Remove all unlabeled shapes at the tail (added by AI in one shot)
            while self.shapes and self.shapes[-1].label is None:
                self.shapes.pop()
            self._cancel_current_shape()
            return
        self.current = self.shapes.pop()
        self.current.open()
        self.current.unrefine()
        if self.create_mode in ("polygon", "linestrip"):
            self.line.points = [self.current[-1], self.current[0]]
        elif self.create_mode in ("rectangle", "line", "circle", "ai_box_to_shape"):
            self.current.points = self.current.points[0:1]
        elif self.create_mode == "point":
            self.current = None
        self.drawing_polygon.emit(True)

    def undo_last_point(self) -> None:
        current = self.current
        if current is None or current.is_closed():
            return
        current.pop_point()
        if len(current) > 0:
            self.line[0] = current[-1]
            self.update()
        else:
            self._cancel_current_shape()

    def load_pixmap(self, pixmap: QtGui.QPixmap, clear_shapes: bool = True) -> None:
        self.pixmap = pixmap
        self._pixmap_hash = hash(
            labelme.utils.img_qt_to_arr(img_qt=self.pixmap.toImage()).tobytes()
        )
        if clear_shapes:
            self.shapes = []
        self.update()

    def load_shapes(self, shapes: list[Shape], replace: bool = True) -> None:
        if replace:
            self.shapes = list(shapes)
        else:
            self.shapes.extend(shapes)
        self.backup_shapes()
        self.current = None
        self.hovered_shape = None
        self.hovered_vertex = None
        self.hovered_edge = None
        self.update()

    def set_shape_visible(self, shape: Shape, value: bool) -> None:
        self.visible[shape] = value
        self.update()

    def _apply_cursor(self, cursor: QtCore.Qt.CursorShape) -> None:
        if cursor == self._cursor:
            return
        # Push on first apply; swap the top of the stack we already own afterwards.
        if self._cursor == CURSOR_DEFAULT:
            QtWidgets.QApplication.setOverrideCursor(cursor)
        else:
            QtWidgets.QApplication.changeOverrideCursor(cursor)
        self._cursor = cursor

    def _release_cursor(self) -> None:
        if self._cursor == CURSOR_DEFAULT:
            return
        self._cursor = CURSOR_DEFAULT
        QtWidgets.QApplication.restoreOverrideCursor()

    def reset_state(self) -> None:
        self._release_cursor()
        self.pixmap = QtGui.QPixmap()
        self._pixmap_hash = None
        self.shapes = []
        self.shape_backups = collections.deque(maxlen=self.num_backups)
        self.is_moving_shape = False
        self.selected_shapes = []
        self.selected_shapes_copy = []
        self.current = None
        self.hovered_shape = None
        self._last_hovered_shape = None
        self.hovered_vertex = None
        self._last_hovered_vertex = None
        self.hovered_edge = None
        self._last_hovered_edge = None
        self.update()


def _shape_from_annotation(
    annotation: osam.types.Annotation,
    output_format: Literal["polygon", "mask"],
) -> Shape | None:
    if annotation.mask is None:
        return None

    mask: np.ndarray = annotation.mask

    if output_format == "mask":
        if annotation.bounding_box is None:
            return None
        bb = annotation.bounding_box
        shape = Shape()
        shape.refine(
            shape_type="mask",
            points=[QPointF(bb.xmin, bb.ymin), QPointF(bb.xmax, bb.ymax)],
            point_labels=[1, 1],
            mask=mask,
        )
        shape.close()
        return shape
    elif output_format == "polygon":
        points = polygon_from_mask.compute_polygon_from_mask(mask=mask)
        if len(points) < 2:
            return None
        if annotation.bounding_box is not None:
            bb = annotation.bounding_box
            points = points + np.array([bb.xmin, bb.ymin], dtype=np.float32)
        shape = Shape()
        shape.refine(
            shape_type="polygon",
            points=[QPointF(point[0], point[1]) for point in points],
            point_labels=[1] * len(points),
        )
        shape.close()
        return shape
    raise ValueError(f"Unsupported output_format: {output_format!r}")


def _shapes_from_ai_response(
    response: osam.types.GenerateResponse,
    output_format: Literal["polygon", "mask"],
) -> list[Shape]:
    if output_format not in ["polygon", "mask"]:
        raise ValueError(
            f"output_format must be 'polygon' or 'mask', not {output_format}"
        )

    if not response.annotations:
        logger.warning("No annotations returned")
        return []

    annotations = sorted(
        response.annotations,
        key=lambda a: a.score if a.score is not None else 0,
        reverse=True,
    )

    shapes: list[Shape] = []
    for annotation in annotations:
        shape = _shape_from_annotation(
            annotation=annotation, output_format=output_format
        )
        if shape is not None:
            shapes.append(shape)
    return shapes


def _snap_cursor_pos_for_square(pos: QPointF, opposite_vertex: QPointF) -> QPointF:
    pos_from_opposite: QPointF = pos - opposite_vertex
    square_size: float = min(abs(pos_from_opposite.x()), abs(pos_from_opposite.y()))
    return opposite_vertex + QPointF(
        np.sign(pos_from_opposite.x()) * square_size,
        np.sign(pos_from_opposite.y()) * square_size,
    )


def _compute_intersection_edges_image(
    p1: QPointF, p2: QPointF, image_size: QtCore.QSize
) -> QPointF:
    width = image_size.width()
    height = image_size.height()

    start_x = np.clip(p1.x(), 0.0, width)
    start_y = np.clip(p1.y(), 0.0, height)
    delta_x = p2.x() - start_x
    delta_y = p2.y() - start_y

    # Liang-Barsky line clipping.
    boundary_pairs = (
        (start_x, -delta_x),
        (width - start_x, delta_x),
        (start_y, -delta_y),
        (height - start_y, delta_y),
    )
    t_exit = 1.0
    for numerator, denominator in boundary_pairs:
        if denominator > 0.0:
            t_exit = min(t_exit, numerator / denominator)

    if t_exit > 0.0:
        return QPointF(start_x + t_exit * delta_x, start_y + t_exit * delta_y)

    # t_exit == 0: start is on a boundary, p2 is exterior — slide along the edge.
    if start_x <= 0.0 or start_x >= width:
        return QPointF(start_x, np.clip(p2.y(), 0.0, height))
    return QPointF(np.clip(p2.x(), 0.0, width), start_y)


def _should_reselect_on_right_press(
    selected_shapes: list[Shape], hovered_shape: Shape | None
) -> bool:
    if not selected_shapes:
        return True
    if hovered_shape is None:
        return False
    return hovered_shape not in selected_shapes


def _pick_pending_moved_shape(
    is_moving_shape: bool, hovered_shape: Shape | None, shapes: list[Shape]
) -> Shape | None:
    if not is_moving_shape:
        return None
    if hovered_shape is None:
        return None
    if hovered_shape not in shapes:
        return None
    return hovered_shape


def _is_shape_paintable(shape: Shape, visible: bool, hide_background: bool) -> bool:
    if not visible:
        return False
    if hide_background and not shape.selected:
        return False
    return True


def _is_shape_filled(shape: Shape, hovered_shape: Shape | None) -> bool:
    return shape.selected or shape is hovered_shape
