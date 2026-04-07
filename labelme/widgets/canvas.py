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

    _createMode: str = "polygon"

    _fill_drawing = False

    prevPoint: QPointF
    prevMovePoint: QPointF
    offsets: tuple[QPointF, QPointF]

    _drag_origin: QPointF
    _drag_active: bool
    _drag_permitted: bool

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
        self._hideBackround: bool = False
        self.hideBackround: bool = False
        self.snapping = True
        self.hShapeIsSelected: bool = False
        self._painter = QtGui.QPainter()
        self._drag_origin = QPointF()
        self._drag_active = False
        self._drag_permitted = False
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
        if value not in _VALID_CREATE_MODES:
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
        return len(self.shapesBackups) >= 2

    def restoreShape(self) -> None:
        if not self.isShapeRestorable:
            return
        self.shapesBackups.pop()
        restored = self.shapesBackups.pop()
        self.shapes = restored
        self.selectedShapes = []
        for shape in self.shapes:
            shape.selected = False
        self.update()

    def enterEvent(self, a0: QtCore.QEvent) -> None:
        self.overrideCursor(self._cursor)
        self._update_status()

    def leaveEvent(self, a0: QtCore.QEvent) -> None:
        changed = self._set_highlight(hShape=None, hEdge=None, hVertex=None)
        if changed:
            self.update()
        self.restoreCursor()
        self._update_status()

    def focusOutEvent(self, a0: QtGui.QFocusEvent) -> None:
        self.restoreCursor()
        self._update_status()

    def isVisible(self, shape: Shape) -> bool:  # type: ignore[override]
        return self.visible.get(shape, True)

    def drawing(self) -> bool:
        return self.mode is CanvasMode.CREATE

    def editing(self) -> bool:
        return self.mode is CanvasMode.EDIT

    def setEditing(self, value: bool = True) -> None:
        self.mode = CanvasMode.EDIT if value else CanvasMode.CREATE
        if self.mode is CanvasMode.EDIT:
            self.update()
        else:
            should_repaint = self._set_highlight(
                hShape=None, hEdge=None, hVertex=None
            )
            should_repaint = self.deSelectShape() or should_repaint
            if should_repaint:
                self.update()

    def _set_highlight(
        self, hShape: Shape | None, hEdge: int | None, hVertex: int | None
    ) -> bool:
        changed = hShape is not None
        if self.hShape:
            self.hShape.highlightClear()
            changed = True
        self._lasthShape = hShape if hShape is not None else self.hShape
        self._lasthVertex = hVertex if hVertex is not None else self.hVertex
        self._lasthEdge = hEdge if hEdge is not None else self.hEdge
        self.hShape = hShape
        self.hVertex = hVertex
        self.hEdge = hEdge
        return changed

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
        try:
            pos = self.transformPos(a0.localPos())
        except AttributeError:
            return

        self.mouseMoved.emit(pos)

        self.prevMovePoint = pos

        is_shift_pressed = bool(a0.modifiers() & Qt.ShiftModifier)

        if self._drag_active:
            self.overrideCursor(CURSOR_GRAB)
            drag_delta = pos - self._drag_origin
            self.scrollRequest.emit(int(drag_delta.x()), Qt.Horizontal)
            self.scrollRequest.emit(int(drag_delta.y()), Qt.Vertical)
            return

        if self.drawing():
            if self.createMode == "ai_points_to_shape":
                self.line.shape_type = "points"
            elif self.createMode == "ai_box_to_shape":
                self.line.shape_type = "rectangle"
            else:
                self.line.shape_type = self.createMode

            self.overrideCursor(CURSOR_DRAW)
            if not self.current:
                self.update()
                self._update_status()
                return

            if self.outOfPixmap(pos):
                pos = self.intersectionPoint(self.current[-1], pos)
            elif (
                self.snapping
                and len(self.current) > 1
                and self.createMode == "polygon"
                and self.closeEnough(pos, self.current[0])
            ):
                pos = self.current[0]
                self.overrideCursor(CURSOR_POINT)
                self.current.highlightVertex(0, Shape.NEAR_VERTEX)
            if self.createMode in ("polygon", "linestrip"):
                self.line.points = [self.current[-1], pos]
                self.line.point_labels = [1, 1]
            elif self.createMode == "ai_points_to_shape":
                self.line.points = [self.current.points[-1], pos]
                self.line.point_labels = [
                    self.current.point_labels[-1],
                    0 if is_shift_pressed else 1,
                ]
            elif self.createMode in ("rectangle", "ai_box_to_shape"):
                if is_shift_pressed:
                    pos = _snap_cursor_pos_for_square(
                        pos=pos, opposite_vertex=self.current[0]
                    )
                    self.prevMovePoint = pos
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.close()
            elif self.createMode == "circle":
                self.line.points = [self.current[0], pos]
                self.line.point_labels = [1, 1]
                self.line.shape_type = "circle"
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

        if a0.buttons() & Qt.RightButton:
            if self.selectedShapesCopy and self.prevPoint is not None:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapesCopy, pos)
                self.update()
            elif self.selectedShapes:
                self.selectedShapesCopy = [s.copy() for s in self.selectedShapes]
                self.update()
            self._update_status()
            return

        if a0.buttons() & Qt.LeftButton:
            if self.selectedVertex():
                self.boundedMoveVertex(pos, is_shift_pressed=is_shift_pressed)
                self.update()
                self.movingShape = True
            elif self.selectedShapes and self.prevPoint is not None:
                self.overrideCursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapes, pos)
                self.update()
                self.movingShape = True
            return

        hover_messages: list[str] = []
        self._highlight_hover_shape(pos=pos, status_messages=hover_messages)
        self.vertexSelected.emit(self.hVertex is not None)
        self._update_status(extra_messages=hover_messages)

    def _highlight_hover_shape(self, pos: QPointF, status_messages: list[str]) -> None:
        priority_shapes: list[Shape] = (
            [self.hShape] if self.hShape else []
        ) + [
            s for s in reversed(self.shapes) if self.isVisible(s) and s != self.hShape
        ]

        for shape in priority_shapes:
            vertex_idx = shape.nearestVertex(pos, self.epsilon)
            if vertex_idx is not None:
                self._set_highlight(hShape=shape, hEdge=None, hVertex=vertex_idx)
                shape.highlightVertex(vertex_idx, shape.MOVE_VERTEX)
                self.overrideCursor(CURSOR_POINT)
                status_messages.append(self.tr("Click & drag to move point"))
                if shape.canRemovePoint():
                    status_messages.append(
                        self.tr("ALT + SHIFT + Click to delete point")
                    )
                self.update()
                return

        for shape in priority_shapes:
            edge_idx = shape.nearestEdge(pos, self.epsilon)
            if edge_idx is not None and shape.canAddPoint():
                self._set_highlight(hShape=shape, hEdge=edge_idx, hVertex=None)
                self.overrideCursor(CURSOR_POINT)
                status_messages.append(self.tr("ALT + Click to create point on shape"))
                self.update()
                return

        for shape in priority_shapes:
            if shape.containsPoint(pos):
                self._set_highlight(hShape=shape, hEdge=None, hVertex=None)
                status_messages.append(self.tr("Click & drag to move shape"))
                status_messages.append(self.tr("Right-click & drag to copy shape"))
                self.overrideCursor(CURSOR_GRAB)
                self.update()
                return

        self.restoreCursor()
        if self._set_highlight(hShape=None, hEdge=None, hVertex=None):
            self.update()

    def addPointToEdge(self) -> None:
        target_shape = self._lasthShape
        target_edge = self._lasthEdge
        insertion_point = self.prevMovePoint
        if target_shape is None or target_edge is None or insertion_point is None:
            return
        target_shape.insertPoint(target_edge, insertion_point)
        target_shape.highlightVertex(target_edge, target_shape.MOVE_VERTEX)
        self.hShape = target_shape
        self.hVertex = target_edge
        self.hEdge = None
        self.movingShape = True

    def removeSelectedPoint(self) -> None:
        target_shape = self._lasthShape
        target_vertex = self._lasthVertex
        if target_shape is None or target_vertex is None:
            return
        target_shape.removePoint(target_vertex)
        target_shape.highlightClear()
        self.hShape = target_shape
        self._lasthVertex = None
        self.movingShape = True

    def mousePressEvent(self, a0: QtGui.QMouseEvent) -> None:
        pos: QPointF = self.transformPos(a0.localPos())

        is_shift_pressed = bool(a0.modifiers() & Qt.ShiftModifier)

        if a0.button() == Qt.LeftButton:
            if self.drawing():
                if self.current:
                    if self.createMode == "polygon":
                        self.current.addPoint(self.line[1])
                        self.line[0] = self.current[-1]
                        if self.current.isClosed():
                            self.finalise()
                    elif self.createMode in (
                        "rectangle",
                        "circle",
                        "line",
                        "ai_box_to_shape",
                    ):
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
                    if self.createMode in (
                        "ai_points_to_shape",
                        "ai_box_to_shape",
                    ):
                        if not download_ai_model(
                            model_name=self._osam_session_model_name, parent=self
                        ):
                            return

                    if self.createMode == "ai_points_to_shape":
                        shape_type_init = "points"
                    elif self.createMode == "ai_box_to_shape":
                        shape_type_init = "rectangle"
                    else:
                        shape_type_init = self.createMode
                    self.current = Shape(shape_type=shape_type_init)
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
                        self.line.points = [pos, pos]
                        if self.createMode == "ai_points_to_shape" and is_shift_pressed:
                            self.line.point_labels = [0, 0]
                        else:
                            self.line.point_labels = [1, 1]
                        self.setHiding()
                        self.drawingPolygon.emit(True)
                        self.update()
            elif self.editing():
                if self.selectedEdge() and a0.modifiers() == Qt.AltModifier:
                    self.addPointToEdge()
                elif self.selectedVertex() and a0.modifiers() == (
                    Qt.AltModifier | Qt.ShiftModifier
                ):
                    self.removeSelectedPoint()

                is_ctrl = int(a0.modifiers()) == Qt.ControlModifier
                self.selectShapePoint(pos, multiple_selection_mode=is_ctrl)
                self.prevPoint = pos
                self.update()
        elif a0.button() == Qt.RightButton and self.editing():
            is_ctrl = int(a0.modifiers()) == Qt.ControlModifier
            if not self.selectedShapes or (
                self.hShape is not None
                and self.hShape not in self.selectedShapes
            ):
                self.selectShapePoint(pos, multiple_selection_mode=is_ctrl)
                self.update()
            self.prevPoint = pos
        elif a0.button() == Qt.MiddleButton and self._drag_permitted:
            self.overrideCursor(CURSOR_GRAB)
            self._drag_origin = pos
            self._drag_active = True
        self._update_status()

    def mouseReleaseEvent(self, a0: QtGui.QMouseEvent) -> None:
        if a0.button() == Qt.RightButton:
            active_menu = self.menus[len(self.selectedShapesCopy) > 0]
            self.restoreCursor()
            menu_result = active_menu.exec_(self.mapToGlobal(a0.pos()))  # type: ignore
            if not menu_result and self.selectedShapesCopy:
                self.selectedShapesCopy = []
                self.update()
        elif a0.button() == Qt.LeftButton:
            if self.editing():
                if (
                    self.hShape is not None
                    and self.hShapeIsSelected
                    and not self.movingShape
                ):
                    remaining = [
                        s for s in self.selectedShapes if s != self.hShape
                    ]
                    self.selectionChanged.emit(remaining)
        elif a0.button() == Qt.MiddleButton:
            self._drag_active = False
            self.restoreCursor()

        if self.movingShape and self.hShape and self.hShape in self.shapes:
            shape_idx = self.shapes.index(self.hShape)
            prev_pts = self.shapesBackups[-1][shape_idx].points
            if prev_pts != self.shapes[shape_idx].points:
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

    def hideBackroundShapes(self, value: bool) -> None:
        self.hideBackround = value
        if self.selectedShapes:
            self.setHiding(True)
            self.update()

    def setHiding(self, enable: bool = True) -> None:
        self._hideBackround = self.hideBackround if enable else False

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
        if self.hVertex is not None:
            assert self.hShape is not None
            self.hShape.highlightVertex(i=self.hVertex, action=self.hShape.MOVE_VERTEX)
        else:
            for candidate in reversed(self.shapes):
                if not self.isVisible(candidate):
                    continue
                if not candidate.containsPoint(point):
                    continue
                self.setHiding()
                if candidate not in self.selectedShapes:
                    if multiple_selection_mode:
                        self.selectionChanged.emit(
                            self.selectedShapes + [candidate]
                        )
                    else:
                        self.selectionChanged.emit([candidate])
                    self.hShapeIsSelected = False
                else:
                    self.hShapeIsSelected = True
                self.calculateOffsets(point)
                return
        if self.deSelectShape():
            self.update()

    def calculateOffsets(self, point: QPointF) -> None:
        min_left = self.pixmap.width() - 1
        max_right = 0
        min_top = self.pixmap.height() - 1
        max_bottom = 0
        for s in self.selectedShapes:
            bounding = s.boundingRect()
            if bounding.left() < min_left:
                min_left = bounding.left()
            if bounding.right() > max_right:
                max_right = bounding.right()
            if bounding.top() < min_top:
                min_top = bounding.top()
            if bounding.bottom() > max_bottom:
                max_bottom = bounding.bottom()

        off_x1 = min_left - point.x()
        off_y1 = min_top - point.y()
        off_x2 = max_right - point.x()
        off_y2 = max_bottom - point.y()
        self.offsets = QPointF(off_x1, off_y1), QPointF(off_x2, off_y2)

    def boundedMoveVertex(self, pos: QPointF, is_shift_pressed: bool) -> None:
        if self.hVertex is None:
            logger.warning("hVertex is None, so cannot move vertex: pos={!r}", pos)
            return
        assert self.hShape is not None

        if self.hVertex >= len(self.hShape.points):
            logger.warning(
                "hVertex is out of range: hVertex={:d}, len(points)={:d}",
                self.hVertex,
                len(self.hShape.points),
            )
            return

        clamped_pos = pos
        if self.outOfPixmap(clamped_pos):
            clamped_pos = self.intersectionPoint(
                self.hShape[self.hVertex], clamped_pos
            )

        if is_shift_pressed and self.hShape.shape_type == "rectangle":
            opposite = self.hShape[1 - self.hVertex]
            clamped_pos = _snap_cursor_pos_for_square(
                pos=clamped_pos, opposite_vertex=opposite
            )

        self.hShape.moveVertex(i=self.hVertex, pos=clamped_pos)

    def boundedMoveShapes(self, shapes: list[Shape], pos: QPointF) -> bool:
        if self.outOfPixmap(pos):
            return False
        corner1 = pos + self.offsets[0]
        if self.outOfPixmap(corner1):
            pos -= QPointF(min(0, corner1.x()), min(0, corner1.y()))
        corner2 = pos + self.offsets[1]
        if self.outOfPixmap(corner2):
            pos += QPointF(
                min(0, self.pixmap.width() - corner2.x()),
                min(0, self.pixmap.height() - corner2.y()),
            )
        displacement = pos - self.prevPoint
        if not displacement.isNull():
            for shape in shapes:
                shape.moveBy(displacement)
            self.prevPoint = pos
            return True
        return False

    def deSelectShape(self) -> bool:
        if not self.selectedShapes:
            return False
        self.setHiding(False)
        self.selectionChanged.emit([])
        self.hShapeIsSelected = False
        return True

    def deleteSelected(self) -> list[Shape]:
        removed: list[Shape] = []
        if self.selectedShapes:
            for shape in self.selectedShapes:
                self.shapes.remove(shape)
                removed.append(shape)
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

        painter.scale(1.0 / self.scale, 1.0 / self.scale)

        _should_draw_crosshair = (
            self._crosshair[self._createMode]
            and self.drawing()
            and self.prevMovePoint is not None
            and not self.outOfPixmap(self.prevMovePoint)
        )
        if _should_draw_crosshair:
            scaled_x = int(self.prevMovePoint.x() * self.scale)
            scaled_y = int(self.prevMovePoint.y() * self.scale)
            canvas_w = int(self.pixmap.width() * self.scale) - 1
            canvas_h = int(self.pixmap.height() * self.scale) - 1
            painter.setPen(QtGui.QColor(0, 0, 0))
            painter.drawLine(0, scaled_y, canvas_w, scaled_y)
            painter.drawLine(scaled_x, 0, scaled_x, canvas_h)

        Shape.scale = self.scale
        for shape in self.shapes:
            if (shape.selected or not self._hideBackround) and self.isVisible(shape):
                shape.fill = shape.selected or shape == self.hShape
                shape.paint(painter)
        if self.current:
            self.current.paint(painter)
            assert len(self.line.points) == len(self.line.point_labels)
            self.line.paint(painter)
        if self.selectedShapesCopy:
            for copied in self.selectedShapesCopy:
                copied.paint(painter)

        if not self.current or self.createMode not in (
            "polygon",
            "ai_points_to_shape",
        ):
            painter.end()
            return

        preview_shape: Shape = self.current.copy()
        if self.createMode == "polygon":
            if self.fillDrawing() and len(self.current.points) >= 2:
                assert preview_shape.fill_color is not None
                if preview_shape.fill_color.getRgb()[3] == 0:
                    logger.warning(
                        "fill_drawing=true, but fill_color is transparent,"
                        " so forcing to be opaque."
                    )
                    preview_shape.fill_color.setAlpha(64)
                preview_shape.addPoint(self.line[1])
        elif self.createMode == "ai_points_to_shape":
            preview_shape.addPoint(
                point=self.line.points[1],
                label=self.line.point_labels[1],
            )
            ai_shapes = self._shapes_from_points_ai(
                points=preview_shape.points,
                point_labels=preview_shape.point_labels,
            )
            if ai_shapes:
                preview_shape = ai_shapes[0]
        preview_shape.fill = self.fillDrawing()
        preview_shape.selected = self.fillDrawing()
        preview_shape.paint(painter)
        painter.end()

    def transformPos(self, point: QPointF) -> QPointF:
        return point / self.scale - self.offsetToCenter()

    def enableDragging(self, enabled: bool) -> None:
        self._drag_permitted = enabled

    def offsetToCenter(self) -> QPointF:
        sc = self.scale
        widget_area = super().size()
        scaled_w = self.pixmap.width() * sc
        scaled_h = self.pixmap.height() * sc
        area_w = widget_area.width()
        area_h = widget_area.height()
        cx = (area_w - scaled_w) / (2 * sc) if area_w > scaled_w else 0
        cy = (area_h - scaled_h) / (2 * sc) if area_h > scaled_h else 0
        return QPointF(cx, cy)

    def outOfPixmap(self, p: QPointF) -> bool:
        pw, ph = self.pixmap.width(), self.pixmap.height()
        return not (0 <= p.x() <= pw and 0 <= p.y() <= ph)

    def finalise(self) -> None:
        assert self.current
        created_shapes: list[Shape] = []
        if self.createMode == "ai_points_to_shape":
            created_shapes = self._shapes_from_points_ai(
                points=self.current.points,
                point_labels=self.current.point_labels,
            )
        elif self.createMode == "ai_box_to_shape":
            created_shapes = self._shapes_from_bbox_ai(
                bbox_points=self.current.points,
            )
        else:
            self.current.close()
            created_shapes = [self.current]

        if not created_shapes:
            self.current = None
            return

        self.shapes.extend(created_shapes)
        self.storeShapes()
        self.current = None
        self.setHiding(False)
        self.newShape.emit()
        self.update()

    def closeEnough(self, p1: QPointF, p2: QPointF) -> bool:
        return labelme.utils.distance(p1 - p2) < (self.epsilon / self.scale)

    def intersectionPoint(self, p1: QPointF, p2: QPointF) -> QPointF:
        pixmap_size = self.pixmap.size()
        corners = [
            (0, 0),
            (pixmap_size.width(), 0),
            (pixmap_size.width(), pixmap_size.height()),
            (0, pixmap_size.height()),
        ]
        ax = min(max(p1.x(), 0), pixmap_size.width())
        ay = min(max(p1.y(), 0), pixmap_size.height())
        bx, by = p2.x(), p2.y()
        dist, edge_i, (ix, iy) = min(
            self.intersectingEdges((ax, ay), (bx, by), corners)
        )
        ex1, ey1 = corners[edge_i]
        ex2, ey2 = corners[(edge_i + 1) % 4]
        if (ix, iy) == (ax, ay):
            if ex1 == ex2:
                return QPointF(ex1, min(max(0, by), max(ey1, ey2)))
            return QPointF(min(max(0, bx), max(ex1, ex2)), ey1)
        return QPointF(ix, iy)

    def intersectingEdges(
        self,
        point1: tuple[float, float],
        point2: tuple[float, float],
        points: list[tuple[int, int]],
    ) -> Iterator[tuple[float, int, tuple[float, float]]]:
        """Find intersecting edges.

        For each edge formed by `points', yield the intersection
        with the line segment `point1 - point2`, if it exists.
        Also return the distance of `point2' to the middle of the
        edge along with its index, so that the one closest can be chosen.
        """
        ax, ay = point1
        bx, by = point2
        for idx in range(4):
            cx, cy = points[idx]
            dx, dy = points[(idx + 1) % 4]
            denominator = (dy - cy) * (bx - ax) - (dx - cx) * (by - ay)
            num_a = (dx - cx) * (ay - cy) - (dy - cy) * (ax - cx)
            num_b = (bx - ax) * (ay - cy) - (by - ay) * (ax - cx)
            if denominator == 0:
                continue
            t_a = num_a / denominator
            t_b = num_b / denominator
            if 0 <= t_a <= 1 and 0 <= t_b <= 1:
                px = ax + t_a * (bx - ax)
                py = ay + t_a * (by - ay)
                midpoint = QPointF((cx + dx) / 2, (cy + dy) / 2)
                dist = labelme.utils.distance(midpoint - QPointF(bx, by))
                yield dist, idx, (px, py)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSizeHint()

    def minimumSizeHint(self) -> QtCore.QSize:
        if not self.pixmap:
            return super().minimumSizeHint()

        base_size = self.scale * self.pixmap.size()
        if self._drag_permitted:
            _DRAG_BUFFER_FACTOR = 1.167
            base_size = _DRAG_BUFFER_FACTOR * base_size
        return base_size

    def wheelEvent(self, a0: QtGui.QWheelEvent) -> None:
        active_mods = a0.modifiers()
        angle_delta = a0.angleDelta()
        if int(active_mods) == Qt.ControlModifier:
            self.zoomRequest.emit(angle_delta.y(), a0.posF())
        else:
            self.scrollRequest.emit(angle_delta.x(), Qt.Horizontal)
            self.scrollRequest.emit(angle_delta.y(), Qt.Vertical)
        a0.accept()

    def moveByKeyboard(self, offset: QPointF) -> None:
        if not self.selectedShapes:
            return
        self.boundedMoveShapes(self.selectedShapes, self.prevPoint + offset)
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
                pressed_key in (Qt.Key_Return, Qt.Key_Space)
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
        unlabeled: list[Shape] = []
        for shape in reversed(self.shapes):
            if shape.label is not None:
                break
            unlabeled.append(shape)
        unlabeled.reverse()
        for shape in unlabeled:
            shape.label = text
            shape.flags = flags
        self.shapesBackups.pop()
        self.storeShapes()
        return unlabeled

    def undoLastLine(self) -> None:
        assert self.shapes
        if self.createMode in ("ai_points_to_shape", "ai_box_to_shape"):
            while self.shapes and self.shapes[-1].label is None:
                self.shapes.pop()
            self.current = None
            self.drawingPolygon.emit(False)
            self.update()
            return
        self.current = self.shapes.pop()
        self.current.setOpen()
        self.current.restoreShapeRaw()
        if self.createMode in ("polygon", "linestrip"):
            self.line.points = [self.current[-1], self.current[0]]
        elif self.createMode in ("rectangle", "line", "circle", "ai_box_to_shape"):
            self.current.points = self.current.points[:1]
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
        image_bytes = labelme.utils.img_qt_to_arr(
            img_qt=self.pixmap.toImage()
        ).tobytes()
        self._pixmap_hash = hash(image_bytes)
        if clear_shapes:
            self.shapes = []
        self.update()

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
        self.update()

    def setShapeVisible(self, shape: Shape, value: bool) -> None:
        self.visible[shape] = value
        self.update()

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
