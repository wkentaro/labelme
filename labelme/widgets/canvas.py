from __future__ import annotations

import enum
from collections.abc import Iterator
from typing import Any
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
    shapesBackups: list[list[Shape]]
    movingShape: bool
    selectedShapes: list[Shape]
    selectedShapesCopy: list[Shape]
    current: Shape | None
    hShape: Shape | None
    _lasthShape: Shape | None
    hVertex: int | None
    _lasthVertex: int | None
    hEdge: int | None
    _lasthEdge: int | None

    _VALID_CREATE_MODES = {
        "polygon",
        "rectangle",
        "circle",
        "line",
        "point",
        "linestrip",
        "ai_points_to_shape",
        "ai_box_to_shape",
    }

    zoomRequest = QtCore.pyqtSignal(int, QPointF)
    scrollRequest = QtCore.pyqtSignal(int, int)
    newShape = QtCore.pyqtSignal()
    selectionChanged = QtCore.pyqtSignal(list)
    shapeMoved = QtCore.pyqtSignal()
    drawingPolygon = QtCore.pyqtSignal(bool)
    vertexSelected = QtCore.pyqtSignal(bool)
    mouseMoved = QtCore.pyqtSignal(QPointF)
    statusUpdated = QtCore.pyqtSignal(str)

    mode: CanvasMode = CanvasMode.EDIT

    # polygon, rectangle, line, or point
    _createMode = "polygon"

    _fill_drawing = False

    prevPoint: QPointF
    prevMovePoint: QPointF
    offsets: tuple[QPointF, QPointF]

    _dragging_start_pos: QPointF
    _is_dragging: bool
    _is_dragging_enabled: bool

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
        self.num_backups: int = kwargs.pop("num_backups", 10)
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

        self.resetState()

        # self.line represents:
        #   - createMode == 'polygon': edge from last point to current
        #   - createMode == 'rectangle': diagonal line of the rectangle
        #   - createMode == 'line': the line
        #   - createMode == 'point': the point
        self.line = Shape()
        self.prevPoint = QPointF()
        self.prevMovePoint = QPointF()
        self.offsets = QPointF(), QPointF()
        self.scale: float = 1.0
        self._osam_session = None
        self.visible: dict = {}
        self._hideBackground: bool = False
        self.hideBackground: bool = False
        self.snapping = True
        self.hShapeIsSelected: bool = False
        self._painter = QtGui.QPainter()
        self._dragging_start_pos = QPointF()
        self._is_dragging = False
        self._is_dragging_enabled = False
        # Context menus: [0] = no active selection, [1] = with active copy/paste
        self.menus = (QtWidgets.QMenu(), QtWidgets.QMenu())
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.WheelFocus)

    def fillDrawing(self) -> bool:
        return self._fill_drawing

    def setFillDrawing(self, value: bool) -> None:
        self._fill_drawing = value

    @property
    def createMode(self) -> str:
        return self._createMode

    @createMode.setter
    def createMode(self, value: str) -> None:
        if value not in self._VALID_CREATE_MODES:
            raise ValueError(f"Unsupported createMode: {value}")
        self._createMode = value

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

    def storeShapes(self) -> None:
        snapshot = [shape.copy() for shape in self.shapes]
        if len(self.shapesBackups) > self.num_backups:
            self.shapesBackups = self.shapesBackups[-(self.num_backups + 1) :]
        self.shapesBackups.append(snapshot)

    @property
    def isShapeRestorable(self) -> bool:
        # Undo requires both the current state and the prior state to exist
        # in the backup stack, since we record state after each edit.
        return len(self.shapesBackups) >= 2

    def restoreShape(self) -> None:
        # Partial undo -- the caller (app.py::undoShapeEdit) handles the rest,
        # and Canvas::loadShapes will re-push the restored state onto the stack.
        if not self.isShapeRestorable:
            return
        self.shapesBackups.pop()  # discard current state

        # Retrieve the previous state; loadShapes will push it back.
        previous_state = self.shapesBackups.pop()
        self.shapes = previous_state
        self.selectedShapes = []
        for s in self.shapes:
            s.selected = False
        self.update()

    def enterEvent(self, a0: QtCore.QEvent) -> None:
        self.overrideCursor(self._cursor)
        self._update_status()

    def leaveEvent(self, a0: QtCore.QEvent) -> None:
        if self._set_highlight(hShape=None, hEdge=None, hVertex=None):
            self.update()
        self.restoreCursor()
        self._update_status()

    def focusOutEvent(self, a0: QtGui.QFocusEvent) -> None:
        self.restoreCursor()
        self._update_status()

    def isVisible(self, shape: Shape) -> bool:  # type: ignore[override]
        return self.visible.get(shape, True)

    def drawing(self) -> bool:
        return self.mode == CanvasMode.CREATE

    def editing(self) -> bool:
        return self.mode == CanvasMode.EDIT

    def setEditing(self, value: bool = True) -> None:
        self.mode = CanvasMode.EDIT if value else CanvasMode.CREATE
        if self.mode == CanvasMode.EDIT:
            # CREATE -> EDIT
            self.update()  # clear crosshair
        else:
            # EDIT -> CREATE
            need_update: bool = self._set_highlight(
                hShape=None, hEdge=None, hVertex=None
            )
            need_update |= self.deSelectShape()
            if need_update:
                self.update()

    def _set_highlight(
        self, hShape: Shape | None, hEdge: int | None, hVertex: int | None
    ) -> bool:
        need_update: bool = hShape is not None
        if self.hShape:
            self.hShape.highlightClear()
            need_update = True
        # NOTE: Store last highlighted for adding/removing points.
        self._lasthShape = self.hShape if hShape is None else hShape
        self._lasthVertex = self.hVertex if hVertex is None else hVertex
        self._lasthEdge = self.hEdge if hEdge is None else hEdge
        self.hShape = hShape
        self.hVertex = hVertex
        self.hEdge = hEdge
        return need_update

    def selectedVertex(self) -> bool:
        return self.hVertex is not None

    def selectedEdge(self) -> bool:
        return self.hEdge is not None

    def _update_status(self, extra_messages: list[str] | None = None) -> None:
        messages: list[str] = []
        if self.drawing():
            messages.append(self.tr("Creating %r") % self.createMode)
            messages.append(self._get_create_mode_message())
            if self.current:
                messages.append(self.tr("ESC to cancel"))
            if self.canCloseShape():
                messages.append(self.tr("Enter or Space to finalize"))
        else:
            assert self.editing()
            messages.append(self.tr("Editing shapes"))
        if extra_messages:
            messages.extend(extra_messages)
        self.statusUpdated.emit(" • ".join(messages))

    def _get_create_mode_message(self) -> str:
        assert self.drawing()
        isNew: bool = self.current is None
        if self.createMode == "ai_points_to_shape":
            return self.tr(
                "Click points to include or Shift+Click to exclude."
                " Ctrl+LeftClick ends creation."
            )
        if self.createMode == "ai_box_to_shape":
            if isNew:
                return self.tr("Click first corner of bbox for AI segmentation")
            else:
                return self.tr("Click opposite corner to segment object")
        if self.createMode == "line":
            if isNew:
                return self.tr("Click start point for line")
            else:
                return self.tr("Click end point for line")
        if self.createMode == "linestrip":
            if isNew:
                return self.tr("Click start point for linestrip")
            else:
                return self.tr(
                    "Click next point or finish by Ctrl/Cmd+Click for linestrip"
                )
        if self.createMode == "circle":
            if isNew:
                return self.tr("Click center point for circle")
            else:
                return self.tr("Click point on circumference for circle")
        if self.createMode == "rectangle":
            if isNew:
                return self.tr("Click first corner for rectangle")
            else:
                return self.tr("Click opposite corner for rectangle (Shift for square)")
        return self.tr("Click to add point")

    def mouseMoveEvent(self, a0: QtGui.QMouseEvent) -> None:
        """Track cursor position and update rubber-band line or shape movement."""
        try:
            pos = self.transformPos(a0.localPos())
        except AttributeError:
            return

        self.mouseMoved.emit(pos)

        self.prevMovePoint = pos

        is_shift_pressed = a0.modifiers() & Qt.ShiftModifier

        if self._is_dragging:
            self.overrideCursor(CURSOR_GRAB)
            delta: QPointF = pos - self._dragging_start_pos
            self.scrollRequest.emit(int(delta.x()), Qt.Horizontal)
            self.scrollRequest.emit(int(delta.y()), Qt.Vertical)
            return

        # Shape creation mode handling
        if self.drawing():
            if self.createMode == "ai_points_to_shape":
                self.line.shape_type = "points"
            elif self.createMode == "ai_box_to_shape":
                self.line.shape_type = "rectangle"
            else:
                self.line.shape_type = self.createMode

            self.overrideCursor(CURSOR_DRAW)
            if not self.current:
                self.update()  # draw crosshair
                self._update_status()
                return

            if self.outOfPixmap(pos):
                # Don't allow the user to draw outside the pixmap.
                # Project the point to the pixmap's edges.
                pos = _compute_intersection_edges_image(
                    self.current[-1], pos, image_size=self.pixmap.size()
                )
            elif (
                self.snapping
                and len(self.current) > 1
                and self.createMode == "polygon"
                and self.closeEnough(pos, self.current[0])
            ):
                # Snap cursor to the origin vertex to hint at closure
                pos = self.current[0]
                self.overrideCursor(CURSOR_POINT)
                self.current.highlightVertex(0, Shape.NEAR_VERTEX)
            if self.createMode in ["polygon", "linestrip"]:
                self.line.points = [self.current[-1], pos]
                self.line.point_labels = [1, 1]
            elif self.createMode == "ai_points_to_shape":
                self.line.points = [self.current.points[-1], pos]
                self.line.point_labels = [
                    self.current.point_labels[-1],
                    0 if is_shift_pressed else 1,
                ]
            elif self.createMode in ["rectangle", "ai_box_to_shape"]:
                if is_shift_pressed:
                    self.prevMovePoint = pos = _snap_cursor_pos_for_square(  # override
                        pos=pos, opposite_vertex=self.current[0]
                    )
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.close()
            elif self.createMode == "circle":
                self.line.shape_type = "circle"
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
            elif self.createMode == "line":
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.close()
            elif self.createMode == "point":
                self.line.points = [self.current[0]]
                self.line.point_labels = [1]
                self.line.close()
            assert len(self.line.points) == len(self.line.point_labels)
            self.update()
            self.current.highlightClear()
            self._update_status()
            return

        # Right-click drag: copy shapes
        if Qt.RightButton & a0.buttons():
            if self.selectedShapesCopy and self.prevPoint is not None:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapesCopy, pos)
                self.update()
            elif self.selectedShapes:
                self.selectedShapesCopy = [s.copy() for s in self.selectedShapes]
                self.update()
            self._update_status()
            return

        # Left-click drag: move vertex or shape
        if Qt.LeftButton & a0.buttons():
            if self.selectedVertex():
                assert self.hVertex is not None
                assert self.hShape is not None
                self.boundedMoveVertex(
                    self.hShape, self.hVertex, pos, is_shift_pressed=is_shift_pressed
                )
                self.update()
                self.movingShape = True
            elif self.selectedShapes and self.prevPoint is not None:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapes, pos)
                self.update()
                self.movingShape = True
            return

        # Hovering: highlight shapes or vertices under the cursor
        status_messages: list[str] = []
        self._highlight_hover_shape(pos=pos, status_messages=status_messages)
        self.vertexSelected.emit(self.hVertex is not None)
        self._update_status(extra_messages=status_messages)

    def _highlight_hover_shape(self, pos: QPointF, status_messages: list[str]) -> None:
        ordered_shapes: list[Shape] = ([self.hShape] if self.hShape else []) + [
            s for s in reversed(self.shapes) if self.isVisible(s) and s != self.hShape
        ]

        for shape in ordered_shapes:
            index: int | None = shape.nearestVertex(pos, self.epsilon)
            if index is not None:
                self._set_highlight(hShape=shape, hEdge=None, hVertex=index)
                shape.highlightVertex(index, shape.MOVE_VERTEX)
                self.overrideCursor(CURSOR_POINT)
                status_messages.append(self.tr("Click & drag to move point"))
                if shape.canRemovePoint():
                    status_messages.append(
                        self.tr("ALT + SHIFT + Click to delete point")
                    )
                self.update()
                return

        for shape in ordered_shapes:
            index_edge: int | None = shape.nearestEdge(pos, self.epsilon)
            if index_edge is not None and shape.canAddPoint():
                self._set_highlight(hShape=shape, hEdge=index_edge, hVertex=None)
                self.overrideCursor(CURSOR_POINT)
                status_messages.append(self.tr("ALT + Click to create point on shape"))
                self.update()
                return

        for shape in ordered_shapes:
            if shape.containsPoint(pos):
                self._set_highlight(hShape=shape, hEdge=None, hVertex=None)
                status_messages.extend(
                    [
                        self.tr("Click & drag to move shape"),
                        self.tr("Right-click & drag to copy shape"),
                    ]
                )
                self.overrideCursor(CURSOR_GRAB)
                self.update()
                return

        self.restoreCursor()
        if self._set_highlight(hShape=None, hEdge=None, hVertex=None):
            self.update()

    def addPointToEdge(self) -> None:
        shape = self._lasthShape
        index = self._lasthEdge
        point = self.prevMovePoint
        if shape is None or index is None or point is None:
            return
        shape.insertPoint(index, point)
        shape.highlightVertex(index, shape.MOVE_VERTEX)
        self.hShape = shape
        self.hVertex = index
        self.hEdge = None
        self.movingShape = True

    def removeSelectedPoint(self) -> None:
        shape = self._lasthShape
        index = self._lasthVertex
        if shape is None or index is None:
            return
        shape.removePoint(index)
        shape.highlightClear()
        self.hShape = shape
        self._lasthVertex = None
        self.movingShape = True  # Save changes

    def mousePressEvent(self, a0: QtGui.QMouseEvent) -> None:
        pos: QPointF = self.transformPos(a0.localPos())

        is_shift_pressed = a0.modifiers() & Qt.ShiftModifier

        if a0.button() == Qt.LeftButton:
            if self.drawing():
                if self.current:
                    # Add point to existing shape.
                    if self.createMode == "polygon":
                        self.current.addPoint(self.line[1])
                        self.line[0] = self.current[-1]
                        if self.current.isClosed():
                            self.finalise()
                    elif self.createMode in [
                        "rectangle",
                        "circle",
                        "line",
                        "ai_box_to_shape",
                    ]:
                        assert len(self.current.points) == 1
                        self.current.points = self.line.points
                        self.finalise()
                    elif self.createMode == "linestrip":
                        self.current.addPoint(self.line[1])
                        self.line[0] = self.current[-1]
                        if int(a0.modifiers()) == Qt.ControlModifier:
                            self.finalise()
                    elif self.createMode == "ai_points_to_shape":
                        self.current.addPoint(
                            self.line.points[1],
                            label=self.line.point_labels[1],
                        )
                        self.line.points[0] = self.current.points[-1]
                        self.line.point_labels[0] = self.current.point_labels[-1]
                        if a0.modifiers() & Qt.ControlModifier:
                            self.finalise()
                elif not self.outOfPixmap(pos):
                    if self.createMode in [
                        "ai_points_to_shape",
                        "ai_box_to_shape",
                    ]:
                        if not download_ai_model(
                            model_name=self._osam_session_model_name, parent=self
                        ):
                            return

                    # Create new shape.
                    if self.createMode == "ai_points_to_shape":
                        initial_shape_type = "points"
                    elif self.createMode == "ai_box_to_shape":
                        initial_shape_type = "rectangle"
                    else:
                        initial_shape_type = self.createMode
                    self.current = Shape(shape_type=initial_shape_type)
                    self.current.addPoint(pos, label=0 if is_shift_pressed else 1)
                    if self.createMode == "point":
                        self.finalise()
                    elif (
                        self.createMode == "ai_points_to_shape"
                        and a0.modifiers() & Qt.ControlModifier
                    ):
                        self.finalise()
                    else:
                        if self.createMode == "circle":
                            self.current.shape_type = "circle"
                        self.line.points = [pos, pos]  # rubber-band start
                        if self.createMode == "ai_points_to_shape" and is_shift_pressed:
                            self.line.point_labels = [0, 0]
                        else:
                            self.line.point_labels = [1, 1]
                        self.setHiding()
                        self.drawingPolygon.emit(True)
                        self.update()
            elif self.editing():
                is_alt = a0.modifiers() == Qt.AltModifier
                is_alt_shift = a0.modifiers() == (Qt.AltModifier | Qt.ShiftModifier)
                if self.selectedEdge() and is_alt:
                    self.addPointToEdge()
                elif self.selectedVertex() and is_alt_shift:
                    self.removeSelectedPoint()

                multi_select = int(a0.modifiers()) == Qt.ControlModifier
                self.selectShapePoint(pos, multiple_selection_mode=multi_select)
                self.prevPoint = pos
                self.update()
        elif a0.button() == Qt.RightButton and self.editing():
            group_mode = int(a0.modifiers()) == Qt.ControlModifier
            no_selection = not self.selectedShapes
            hover_outside = (
                self.hShape is not None and self.hShape not in self.selectedShapes
            )
            if no_selection or hover_outside:
                self.selectShapePoint(pos, multiple_selection_mode=group_mode)
                self.update()
            self.prevPoint = pos
        elif a0.button() == Qt.MiddleButton and self._is_dragging_enabled:
            self.overrideCursor(CURSOR_GRAB)
            self._dragging_start_pos = pos
            self._is_dragging = True
        self._update_status()

    def mouseReleaseEvent(self, a0: QtGui.QMouseEvent) -> None:
        if a0.button() == Qt.RightButton:
            has_copies = len(self.selectedShapesCopy) > 0
            menu = self.menus[has_copies]
            self.restoreCursor()
            if not menu.exec_(self.mapToGlobal(a0.pos())) and self.selectedShapesCopy:  # type: ignore
                # Discard the dragged shadow copies since the context menu was dismissed
                self.selectedShapesCopy = []
                self.update()
        elif a0.button() == Qt.LeftButton:
            if self.editing():
                if (
                    self.hShape is not None
                    and self.hShapeIsSelected
                    and not self.movingShape
                ):
                    remaining = [s for s in self.selectedShapes if s != self.hShape]
                    self.selectionChanged.emit(remaining)
        elif a0.button() == Qt.MiddleButton:
            self._is_dragging = False
            self.restoreCursor()

        if self.movingShape and self.hShape and self.hShape in self.shapes:
            idx = self.shapes.index(self.hShape)
            if self.shapesBackups[-1][idx].points != self.shapes[idx].points:
                self.storeShapes()
                self.shapeMoved.emit()

            self.movingShape = False
        self._update_status()

    def endMove(self, copy: bool) -> bool:
        assert self.selectedShapes and self.selectedShapesCopy
        assert len(self.selectedShapesCopy) == len(self.selectedShapes)
        if copy:
            for idx, copied_shape in enumerate(self.selectedShapesCopy):
                self.shapes.append(copied_shape)
                self.selectedShapes[idx].selected = False
                self.selectedShapes[idx] = copied_shape
        else:
            for idx, copied_shape in enumerate(self.selectedShapesCopy):
                self.selectedShapes[idx].points = copied_shape.points
        self.selectedShapesCopy = []
        self.update()
        self.storeShapes()
        return True

    def hideBackgroundShapes(self, value: bool) -> None:
        self.hideBackground = value
        if not self.selectedShapes:
            # Without a selection, hiding would prevent picking any shape.
            return
        self.setHiding(True)
        self.update()

    def setHiding(self, enable: bool = True) -> None:
        self._hideBackground = self.hideBackground if enable else False

    def canCloseShape(self) -> bool:
        if not self.drawing():
            return False
        if not self.current:
            return False
        if self.createMode == "ai_points_to_shape":
            return True
        if self.createMode == "linestrip":
            return len(self.current) >= 2
        return len(self.current) >= 3

    def mouseDoubleClickEvent(self, a0: QtGui.QMouseEvent) -> None:
        if self.double_click != "close":
            return

        if self.canCloseShape():
            self.finalise()

    def selectShapes(self, shapes: list[Shape]) -> None:
        self.setHiding()
        self.selectionChanged.emit(shapes)
        self.update()

    def selectShapePoint(self, point: QPointF, multiple_selection_mode: bool) -> None:
        """Find and select the top-most shape under this point."""
        if self.hVertex is not None:
            assert self.hShape is not None
            self.hShape.highlightVertex(i=self.hVertex, action=self.hShape.MOVE_VERTEX)
        else:
            shape: Shape
            for shape in reversed(self.shapes):
                if self.isVisible(shape) and shape.containsPoint(point):
                    self.setHiding()
                    already_selected = shape in self.selectedShapes
                    if not already_selected:
                        if multiple_selection_mode:
                            self.selectionChanged.emit(self.selectedShapes + [shape])
                        else:
                            self.selectionChanged.emit([shape])
                        self.hShapeIsSelected = False
                    else:
                        self.hShapeIsSelected = True
                    self.calculateOffsets(point)
                    return
        if self.deSelectShape():
            self.update()

    def calculateOffsets(self, point: QPointF) -> None:
        rects = [s.boundingRect() for s in self.selectedShapes]
        min_left = min(r.left() for r in rects) if rects else 0.0
        max_right = max(r.right() for r in rects) if rects else 0.0
        min_top = min(r.top() for r in rects) if rects else 0.0
        max_bottom = max(r.bottom() for r in rects) if rects else 0.0

        self.offsets = (
            QPointF(min_left - point.x(), min_top - point.y()),
            QPointF(max_right - point.x(), max_bottom - point.y()),
        )

    def boundedMoveVertex(
        self, shape: Shape, vertex_index: int, pos: QPointF, is_shift_pressed: bool
    ) -> None:
        if vertex_index >= len(shape.points):
            logger.warning(
                "vertex_index is out of range: vertex_index={:d}, len(points)={:d}",
                vertex_index,
                len(shape.points),
            )
            return

        if self.outOfPixmap(pos):
            pos = _compute_intersection_edges_image(
                shape[vertex_index], pos, image_size=self.pixmap.size()
            )

        if is_shift_pressed and shape.shape_type == "rectangle":
            pos = _snap_cursor_pos_for_square(
                pos=pos, opposite_vertex=shape[1 - vertex_index]
            )

        shape.moveVertex(i=vertex_index, pos=pos)

    def boundedMoveShapes(self, shapes: list[Shape], pos: QPointF) -> bool:
        if self.outOfPixmap(pos):
            return False

        img_w = self.pixmap.width()
        img_h = self.pixmap.height()

        # Clamp so the top-left extent of all selected shapes stays in bounds
        top_left = pos + self.offsets[0]
        clamp_x = max(0.0, -top_left.x()) if self.outOfPixmap(top_left) else 0.0
        clamp_y = max(0.0, -top_left.y()) if self.outOfPixmap(top_left) else 0.0
        pos = QPointF(pos.x() + clamp_x, pos.y() + clamp_y)

        # Clamp so the bottom-right extent stays in bounds
        bottom_right = pos + self.offsets[1]
        if self.outOfPixmap(bottom_right):
            excess_x = max(0.0, bottom_right.x() - img_w)
            excess_y = max(0.0, bottom_right.y() - img_h)
            pos = QPointF(pos.x() - excess_x, pos.y() - excess_y)

        delta = pos - self.prevPoint
        if delta.isNull():
            return False

        for shape in shapes:
            shape.moveBy(delta)
        self.prevPoint = pos
        return True

    def deSelectShape(self) -> bool:
        if not self.selectedShapes:
            return False
        self.setHiding(False)
        self.selectionChanged.emit([])
        self.hShapeIsSelected = False
        return True

    def deleteSelected(self) -> list[Shape]:
        if not self.selectedShapes:
            return []
        removed: list[Shape] = []
        for s in self.selectedShapes:
            self.shapes.remove(s)
            removed.append(s)
        self.storeShapes()
        self.selectedShapes = []
        self.update()
        return removed

    def deleteShape(self, shape: Shape) -> None:
        if shape in self.selectedShapes:
            self.selectedShapes.remove(shape)
        if shape in self.shapes:
            self.shapes.remove(shape)
        self.storeShapes()
        self.update()

    def paintEvent(self, a0: QtGui.QPaintEvent) -> None:
        if not self.pixmap:
            return super().paintEvent(a0)

        painter = self._painter
        painter.begin(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.HighQualityAntialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)

        painter.scale(self.scale, self.scale)
        painter.translate(self.offsetToCenter())

        painter.drawPixmap(0, 0, self.pixmap)

        # Undo the scale so crosshair / shape rendering uses pixel coordinates
        inv_scale = 1.0 / self.scale
        painter.scale(inv_scale, inv_scale)

        # draw crosshair
        if (
            self._crosshair[self._createMode]
            and self.drawing()
            and self.prevMovePoint is not None
            and not self.outOfPixmap(self.prevMovePoint)
        ):
            painter.setPen(QtGui.QColor(0, 0, 0))
            scaled_cursor_y = int(self.prevMovePoint.y() * self.scale)
            scaled_cursor_x = int(self.prevMovePoint.x() * self.scale)
            painter.drawLine(
                0,
                scaled_cursor_y,
                int(self.pixmap.width() * self.scale) - 1,
                scaled_cursor_y,
            )
            painter.drawLine(
                scaled_cursor_x,
                0,
                scaled_cursor_x,
                int(self.pixmap.height() * self.scale) - 1,
            )

        Shape.scale = self.scale
        for shape in self.shapes:
            if (shape.selected or not self._hideBackground) and self.isVisible(shape):
                shape.fill = shape.selected or shape == self.hShape
                shape.paint(painter)
        if self.current:
            self.current.paint(painter)
            assert len(self.line.points) == len(self.line.point_labels)
            self.line.paint(painter)
        if self.selectedShapesCopy:
            for copied in self.selectedShapesCopy:
                copied.paint(painter)

        if not self.current or self.createMode not in [
            "polygon",
            "ai_points_to_shape",
        ]:
            painter.end()
            return

        drawing_shape: Shape = self.current.copy()
        if self.createMode == "polygon":
            if self.fillDrawing() and len(self.current.points) >= 2:
                assert drawing_shape.fill_color is not None
                if drawing_shape.fill_color.getRgb()[3] == 0:
                    logger.warning(
                        "fill_drawing=true, but fill_color is transparent,"
                        " so forcing to be opaque."
                    )
                    drawing_shape.fill_color.setAlpha(64)
                drawing_shape.addPoint(self.line[1])
        elif self.createMode == "ai_points_to_shape":
            drawing_shape.addPoint(
                point=self.line.points[1],
                label=self.line.point_labels[1],
            )
            shapes = self._shapes_from_points_ai(
                points=drawing_shape.points,
                point_labels=drawing_shape.point_labels,
            )
            if shapes:
                drawing_shape = shapes[0]
        drawing_shape.fill = self.fillDrawing()
        drawing_shape.selected = self.fillDrawing()
        drawing_shape.paint(painter)
        painter.end()

    def transformPos(self, point: QPointF) -> QPointF:
        """Map widget coordinates to image coordinates (inverse of paint transform)."""
        return point / self.scale - self.offsetToCenter()

    def enableDragging(self, enabled: bool) -> None:
        self._is_dragging_enabled = enabled

    def offsetToCenter(self) -> QPointF:
        zoom = self.scale
        widget_size = super().size()
        scaled_img_w = self.pixmap.width() * zoom
        scaled_img_h = self.pixmap.height() * zoom
        dx = (
            (widget_size.width() - scaled_img_w) / (2 * zoom)
            if widget_size.width() > scaled_img_w
            else 0.0
        )
        dy = (
            (widget_size.height() - scaled_img_h) / (2 * zoom)
            if widget_size.height() > scaled_img_h
            else 0.0
        )
        return QPointF(dx, dy)

    def outOfPixmap(self, p: QPointF) -> bool:
        w, h = self.pixmap.width(), self.pixmap.height()
        return not (0 <= p.x() <= w and 0 <= p.y() <= h)

    def finalise(self) -> None:
        assert self.current
        new_shapes: list[Shape] = []
        if self.createMode == "ai_points_to_shape":
            new_shapes = self._shapes_from_points_ai(
                points=self.current.points,
                point_labels=self.current.point_labels,
            )
        elif self.createMode == "ai_box_to_shape":
            new_shapes = self._shapes_from_bbox_ai(
                bbox_points=self.current.points,
            )
        else:
            self.current.close()
            new_shapes = [self.current]

        if not new_shapes:
            self.current = None
            return

        self.shapes.extend(new_shapes)
        self.storeShapes()
        self.current = None
        self.setHiding(False)
        self.newShape.emit()
        self.update()

    def closeEnough(self, p1: QPointF, p2: QPointF) -> bool:
        # Scale-adjusted threshold so zoomed-in views allow finer snapping
        threshold = self.epsilon / self.scale
        return labelme.utils.distance(p1 - p2) < threshold

    # Required by scroll area along with adjustSize
    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSizeHint()

    def minimumSizeHint(self) -> QtCore.QSize:
        if not self.pixmap:
            return super().minimumSizeHint()

        scaled_size = self.scale * self.pixmap.size()
        if self._is_dragging_enabled:
            # Extra margin so the user can drag past image edges slightly
            scaled_size = 1.167 * scaled_size
        return scaled_size

    def wheelEvent(self, a0: QtGui.QWheelEvent) -> None:
        mods: Qt.KeyboardModifiers = a0.modifiers()
        delta: QPoint = a0.angleDelta()
        if Qt.ControlModifier == int(mods):
            # with Ctrl/Command key
            # zoom
            self.zoomRequest.emit(delta.y(), a0.posF())
        else:
            # scroll
            self.scrollRequest.emit(delta.x(), Qt.Horizontal)
            self.scrollRequest.emit(delta.y(), Qt.Vertical)
        a0.accept()

    def moveByKeyboard(self, offset: QPointF) -> None:
        if not self.selectedShapes:
            return
        target = self.prevPoint + offset
        self.boundedMoveShapes(self.selectedShapes, target)
        self.update()
        self.movingShape = True

    def keyPressEvent(self, a0: QtGui.QKeyEvent) -> None:
        active_modifiers = a0.modifiers()
        pressed_key = a0.key()
        if self.drawing():
            if pressed_key == Qt.Key_Escape and self.current:
                self.current = None
                self.drawingPolygon.emit(False)
                self.update()
            elif (
                pressed_key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Space)
                and self.canCloseShape()
            ):
                self.finalise()
            elif active_modifiers == Qt.AltModifier:
                self.snapping = False
        elif self.editing():
            if pressed_key == Qt.Key_Up:
                self.moveByKeyboard(QPointF(0.0, -MOVE_SPEED))
            elif pressed_key == Qt.Key_Down:
                self.moveByKeyboard(QPointF(0.0, MOVE_SPEED))
            elif pressed_key == Qt.Key_Left:
                self.moveByKeyboard(QPointF(-MOVE_SPEED, 0.0))
            elif pressed_key == Qt.Key_Right:
                self.moveByKeyboard(QPointF(MOVE_SPEED, 0.0))
        self._update_status()

    def keyReleaseEvent(self, a0: QtGui.QKeyEvent) -> None:
        released_modifiers = a0.modifiers()
        if self.drawing():
            if int(released_modifiers) == 0:
                self.snapping = True
        elif self.editing():
            if (
                self.movingShape
                and self.selectedShapes
                and self.selectedShapes[0] in self.shapes
            ):
                first_idx = self.shapes.index(self.selectedShapes[0])
                if (
                    self.shapesBackups[-1][first_idx].points
                    != self.shapes[first_idx].points
                ):
                    self.storeShapes()
                    self.shapeMoved.emit()

                self.movingShape = False

    def setLastLabel(self, text: str, flags: dict[str, bool]) -> list[Shape]:
        assert text
        shapes = []
        for shape in reversed(self.shapes):
            if shape.label is not None:
                break
            shapes.append(shape)
        shapes.reverse()
        for shape in shapes:
            shape.label = text
            shape.flags = flags
        self.shapesBackups.pop()
        self.storeShapes()
        return shapes

    def undoLastLine(self) -> None:
        assert self.shapes
        if self.createMode in ["ai_points_to_shape", "ai_box_to_shape"]:
            # Remove all unlabeled shapes at the tail (added by AI in one shot)
            while self.shapes and self.shapes[-1].label is None:
                self.shapes.pop()
            self.current = None
            self.drawingPolygon.emit(False)
            self.update()
            return
        self.current = self.shapes.pop()
        self.current.setOpen()
        self.current.restoreShapeRaw()
        if self.createMode in ["polygon", "linestrip"]:
            self.line.points = [
                self.current[-1],
                self.current[0],
            ]  # restore rubber-band
        elif self.createMode in [
            "rectangle",
            "line",
            "circle",
            "ai_box_to_shape",
        ]:
            self.current.points = self.current.points[0:1]
        elif self.createMode == "point":
            self.current = None
        self.drawingPolygon.emit(True)

    def undoLastPoint(self) -> None:
        if not self.current or self.current.isClosed():
            return
        self.current.popPoint()
        if self.current:
            self.line[0] = self.current[-1]
        else:
            self.current = None
            self.drawingPolygon.emit(False)
        self.update()

    def loadPixmap(self, pixmap: QtGui.QPixmap, clear_shapes: bool = True) -> None:
        self.pixmap = pixmap
        self._pixmap_hash = hash(
            labelme.utils.img_qt_to_arr(img_qt=self.pixmap.toImage()).tobytes()
        )
        if clear_shapes:
            self.shapes = []
        self.update()  # trigger repaint with new image

    def loadShapes(self, shapes: list[Shape], replace: bool = True) -> None:
        if replace:
            self.shapes = list(shapes)
        else:
            self.shapes.extend(shapes)
        self.storeShapes()
        self.current = None
        self.hShape = None
        self.hVertex = None
        self.hEdge = None
        self.update()  # refresh with newly loaded shapes

    def setShapeVisible(self, shape: Shape, value: bool) -> None:
        self.visible[shape] = value
        self.update()  # repaint to reflect visibility change

    def overrideCursor(self, cursor: QtCore.Qt.CursorShape) -> None:
        if cursor == self._cursor:
            return
        self.restoreCursor()
        self._cursor = cursor
        QtWidgets.QApplication.setOverrideCursor(cursor)

    def restoreCursor(self) -> None:
        self._cursor = CURSOR_DEFAULT
        QtWidgets.QApplication.restoreOverrideCursor()

    def resetState(self) -> None:
        self.restoreCursor()
        self.pixmap = QtGui.QPixmap()
        self._pixmap_hash = None
        self.shapes = []
        self.shapesBackups = []
        self.movingShape = False
        self.selectedShapes = []
        self.selectedShapesCopy = []
        self.current = None
        self.hShape = None
        self._lasthShape = None
        self.hVertex = None
        self._lasthVertex = None
        self.hEdge = None
        self._lasthEdge = None
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
        shape.setShapeRefined(
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
        shape.setShapeRefined(
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
    # Cycle through each image edge in clockwise fashion,
    # and find the one intersecting the current line segment.
    # http://paulbourke.net/geometry/lineline2d/
    points = [
        (0, 0),
        (image_size.width(), 0),
        (image_size.width(), image_size.height()),
        (0, image_size.height()),
    ]
    # x1, y1 should be in the pixmap, x2, y2 should be out of the pixmap
    x1 = min(max(p1.x(), 0), image_size.width())
    y1 = min(max(p1.y(), 0), image_size.height())
    x2, y2 = p2.x(), p2.y()
    d, i, (x, y) = min(_compute_intersection_edges((x1, y1), (x2, y2), points))
    x3, y3 = points[i]
    x4, y4 = points[(i + 1) % 4]
    if (x, y) == (x1, y1):
        # Handle cases where previous point is on one of the edges.
        if x3 == x4:
            return QPointF(x3, min(max(0, y2), max(y3, y4)))
        else:  # y3 == y4
            return QPointF(min(max(0, x2), max(x3, x4)), y3)
    return QPointF(x, y)


def _compute_intersection_edges(
    point1: tuple[float, float],
    point2: tuple[float, float],
    points: list[tuple[int, int]],
) -> Iterator[tuple[float, int, tuple[float, float]]]:
    """Find intersecting edges.

    For each edge formed by `points', yield the intersection
    with the line segment `(x1,y1) - (x2,y2)`, if it exists.
    Also return the distance of `(x2,y2)' to the middle of the
    edge along with its index, so that the one closest can be chosen.
    """
    (x1, y1) = point1
    (x2, y2) = point2
    for i in range(4):
        x3, y3 = points[i]
        x4, y4 = points[(i + 1) % 4]
        denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
        nua = (x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)
        nub = (x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)
        if denom == 0:
            # This covers two cases:
            #   nua == nub == 0: Coincident
            #   otherwise: Parallel
            continue
        ua, ub = nua / denom, nub / denom
        if 0 <= ua <= 1 and 0 <= ub <= 1:
            x = x1 + ua * (x2 - x1)
            y = y1 + ua * (y2 - y1)
            m = QPointF((x3 + x4) / 2, (y3 + y4) / 2)
            d = labelme.utils.distance(m - QPointF(x2, y2))
            yield d, i, (x, y)
