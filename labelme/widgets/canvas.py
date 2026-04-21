from __future__ import annotations

import collections
import enum
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
    shapesBackups: collections.deque[list[Shape]]
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
        # Menus:
        # 0: right-click without selection and dragging of shapes
        # 1: right-click with selection and dragging of shapes
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
        self.shapesBackups.append([s.copy() for s in self.shapes])

    @property
    def isShapeRestorable(self) -> bool:
        # We save the state AFTER each edit (not before) so for an
        # edit to be undoable, we expect the CURRENT and the PREVIOUS state
        # to be in the undo stack.
        if len(self.shapesBackups) < 2:
            return False
        return True

    def restoreShape(self) -> None:
        # This does _part_ of the job of restoring shapes.
        # The complete process is also done in app.py::undoShapeEdit
        # and app.py::loadShapes and our own Canvas::loadShapes function.
        if not self.isShapeRestorable:
            return
        self.shapesBackups.pop()  # latest

        # The application will eventually call Canvas.loadShapes which will
        # push this right back onto the stack.
        shapesBackup = self.shapesBackups.pop()
        self.shapes = shapesBackup
        self.selectedShapes = []
        for shape in self.shapes:
            shape.selected = False
        self.update()

    def enterEvent(self, a0: QtCore.QEvent) -> None:
        self._apply_cursor(self._cursor)
        self._update_status()

    def leaveEvent(self, a0: QtCore.QEvent) -> None:
        if self._set_highlight(hShape=None, hEdge=None, hVertex=None):
            self.update()
        self._release_cursor()
        self._update_status()

    def focusOutEvent(self, a0: QtGui.QFocusEvent) -> None:
        self._release_cursor()
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
        previous_shape: Shape | None = self.hShape
        need_update: bool = hShape is not None
        if previous_shape is not None:
            previous_shape.highlightClear()
            need_update = True
        # NOTE: Store last highlighted for adding/removing points.
        self._lasthShape = previous_shape if hShape is None else hShape
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
        """Update line with last point and current coordinates."""
        try:
            pos = self._transform_point_widget_to_image(a0.localPos())
        except AttributeError:
            return

        self.mouseMoved.emit(pos)

        self.prevMovePoint = pos

        is_shift_pressed = a0.modifiers() & Qt.ShiftModifier

        if self._is_dragging:
            self._apply_cursor(CURSOR_GRAB)
            delta: QPointF = pos - self._dragging_start_pos
            self.scrollRequest.emit(int(delta.x()), Qt.Horizontal)
            self.scrollRequest.emit(int(delta.y()), Qt.Vertical)
            return

        # Polygon drawing.
        if self.drawing():
            if self.createMode == "ai_points_to_shape":
                self.line.shape_type = "points"
            elif self.createMode == "ai_box_to_shape":
                self.line.shape_type = "rectangle"
            else:
                self.line.shape_type = self.createMode

            self._apply_cursor(CURSOR_DRAW)
            if not self.current:
                self.update()  # draw crosshair
                self._update_status()
                return

            self.current.highlightClear()
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
                # Attract line to starting point and
                # colorise to alert the user.
                pos = self.current[0]
                self._apply_cursor(CURSOR_POINT)
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
            self._update_status()
            return

        # Polygon copy moving.
        if Qt.RightButton & a0.buttons():
            if self.selectedShapesCopy and self.prevPoint is not None:
                self._apply_cursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapesCopy, pos)
                self.update()
            elif self.selectedShapes:
                self.selectedShapesCopy = [s.copy() for s in self.selectedShapes]
                self.update()
            self._update_status()
            return

        # Polygon/Vertex moving.
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
                self._apply_cursor(CURSOR_MOVE)
                self.boundedMoveShapes(self.selectedShapes, pos)
                self.update()
                self.movingShape = True
            return

        # Just hovering over the canvas, 2 possibilities:
        # - Highlight shapes
        # - Highlight vertex
        # Update shape/vertex fill and tooltip value accordingly.
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
                self._apply_cursor(CURSOR_POINT)
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
                self._apply_cursor(CURSOR_POINT)
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
                self._apply_cursor(CURSOR_GRAB)
                self.update()
                return

        self._release_cursor()
        if self._set_highlight(hShape=None, hEdge=None, hVertex=None):
            self.update()

    def addPointToEdge(self) -> None:
        shape = self._lasthShape
        index = self._lasthEdge
        point = self.prevMovePoint
        if shape is None or index is None or point is None:
            return
        shape.insertPoint(index, point)
        shape.highlightVertex(i=index, action=shape.MOVE_VERTEX)
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
        pos: QPointF = self._transform_point_widget_to_image(a0.localPos())

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

                group_mode = int(a0.modifiers()) == Qt.ControlModifier
                self.selectShapePoint(pos, multiple_selection_mode=group_mode)
                self.prevPoint = pos
                self.update()
        elif a0.button() == Qt.RightButton and self.editing():
            group_mode = int(a0.modifiers()) == Qt.ControlModifier
            if not self.selectedShapes or (
                self.hShape is not None and self.hShape not in self.selectedShapes
            ):
                self.selectShapePoint(pos, multiple_selection_mode=group_mode)
                self.update()
            self.prevPoint = pos
        elif a0.button() == Qt.MiddleButton and self._is_dragging_enabled:
            self._apply_cursor(CURSOR_GRAB)
            self._dragging_start_pos = pos
            self._is_dragging = True
        self._update_status()

    def mouseReleaseEvent(self, a0: QtGui.QMouseEvent) -> None:
        if a0.button() == Qt.RightButton:
            menu = self.menus[len(self.selectedShapesCopy) > 0]
            self._release_cursor()
            if not menu.exec_(self.mapToGlobal(a0.pos())) and self.selectedShapesCopy:  # type: ignore
                # Cancel the move by deleting the shadow copy.
                self.selectedShapesCopy = []
                self.update()
        elif a0.button() == Qt.LeftButton:
            if self.editing():
                if (
                    self.hShape is not None
                    and self.hShapeIsSelected
                    and not self.movingShape
                ):
                    self.selectionChanged.emit(
                        [x for x in self.selectedShapes if x != self.hShape]
                    )
        elif a0.button() == Qt.MiddleButton:
            self._is_dragging = False
            self._release_cursor()

        if self.movingShape and self.hShape and self.hShape in self.shapes:
            index = self.shapes.index(self.hShape)
            if self.shapesBackups[-1][index].points != self.shapes[index].points:
                self.storeShapes()
                self.shapeMoved.emit()

            self.movingShape = False
        self._update_status()

    def endMove(self, copy: bool) -> bool:
        assert self.selectedShapes and self.selectedShapesCopy
        assert len(self.selectedShapesCopy) == len(self.selectedShapes)
        if copy:
            for i, shape in enumerate(self.selectedShapesCopy):
                self.shapes.append(shape)
                self.selectedShapes[i].selected = False
                self.selectedShapes[i] = shape
        else:
            for i, shape in enumerate(self.selectedShapesCopy):
                self.selectedShapes[i].points = shape.points
        self.selectedShapesCopy = []
        self.update()
        self.storeShapes()
        return True

    def hideBackgroundShapes(self, value: bool) -> None:
        self.hideBackground = value
        if self.selectedShapes:
            # Only hide other shapes if there is a current selection.
            # Otherwise the user will not be able to select a shape.
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
        """Select the first shape created which contains this point."""
        if self.hVertex is not None:
            assert self.hShape is not None
            self.hShape.highlightVertex(i=self.hVertex, action=self.hShape.MOVE_VERTEX)
        else:
            shape: Shape
            for shape in reversed(self.shapes):
                if self.isVisible(shape) and shape.containsPoint(point):
                    self.setHiding()
                    if shape not in self.selectedShapes:
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
        if not self.selectedShapes:
            self.offsets = QPointF(0.0, 0.0), QPointF(0.0, 0.0)
            return

        rects = [s.boundingRect() for s in self.selectedShapes]
        left = min(r.left() for r in rects)
        top = min(r.top() for r in rects)
        right = max(r.right() for r in rects)
        bottom = max(r.bottom() for r in rects)

        self.offsets = (
            QPointF(left - point.x(), top - point.y()),
            QPointF(right - point.x(), bottom - point.y()),
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

        tl = pos + self.offsets[0]
        if self.outOfPixmap(tl):
            pos -= QPointF(min(0, tl.x()), min(0, tl.y()))

        br = pos + self.offsets[1]
        if self.outOfPixmap(br):
            pos += QPointF(
                min(0, self.pixmap.width() - br.x()),
                min(0, self.pixmap.height() - br.y()),
            )

        dp = pos - self.prevPoint
        if dp.isNull():
            return False

        for shape in shapes:
            shape.moveBy(dp)
        self.prevPoint = pos
        return True

    def deSelectShape(self) -> bool:
        need_update: bool = False
        if self.selectedShapes:
            self.setHiding(False)
            self.selectionChanged.emit([])
            self.hShapeIsSelected = False
            need_update = True
        return need_update

    def deleteSelected(self) -> list[Shape]:
        deleted_shapes = []
        if self.selectedShapes:
            for shape in self.selectedShapes:
                self.shapes.remove(shape)
                deleted_shapes.append(shape)
            self.storeShapes()
            self.selectedShapes = []
            self.update()
        return deleted_shapes

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

        painter: QtGui.QPainter = self._painter
        painter.begin(self)
        try:
            for hint in (
                QtGui.QPainter.Antialiasing,
                QtGui.QPainter.HighQualityAntialiasing,
                QtGui.QPainter.SmoothPixmapTransform,
            ):
                painter.setRenderHint(hint)
            painter.translate(self._compute_image_origin_offset() * self.scale)
            self._paint_background(painter=painter)
            self._paint_crosshair(painter=painter)
            self._paint_shapes(painter=painter)
            self._paint_current_shape_preview(painter=painter)
        finally:
            painter.end()

    def _paint_background(self, painter: QtGui.QPainter) -> None:
        painter.save()
        painter.scale(self.scale, self.scale)
        painter.drawPixmap(0, 0, self.pixmap)
        painter.restore()

    def _paint_crosshair(self, painter: QtGui.QPainter) -> None:
        if not self._crosshair[self._createMode]:
            return
        if not self.drawing():
            return

        cursor: QPointF | None = self.prevMovePoint
        if cursor is None or self.outOfPixmap(cursor):
            return

        painter.setPen(QtGui.QColor(0, 0, 0))
        painter.drawLine(
            0,
            int(cursor.y() * self.scale),
            int(self.pixmap.width() * self.scale) - 1,
            int(cursor.y() * self.scale),
        )
        painter.drawLine(
            int(cursor.x() * self.scale),
            0,
            int(cursor.x() * self.scale),
            int(self.pixmap.height() * self.scale) - 1,
        )

    def _paint_shapes(self, painter: QtGui.QPainter) -> None:
        Shape.scale = self.scale
        for shape in self.shapes:
            if not self.isVisible(shape):
                continue
            if not shape.selected and self._hideBackground:
                continue
            shape.fill = shape.selected or shape is self.hShape
            shape.paint(painter)
        if self.current is not None:
            self.current.paint(painter)
            assert len(self.line.points) == len(self.line.point_labels)
            self.line.paint(painter)
        for copy_shape in self.selectedShapesCopy:
            copy_shape.paint(painter)

    def _paint_current_shape_preview(self, painter: QtGui.QPainter) -> None:
        if self.current is None or self.createMode not in (
            "polygon",
            "ai_points_to_shape",
        ):
            return

        preview: Shape = self.current.copy()
        if self.createMode == "polygon":
            if self.fillDrawing() and len(preview.points) >= 2:
                assert preview.fill_color is not None
                if preview.fill_color.getRgb()[3] == 0:
                    logger.warning(
                        "fill_drawing=true, but fill_color is transparent,"
                        " so forcing to be opaque."
                    )
                    preview.fill_color.setAlpha(64)
                preview.addPoint(point=self.line[1])
        else:
            assert self.createMode == "ai_points_to_shape"
            preview.addPoint(
                point=self.line.points[1],
                label=self.line.point_labels[1],
            )
            ai_shapes = self._shapes_from_points_ai(
                points=preview.points,
                point_labels=preview.point_labels,
            )
            if ai_shapes:
                preview = ai_shapes[0]
        preview.fill = self.fillDrawing()
        preview.selected = self.fillDrawing()
        preview.paint(painter)

    def _transform_point_widget_to_image(self, point: QPointF) -> QPointF:
        return point / self.scale - self._compute_image_origin_offset()

    def enableDragging(self, enabled: bool) -> None:
        self._is_dragging_enabled = enabled

    def _compute_image_origin_offset(self) -> QPointF:
        area = super().size()
        scaled_w = self.pixmap.width() * self.scale
        scaled_h = self.pixmap.height() * self.scale
        slack_w = max(area.width() - scaled_w, 0.0)
        slack_h = max(area.height() - scaled_h, 0.0)
        return QPointF(slack_w, slack_h) / (2.0 * self.scale)

    def outOfPixmap(self, p: QPointF) -> bool:
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
        self.storeShapes()
        self._reset_after_shape_creation()

    def _build_new_shapes_from_current(self) -> list[Shape]:
        assert self.current is not None
        if self.createMode == "ai_points_to_shape":
            return self._shapes_from_points_ai(
                points=self.current.points,
                point_labels=self.current.point_labels,
            )
        if self.createMode == "ai_box_to_shape":
            return self._shapes_from_bbox_ai(bbox_points=self.current.points)
        self.current.close()
        return [self.current]

    def _reset_after_shape_creation(self) -> None:
        self.current = None
        self.setHiding(False)
        self.newShape.emit()
        self.update()

    def _cancel_current_shape(self) -> None:
        self.current = None
        self.drawingPolygon.emit(False)
        self.update()

    def closeEnough(self, p1: QPointF, p2: QPointF) -> bool:
        # d = distance(p1 - p2)
        # m = (p1-p2).manhattanLength()
        # print "d %.2f, m %d, %.2f" % (d, m, d - m)
        # divide by scale to allow more precision when zoomed in
        return labelme.utils.distance(p1 - p2) < (self.epsilon / self.scale)

    # These two, along with a call to adjustSize are required for the
    # scroll area.
    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSizeHint()

    def minimumSizeHint(self) -> QtCore.QSize:
        if not self.pixmap:
            return super().minimumSizeHint()

        min_size = self.scale * self.pixmap.size()
        if self._is_dragging_enabled:
            # When drag buffer should be enabled, add a bit of buffer around the image
            # This lets dragging the image around have a bit of give on the edges
            min_size = 1.167 * min_size
        return min_size

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
        if self.selectedShapes:
            self.boundedMoveShapes(self.selectedShapes, self.prevPoint + offset)
            self.update()
            self.movingShape = True

    def keyPressEvent(self, a0: QtGui.QKeyEvent) -> None:
        modifiers = a0.modifiers()
        key = a0.key()
        if self.drawing():
            if key == Qt.Key_Escape and self.current:
                self._cancel_current_shape()
            elif (
                key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Space)
                and self.canCloseShape()
            ):
                self.finalise()
            elif modifiers == Qt.AltModifier:
                self.snapping = False
        elif self.editing():
            if key == Qt.Key_Up:
                self.moveByKeyboard(QPointF(0.0, -MOVE_SPEED))
            elif key == Qt.Key_Down:
                self.moveByKeyboard(QPointF(0.0, MOVE_SPEED))
            elif key == Qt.Key_Left:
                self.moveByKeyboard(QPointF(-MOVE_SPEED, 0.0))
            elif key == Qt.Key_Right:
                self.moveByKeyboard(QPointF(MOVE_SPEED, 0.0))
            elif a0.matches(QtGui.QKeySequence.SelectAll):
                self.selectShapes(shapes=self.shapes[:])
        self._update_status()

    def keyReleaseEvent(self, a0: QtGui.QKeyEvent) -> None:
        modifiers = a0.modifiers()
        if self.drawing():
            if int(modifiers) == 0:
                self.snapping = True
        elif self.editing():
            if (
                self.movingShape
                and self.selectedShapes
                and self.selectedShapes[0] in self.shapes
            ):
                index = self.shapes.index(self.selectedShapes[0])
                if self.shapesBackups[-1][index].points != self.shapes[index].points:
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
        if self.createMode in ("ai_points_to_shape", "ai_box_to_shape"):
            # Remove all unlabeled shapes at the tail (added by AI in one shot)
            while self.shapes and self.shapes[-1].label is None:
                self.shapes.pop()
            self._cancel_current_shape()
            return
        self.current = self.shapes.pop()
        self.current.setOpen()
        self.current.restoreShapeRaw()
        if self.createMode in ("polygon", "linestrip"):
            self.line.points = [self.current[-1], self.current[0]]
        elif self.createMode in ("rectangle", "line", "circle", "ai_box_to_shape"):
            self.current.points = self.current.points[0:1]
        elif self.createMode == "point":
            self.current = None
        self.drawingPolygon.emit(True)

    def undoLastPoint(self) -> None:
        current = self.current
        if current is None or current.isClosed():
            return
        current.popPoint()
        if len(current) > 0:
            self.line[0] = current[-1]
            self.update()
        else:
            self._cancel_current_shape()

    def loadPixmap(self, pixmap: QtGui.QPixmap, clear_shapes: bool = True) -> None:
        self.pixmap = pixmap
        self._pixmap_hash = hash(
            labelme.utils.img_qt_to_arr(img_qt=self.pixmap.toImage()).tobytes()
        )
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

    def resetState(self) -> None:
        self._release_cursor()
        self.pixmap = QtGui.QPixmap()
        self._pixmap_hash = None
        self.shapes = []
        self.shapesBackups = collections.deque(maxlen=self.num_backups)
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
