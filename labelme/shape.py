import copy

import numpy as np
import skimage.measure
from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui

import labelme.utils

# TODO(unknown):
# - [opt] Store paths instead of creating new ones at each paint.


class Shape:
    # Render handles as squares
    P_SQUARE = 0

    # Render handles as circles
    P_ROUND = 1

    # Flag for the handles we would move if dragging
    MOVE_VERTEX = 0

    # Flag for all other handles on the current shape
    NEAR_VERTEX = 1

    PEN_WIDTH = 2

    # The following class variables influence the drawing of all shape objects.
    line_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 128)
    fill_color: QtGui.QColor = QtGui.QColor(0, 0, 0, 64)
    vertex_fill_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 255)
    select_line_color: QtGui.QColor = QtGui.QColor(255, 255, 255, 255)
    select_fill_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 64)
    hvertex_fill_color: QtGui.QColor = QtGui.QColor(255, 255, 255, 255)

    point_type = P_ROUND
    point_size = 8
    scale = 1.0

    _current_vertex_fill_color: QtGui.QColor

    def __init__(
        self,
        label=None,
        line_color=None,
        shape_type=None,
        flags=None,
        group_id=None,
        description=None,
        mask=None,
    ):
        self.label = label
        self.group_id = group_id
        self.points = []
        self.point_labels = []
        self.shape_type = shape_type
        self._shape_raw = None
        self._points_raw = []
        self._shape_type_raw = None
        self.fill = False
        self.selected = False
        self.flags = flags
        self.description = description
        self.other_data = {}
        self.mask = mask

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
            value = "polygon"
        if value not in [
            "polygon",
            "rectangle",
            "point",
            "line",
            "circle",
            "linestrip",
            "points",
            "mask",
        ]:
            raise ValueError(f"Unexpected shape_type: {value}")
        self._shape_type = value

    def close(self):
        self._closed = True

    def addPoint(self, point, label=1):
        if self.points and point == self.points[0]:
            self.close()
        else:
            self.points.append(point)
            self.point_labels.append(label)

    def canAddPoint(self):
        return self.shape_type in ["polygon", "linestrip"]

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

        if self.shape_type == "linestrip" and len(self.points) <= 2:
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
            elif self.shape_type == "circle":
                assert len(self.points) in [1, 2]
                if len(self.points) == 2:
                    raidus = labelme.utils.distance(
                        self._scale_point(self.points[0] - self.points[1])
                    )
                    line_path.addEllipse(
                        self._scale_point(self.points[0]), raidus, raidus
                    )
                for i in range(len(self.points)):
                    self.drawVertex(vrtx_path, i)
            elif self.shape_type == "linestrip":
                line_path.moveTo(self._scale_point(self.points[0]))
                for i, p in enumerate(self.points):
                    line_path.lineTo(self._scale_point(p))
                    self.drawVertex(vrtx_path, i)
            elif self.shape_type == "points":
                assert len(self.points) == len(self.point_labels)
                for i, point_label in enumerate(self.point_labels):
                    if point_label == 1:
                        self.drawVertex(vrtx_path, i)
                    else:
                        self.drawVertex(negative_vrtx_path, i)
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
                painter.fillPath(vrtx_path, self._current_vertex_fill_color)
            if self.fill and self.shape_type not in [
                "line",
                "linestrip",
                "points",
                "mask",
            ]:
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
            d *= size  # type: ignore[assignment]
        if self._highlightIndex is not None:
            self._current_vertex_fill_color = self.hvertex_fill_color
        else:
            self._current_vertex_fill_color = self.vertex_fill_color
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

    def containsPoint(self, point) -> bool:
        if self.shape_type in ["line", "linestrip", "points"]:
            return False
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
        elif self.shape_type == "circle":
            path = QtGui.QPainterPath()
            if len(self.points) == 2:
                raidus = labelme.utils.distance(self.points[0] - self.points[1])
                path.addEllipse(self.points[0], raidus, raidus)
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
        return copy.deepcopy(self)

    def __len__(self):
        return len(self.points)

    def __getitem__(self, key):
        return self.points[key]

    def __setitem__(self, key, value):
        self.points[key] = value
