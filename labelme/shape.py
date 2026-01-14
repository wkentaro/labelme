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

    # TODO: Use to config file for the size of the orientation arrow.
    orientation_arrow_scale = np.array([5.0, 5.0])
    arrow_points = [
        np.array([0.22, -0.5]) * orientation_arrow_scale,
        np.array([1.0, 0.0]) * orientation_arrow_scale,
        np.array([0.22, 0.5]) * orientation_arrow_scale,
        np.array([-1.0, 0.0]) * orientation_arrow_scale,
    ]
    orientation_arrow_size = np.max(arrow_points, axis=0) - np.min(arrow_points, axis=0)

    point_type = P_ROUND
    point_size = 8
    scale = 1.0

    _current_vertex_fill_color: QtGui.QColor
    _current_rotation_point_fill_color: QtGui.QColor

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
        self._highlight_rotation_point_index = None,
        self._highlight_orientation_arrow = False,

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
            "oriented rectangle",
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
        if self.shape_type == "oriented rectangle":
            self.points.append(point)
            self.point_labels.append(label)
        elif self.points and point == self.points[0]:
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

    def canRemovePoint(self) -> bool:
        if not self.canAddPoint():
            return False

        if self.shape_type == "polygon" and len(self.points) <= 3:
            return False

        if self.shape_type == "linestrip" and len(self.points) <= 2:
            return False

        if self.shape_type == "oriented rectangle":
            return False
        return True

    def removePoint(self, i: int):
        if not self.canRemovePoint():
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
            rotation_points_path = QtGui.QPainterPath()
            orientation_arrow_path = QtGui.QPainterPath()
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
            elif self.shape_type == "oriented rectangle":
                assert len(self.points) in [1, 2, 3, 4]
                line_path.moveTo(self._scale_point(self.points[0]))
                if self.isClosed():
                    for i, p in enumerate(self.points):
                        line_path.lineTo(self._scale_point(p))
                        self.drawVertex(vrtx_path, i)
                    center = self.getCenter()
                    angle = self.getRotationRad()
                    self.drawArrow(orientation_arrow_path, center, angle)
                    line_path.lineTo(self._scale_point(self.points[0]))
                    self.drawRotationPoints(rotation_points_path)
                elif len(self.points) > 1:
                    # Draw a preview of the shape.
                    self.drawVertex(vrtx_path, 0)
                    line_path.lineTo(self._scale_point(self.points[1]))
                    self.drawVertex(vrtx_path, 1)
            elif self.shape_type == "circle":
                assert len(self.points) in [1, 2]
                if len(self.points) == 2:
                    radius = labelme.utils.distance(
                        self._scale_point(self.points[0] - self.points[1])
                    )
                    line_path.addEllipse(
                        self._scale_point(self.points[0]), radius, radius
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
            if rotation_points_path.length() > 0:
                painter.drawPath(rotation_points_path)
                painter.fillPath(rotation_points_path, self._current_rotation_point_fill_color)
            if self.fill and self.shape_type not in [
                "line",
                "linestrip",
                "points",
                "mask",
            ]:
                color = self.select_fill_color if self.selected else self.fill_color
                painter.fillPath(line_path, color)
            
            if orientation_arrow_path.length() > 0:
                if self._highlight_orientation_arrow:
                    arrow_highlight_color = self.hvertex_fill_color
                else:
                    arrow_highlight_color = self.vertex_fill_color
                pen.setColor(arrow_highlight_color)
                painter.setPen(pen)
                painter.drawPath(orientation_arrow_path)

            pen.setColor(QtGui.QColor(255, 0, 0, 255))
            painter.setPen(pen)
            painter.drawPath(negative_vrtx_path)
            painter.fillPath(negative_vrtx_path, QtGui.QColor(255, 0, 0, 255))

    def getRotationRad(self) -> float:
        if self.shape_type == "oriented rectangle":
            return labelme.utils.angleRad(self.points[0], self.points[1])
        else:
            return 0.0

    def getCenter(self) -> QtCore.QPointF:
        assert len(self.points) != 0
        center = QtCore.QPointF(0.0, 0.0)
        for p in self.points:
            center += p
        return center / len(self.points)

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

    def drawRotationPoints(self, path: QtGui.QPainterPath):
        if self._highlight_rotation_point_index is not None:
            self._current_rotation_point_fill_color = self.hvertex_fill_color
        else:
            self._current_rotation_point_fill_color = self.vertex_fill_color

        for i, p in enumerate(self.getRotationPoints()):
            d = self.point_size
            point = self._scale_point(p)
            if i == self._highlight_rotation_point_index:
                pass
            path.addEllipse(point, d / 2.0, d / 2.0)

    def drawArrow(self, path: QtGui.QPainterPath, position: QtCore.QPointF, angle_rad: float):
        transformed_points = np.add(labelme.utils.rotateMany(self.arrow_points, angle_rad), [position.x(), position.y()])
        q_points = [self._scale_point(QtCore.QPointF(*p)) for p in transformed_points]

        path.moveTo(q_points[0])
        path.lineTo(q_points[1])
        path.lineTo(q_points[2])
        path.moveTo(q_points[3])
        path.lineTo(q_points[1])

    def cycleOrientation(self):
        """
        Cycle the orientation of the shape in a clockwise manner.
        """
        if self.shape_type != "oriented rectangle":
            return
        
        previous_point = self.points[0]
        previous_point_label = self.point_labels[0]
        for i, p in reversed(list(self.points)):
            self.points[i] = previous_point
            previous_point = p

            label = self.point_labels[i]
            self.point_labels[i] = previous_point_label
            previous_point_label = label

    def isHoveringOrientationArrow(self, point: QtCore.QPointF, epsilon: float) -> bool:
        if self.shape_type != "oriented rectangle":
            return False
        
        # The hover area is the bounding box of the arrow.
        angle_rad = self.getRotationRad()
        center = self._scale_point(self.getCenter())
        arrow_size = self._scale_point(QtCore.QPointF(*self.orientation_arrow_size))
        w, h = arrow_size.x(), arrow_size.y()
        point = self._scale_point(point)
        point_np = np.array([point.x(), point.y()])
        center_np = np.array([center.x(), center.y()])
        # Transform the point into the bounding box's frame so we can consider the box as axis-aligned.
        transformed = QtCore.QPointF(*labelme.utils.rotate(point_np - center_np, -angle_rad))
        # The point is transformed around the center of the bounding box. Offset it using the bounding box's size.
        transformed += QtCore.QPointF(w, h)/2
        if transformed.x() < -epsilon:
            return False
        if transformed.x() > w + epsilon:
            return False
        if transformed.y() < -epsilon:
            return False
        if transformed.y() > h + epsilon:
            return False
        return True

    def nearestVertex(self, point, epsilon):
        min_distance = float("inf")
        min_i = None
        point = self._scale_point(point)
        for i, p in enumerate(self.points):
            p = self._scale_point(p)
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

    def nearestRotationPoint(self, point, epsilon):
        min_distance = float("inf")
        min_i = None
        point = self._scale_point(point)
        for i, p in enumerate(self.getRotationPoints()):
            p = self._scale_point(p)
            dist = labelme.utils.distance(p - point)
            if dist <= epsilon and dist < min_distance:
                min_distance = dist
                min_i = i
        return min_i

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

    def getRotationPoints(self):
        rotation_points = []
        if self.shape_type == "oriented rectangle":
            for i, p in enumerate(self.points):
                rotation_points.append((p + self.points[i-1])/2)
        return rotation_points

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
        self._highlight_rotation_point_index = None

    def highlightRotationPoint(self, i, action):
        self._highlight_rotation_point_index = i
        self._highlightIndex = None
        #TODO

    def highlightOrientationArrow(self):
        self._highlight_orientation_arrow = True
        self._highlightIndex = None
        self._highlight_rotation_point_index = None

    def highlightClear(self):
        """Clear the highlighted point"""
        self._highlightIndex = None
        self._highlight_orientation_arrow = False
        self._highlight_rotation_point_index = None

    def copy(self):
        return copy.deepcopy(self)

    def __len__(self):
        return len(self.points)

    def __getitem__(self, key):
        return self.points[key]

    def __setitem__(self, key, value):
        self.points[key] = value
