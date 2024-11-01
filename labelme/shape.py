from typing import List

import copy
from enum import Enum

import numpy as np
import skimage.measure
from qtpy import QtCore
from qtpy import QtGui

import labelme.utils
from labelme.logger import logger


# TODO(unknown):
# - [opt] Store paths instead of creating new ones at each paint.

class ShapeClass(Enum):
    TEXT = 0
    ROW = 1
    LETTER = 2


class IdController:
    _count: int = 0

    @classmethod
    def resetCount(cls):
        cls._count = 0

    @classmethod
    def getId(cls):
        tmp = cls._count
        cls._count += 1
        return tmp


class Shape(object):
    # Render handles as squares
    P_SQUARE = 0

    # Render handles as circles
    P_ROUND = 1

    # Flag for the handles we would move if dragging
    MOVE_VERTEX = 0

    # Flag for all other handles on the current shape
    NEAR_VERTEX = 1

    PEN_WIDTH = 2

    # цвета для блока текста и строки
    text_color = None
    row_color = None
    # The following class variables influence the drawing of all shape objects.
    line_color = None
    fill_color = None
    select_line_color = None
    select_fill_color = None
    vertex_fill_color = None
    hvertex_fill_color = None
    point_type = P_ROUND
    point_size = 8
    scale = 1.0

    def __init__(
        self,
        id = None,
        label=None,
        diacritical=None,
        line_color=None,
        shape_type=None,
        flags=None,
        group_id=None,
        description=None,
        mask=None,
        parent : "Shape" = None,
    ):
        if id is None:
            self._id: int = IdController.getId()
        else:
            self._id = id
        self.label = label
        self.diacritical = diacritical
        self.group_id = group_id
        self.points: List[QtCore.QPoint] = []
        self.point_labels = []
        self.shape_type = shape_type
        self._shape_raw = None
        self._points_raw = []
        self._shape_type_raw = None
        self.fill = False
        self.selected = False
        self.description = description
        self.other_data = {}
        self.mask = mask

        # self.parent - родительский элемент по отношению к текущему.
        # В зависимости от класса родителя автоматически подбирается класс потомка
        # self._shape_class - класс элемента (текст, строка, буква)
        if parent is None:
            self.parent = None
            self._shape_class = ShapeClass.TEXT
        else:
            self.parent = parent
            if parent.getClass() == ShapeClass.TEXT:
                self._shape_class = ShapeClass.ROW
            elif parent.getClass() == ShapeClass.ROW:
                self._shape_class = ShapeClass.LETTER
            else:
                raise Exception(f"Shape wrong parent shape_class: {parent.getClass()}")
            parent._addChild(self)
        # self._children - список потомков элемента
        self._children: List[Shape] = []

        self._highlightIndex = None
        self._highlightMode = self.NEAR_VERTEX
        self._highlightSettings = {
            self.NEAR_VERTEX: (4, self.P_ROUND),
            self.MOVE_VERTEX: (1.5, self.P_SQUARE),
        }

        self._closed = False

        if line_color is not None:
            # Override the class line_color attribute
            # with an object attribute. Currently this
            # is used for drawing the pending line a different color.
            self.line_color = line_color

    def delete(self):
        """
            Удаляет элемент и также стирает его из списка потомков родителя
        """
        if self.parent is not None:
            self.parent._deleteChild(self)

    def _addChild(self, shape: "Shape"):
        if self._shape_class == ShapeClass.LETTER:
            Exception("Letter can't be parent.")
        self._children.append(shape)

    def _deleteChild(self, shape: "Shape"):
        if shape in self._children:
            self._children.remove(shape)

    def _childrenRecursive(self, list: List["Shape"]):
        for a in self._children:
            list.append(a)
        for a in self._children:
            a._childrenRecursive(list)

    def getAllChildren(self) -> List["Shape"]:
        """
            Возвращает всех потомков
        """
        list = []
        self._childrenRecursive(list)
        return list

    def getChildren(self):
        """
            Возвращает прямых потомков
        """
        return self._children

    def getId(self):
        return self._id

    def getClass(self):
        """
            Возвращает класс элемента (Текст, Строка, Буква)
        """
        return self._shape_class

    def _scale_point(self, point: QtCore.QPointF) -> QtCore.QPointF:
        return QtCore.QPointF(point.x() * self.scale, point.y() * self.scale)

    def setShapeRefined(self, shape_type, points, point_labels, mask=None):
        self._shape_raw = (self.shape_type, self.points, self.point_labels)
        self.shape_type = shape_type
        self.points = points
        self.point_labels = point_labels
        self.mask = mask

    def restoreShapeRaw(self):
        if self._shape_raw is None:
            return
        self.shape_type, self.points, self.point_labels = self._shape_raw
        self._shape_raw = None

    @property
    def shape_type(self):
        return self._shape_type

    @shape_type.setter
    def shape_type(self, value):
        if value is None:
            value = "rectangle"
        if value not in [
            "rectangle",
            "mask",
        ]:
            raise ValueError("Unexpected shape_type: {}".format(value))
        self._shape_type = value

    def close(self):
        self._closed = True

    def addPoint(self, point, label=1):
        if self.points and point == self.points[0]:
            self.close()
        else:
            self.points.append(point)
            self.point_labels.append(label)

    def getCroppBox(self) -> QtCore.QRect:
        """
            Находит обрамляющий прямоугольник для обрезки изоображения
            
            -------------
            Возвращает
            
            QTCore.QRect(x, y, width, height)
                Координаты и размеры прямоугольника
        """

        x = [100000000, 0]
        y = [100000000, 0]
        for point in self.points:
            x[0] = min(point.x(), x[0])
            x[1] = max(point.x(), x[1])

            y[0] = min(point.y(), y[0])
            y[1] = max(point.y(), y[1])

        return QtCore.QRect(int(x[0]), int(y[0]), int(x[1] - x[0]), int(y[1] - y[0]))

    def canAddPoint(self):
        return self.shape_type in ["polygon"]

    def popPoint(self):
        if self.points:
            if self.point_labels:
                self.point_labels.pop()
            return self.points.pop()
        return None

    def insertPoint(self, i, point, label=1):
        self.points.insert(i, point)
        self.point_labels.insert(i, label)

    def removePoint(self, i):
        if not self.canAddPoint():
            logger.warning(
                "Cannot remove point from: shape_type=%r",
                self.shape_type,
            )
            return

        if self.shape_type == "polygon" and len(self.points) <= 3:
            logger.warning(
                "Cannot remove point from: shape_type=%r, len(points)=%d",
                self.shape_type,
                len(self.points),
            )
            return

        self.points.pop(i)
        self.point_labels.pop(i)

    def isClosed(self):
        return self._closed

    def setOpen(self):
        self._closed = False

    def paint(self, painter):
        if self.mask is None and not self.points:
            return

        color = self.select_line_color if self.selected else self.line_color
        pen = QtGui.QPen(color)
        # Try using integer sizes for smoother drawing(?)
        pen.setWidth(self.PEN_WIDTH)
        painter.setPen(pen)

        if self.mask is not None:
            image_to_draw = np.zeros(self.mask.shape + (4,), dtype=np.uint8)
            fill_color = (
                self.select_fill_color.getRgb()
                if self.selected
                else self.fill_color.getRgb()
            )
            image_to_draw[self.mask] = fill_color
            qimage = QtGui.QImage.fromData(labelme.utils.img_arr_to_data(image_to_draw))
            qimage = qimage.scaled(
                qimage.size() * self.scale,
                QtCore.Qt.IgnoreAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )

            painter.drawImage(self._scale_point(point=self.points[0]), qimage)

            line_path = QtGui.QPainterPath()
            contours = skimage.measure.find_contours(np.pad(self.mask, pad_width=1))
            for contour in contours:
                contour += [self.points[0].y(), self.points[0].x()]
                line_path.moveTo(
                    self._scale_point(QtCore.QPointF(contour[0, 1], contour[0, 0]))
                )
                for point in contour[1:]:
                    line_path.lineTo(
                        self._scale_point(QtCore.QPointF(point[1], point[0]))
                    )
            painter.drawPath(line_path)

        if self.points:
            line_path = QtGui.QPainterPath()
            vrtx_path = QtGui.QPainterPath()
            negative_vrtx_path = QtGui.QPainterPath()

            if self.shape_type in ["rectangle", "mask"]:
                assert len(self.points) in [1, 2]
                if len(self.points) == 2:
                    rectangle = QtCore.QRectF(
                        self._scale_point(self.points[0]),
                        self._scale_point(self.points[1]),
                    )
                    line_path.addRect(rectangle)
                if self.shape_type == "rectangle":
                    for i in range(len(self.points)):
                        self.drawVertex(vrtx_path, i)
            else:
                line_path.moveTo(self._scale_point(self.points[0]))
                # Uncommenting the following line will draw 2 paths
                # for the 1st vertex, and make it non-filled, which
                # may be desirable.
                # self.drawVertex(vrtx_path, 0)

                for i, p in enumerate(self.points):
                    line_path.lineTo(self._scale_point(p))
                    self.drawVertex(vrtx_path, i)
                if self.isClosed():
                    line_path.lineTo(self._scale_point(self.points[0]))

            painter.drawPath(line_path)
            if vrtx_path.length() > 0:
                painter.drawPath(vrtx_path)
                painter.fillPath(vrtx_path, self._vertex_fill_color)
            if self.fill and self.mask is None:
                color = self.select_fill_color if self.selected else self.fill_color
                painter.fillPath(line_path, color)

            pen.setColor(QtGui.QColor(255, 0, 0, 255))
            painter.setPen(pen)
            painter.drawPath(negative_vrtx_path)
            painter.fillPath(negative_vrtx_path, QtGui.QColor(255, 0, 0, 255))

    def drawVertex(self, path, i):
        d = self.point_size
        shape = self.point_type
        point = self._scale_point(self.points[i])
        if i == self._highlightIndex:
            size, shape = self._highlightSettings[self._highlightMode]
            d *= size
        if self._highlightIndex is not None:
            self._vertex_fill_color = self.hvertex_fill_color
        else:
            self._vertex_fill_color = self.vertex_fill_color
        if shape == self.P_SQUARE:
            path.addRect(point.x() - d / 2, point.y() - d / 2, d, d)
        elif shape == self.P_ROUND:
            path.addEllipse(point, d / 2.0, d / 2.0)
        else:
            assert False, "unsupported vertex shape"

    def nearestVertex(self, point, epsilon):
        min_distance = float("inf")
        min_i = None
        point = QtCore.QPointF(point.x() * self.scale, point.y() * self.scale)
        for i, p in enumerate(self.points):
            p = QtCore.QPointF(p.x() * self.scale, p.y() * self.scale)
            dist = labelme.utils.distance(p - point)
            if dist <= epsilon and dist < min_distance:
                min_distance = dist
                min_i = i
        return min_i

    def nearestEdge(self, point, epsilon):
        min_distance = float("inf")
        post_i = None
        point = QtCore.QPointF(point.x() * self.scale, point.y() * self.scale)
        for i in range(len(self.points)):
            start = self.points[i - 1]
            end = self.points[i]
            start = QtCore.QPointF(start.x() * self.scale, start.y() * self.scale)
            end = QtCore.QPointF(end.x() * self.scale, end.y() * self.scale)
            line = [start, end]
            dist = labelme.utils.distancetoline(point, line)
            if dist <= epsilon and dist < min_distance:
                min_distance = dist
                post_i = i
        return post_i

    def containsPoint(self, point):
        if self.mask is not None:
            y = np.clip(
                int(round(point.y() - self.points[0].y())),
                0,
                self.mask.shape[0] - 1,
            )
            x = np.clip(
                int(round(point.x() - self.points[0].x())),
                0,
                self.mask.shape[1] - 1,
            )
            return self.mask[y, x]
        return self.makePath().contains(point)

    def makePath(self):
        if self.shape_type in ["rectangle", "mask"]:
            path = QtGui.QPainterPath()
            if len(self.points) == 2:
                path.addRect(QtCore.QRectF(self.points[0], self.points[1]))
        else:
            path = QtGui.QPainterPath(self.points[0])
            for p in self.points[1:]:
                path.lineTo(p)
        return path

    def boundingRect(self):
        return self.makePath().boundingRect()

    def moveBy(self, offset):
        self.points = [p + offset for p in self.points]

    def moveVertexBy(self, i, offset):
        self.points[i] = self.points[i] + offset

    def highlightVertex(self, i, action):
        """Highlight a vertex appropriately based on the current action

        Args:
            i (int): The vertex index
            action (int): The action
            (see Shape.NEAR_VERTEX and Shape.MOVE_VERTEX)
        """
        self._highlightIndex = i
        self._highlightMode = action

    def highlightClear(self):
        """Clear the highlighted point"""
        self._highlightIndex = None

    def copy(self):
        shape = Shape(parent=self.parent, id=self._id)
        shape.label = self.label
        shape.diacritical = self.diacritical
        shape.points = copy.deepcopy(self.points)
        shape.shape_type = self.shape_type
        shape.description = self.description

    def _copyWithChildren(self, list: List["Shape"], parent: "Shape" = None):
        shape = Shape(parent=parent, id=self._id)
        shape.label = self.label
        shape.diacritical = self.diacritical
        shape.points = copy.deepcopy(self.points)
        shape.shape_type = self.shape_type
        shape.description = self.description
        list.append(shape)
        for child in self._children:
            child._copyWithChildren(list, shape)

    def copyWithChildren(self):
        allShapes: List[Shape] = []
        self._copyWithChildren(allShapes, None)
        return allShapes

    def __len__(self):
        return len(self.points)

    def __getitem__(self, key):
        return self.points[key]

    def __setitem__(self, key, value):
        self.points[key] = value
