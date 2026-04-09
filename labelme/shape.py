from __future__ import annotations

import copy
import enum

import numpy as np
import numpy.typing as npt
import skimage.measure
from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui

import labelme.utils


class _PointStyle(enum.IntEnum):
    SQUARE = 0
    ROUND = 1


class _VertexMode(enum.IntEnum):
    MOVE = 0
    NEAR = 1


class Shape:
    # Handle point styles: square or round
    P_SQUARE = _PointStyle.SQUARE
    P_ROUND = _PointStyle.ROUND

    # Vertex interaction modes
    MOVE_VERTEX = _VertexMode.MOVE
    NEAR_VERTEX = _VertexMode.NEAR

    PEN_WIDTH = 2

    _VALID_SHAPE_TYPES = {
        "circle",
        "line",
        "linestrip",
        "mask",
        "point",
        "points",
        "polygon",
        "rectangle",
    }

    # The following class variables influence the drawing of all shape objects.
    line_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 128)
    fill_color: QtGui.QColor = QtGui.QColor(0, 0, 0, 64)
    vertex_fill_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 255)
    select_line_color: QtGui.QColor = QtGui.QColor(255, 255, 255, 255)
    select_fill_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 64)
    hvertex_fill_color: QtGui.QColor = QtGui.QColor(255, 255, 255, 255)

    # Default handle style, size, and zoom scale
    point_type = _PointStyle.ROUND
    point_size = 8
    scale = 1.0

    _current_vertex_fill_color: QtGui.QColor

    def __init__(
        self,
        label: str | None = None,
        line_color: QtGui.QColor | None = None,
        shape_type: str | None = None,
        flags: dict[str, bool] | None = None,
        group_id: int | None = None,
        description: str | None = None,
        mask: npt.NDArray[np.bool_] | None = None,
    ) -> None:
        self.label = label
        self.group_id = group_id
        self.points: list[QtCore.QPointF] = []
        self.point_labels = []
        self.shape_type = shape_type
        self._shape_raw = None
        self._points_raw = []
        self._shape_type_raw = None
        self.fill = False
        self.selected = False
        self.flags = dict(flags) if flags is not None else flags
        self.description = description
        self.other_data: dict = {}
        self.mask = mask

        # Highlight state: which vertex is highlighted and how it looks
        self._highlightIndex: int | None = None
        self._highlightMode: int = self.NEAR_VERTEX
        self._highlightSettings: dict[int, tuple[float, int]] = {
            self.NEAR_VERTEX: (4.0, self.P_ROUND),
            self.MOVE_VERTEX: (1.5, self.P_SQUARE),
        }

        self._closed: bool = False

        if line_color is not None:
            # Per-instance line color override (used for the pending line).
            self.line_color = line_color

    def _scale_point(self, point: QtCore.QPointF) -> QtCore.QPointF:
        return point * self.scale

    def setShapeRefined(
        self,
        shape_type: str,
        points: list[QtCore.QPointF],
        point_labels: list[int],
        mask: npt.NDArray[np.bool_] | None = None,
    ) -> None:
        self._shape_raw = (self.shape_type, self.points, self.point_labels)
        self.shape_type = shape_type
        self.points = points
        self.point_labels = point_labels
        self.mask = mask

    def restoreShapeRaw(self) -> None:
        if self._shape_raw is None:
            return
        self.shape_type, self.points, self.point_labels = self._shape_raw
        self._shape_raw = None

    @property
    def shape_type(self) -> str:
        return self._shape_type

    @shape_type.setter
    def shape_type(self, value: str | None) -> None:
        if value is None:
            value = "polygon"
        if value not in self._VALID_SHAPE_TYPES:
            raise ValueError(f"Unexpected shape_type: {value}")
        self._shape_type = value

    def close(self) -> None:
        self._closed = True

    def addPoint(self, point: QtCore.QPointF, label: int = 1) -> None:
        is_closing = len(self.points) > 0 and point == self.points[0]
        if is_closing:
            self._closed = True
            return
        self.points.append(point)
        self.point_labels.append(label)

    def canAddPoint(self) -> bool:
        return self.shape_type in {"polygon", "linestrip"}

    def popPoint(self) -> QtCore.QPointF | None:
        if len(self.points) == 0:
            return None
        if self.point_labels:
            self.point_labels.pop()
        return self.points.pop()

    def insertPoint(self, i: int, point: QtCore.QPointF, label: int = 1) -> None:
        self.points = self.points[:i] + [point] + self.points[i:]
        self.point_labels = self.point_labels[:i] + [label] + self.point_labels[i:]

    def canRemovePoint(self) -> bool:
        if not self.canAddPoint():
            return False

        if self.shape_type == "polygon" and len(self.points) <= 3:
            return False

        if self.shape_type == "linestrip" and len(self.points) <= 2:
            return False

        return True

    def removePoint(self, i: int) -> None:
        if not self.canRemovePoint():
            logger.warning(
                "Cannot remove point from: shape_type=%r, len(points)=%d",
                self.shape_type,
                len(self.points),
            )
            return

        del self.points[i]
        del self.point_labels[i]

    def isClosed(self) -> bool:
        return bool(self._closed)

    def setOpen(self) -> None:
        self._closed = False

    def paint(self, painter: QtGui.QPainter) -> None:
        if self.mask is None and not self.points:
            return

        color = self.select_line_color if self.selected else self.line_color
        pen = QtGui.QPen(color)
        # Try using integer sizes for smoother drawing(?)
        pen.setWidth(self.PEN_WIDTH)
        painter.setPen(pen)

        if self.shape_type == "mask" and self.mask is not None:
            image_to_draw = np.zeros(self.mask.shape + (4,), dtype=np.uint8)
            fill_color = (
                self.select_fill_color.getRgb()
                if self.selected
                else self.fill_color.getRgb()
            )
            image_to_draw[self.mask] = fill_color
            qimage = QtGui.QImage.fromData(labelme.utils.img_arr_to_data(image_to_draw))
            scaled_size = qimage.size() * self.scale
            qimage = qimage.scaled(
                scaled_size,
                QtCore.Qt.IgnoreAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )

            painter.drawImage(self._scale_point(point=self.points[0]), qimage)

            line_path = QtGui.QPainterPath()
            contours = skimage.measure.find_contours(np.pad(self.mask, pad_width=1))
            for contour in contours:
                contour += [self.points[0].y(), self.points[0].x()]
                first_pt = QtCore.QPointF(contour[0, 1], contour[0, 0])
                line_path.moveTo(self._scale_point(first_pt))
                for point in contour[1:]:
                    contour_pt = QtCore.QPointF(point[1], point[0])
                    line_path.lineTo(self._scale_point(contour_pt))
            painter.drawPath(line_path)

        if self.points:
            line_path = QtGui.QPainterPath()
            vrtx_path = QtGui.QPainterPath()
            negative_vrtx_path = QtGui.QPainterPath()

            if self.shape_type in ["rectangle", "mask"]:
                assert len(self.points) in [1, 2]
                if len(self.points) == 2:
                    top_left = self._scale_point(self.points[0])
                    bottom_right = self._scale_point(self.points[1])
                    line_path.addRect(QtCore.QRectF(top_left, bottom_right))
                if self.shape_type == "rectangle":
                    for i in range(len(self.points)):
                        self.drawVertex(vrtx_path, i)
            elif self.shape_type == "circle":
                assert len(self.points) in [1, 2]
                if len(self.points) == 2:
                    diff = self.points[0] - self.points[1]
                    r = labelme.utils.distance(self._scale_point(diff))
                    center = self._scale_point(self.points[0])
                    line_path.addEllipse(center, r, r)
                for idx in range(len(self.points)):
                    self.drawVertex(vrtx_path, idx)
            elif self.shape_type == "linestrip":
                first_scaled = self._scale_point(self.points[0])
                line_path.moveTo(first_scaled)
                for idx, pt in enumerate(self.points):
                    line_path.lineTo(self._scale_point(pt))
                    self.drawVertex(vrtx_path, idx)
            elif self.shape_type == "points":
                assert len(self.points) == len(self.point_labels)
                for i, point_label in enumerate(self.point_labels):
                    if point_label == 1:
                        self.drawVertex(vrtx_path, i)
                    else:
                        self.drawVertex(negative_vrtx_path, i)
            else:
                origin = self._scale_point(self.points[0])
                line_path.moveTo(origin)

                for idx, pt in enumerate(self.points):
                    line_path.lineTo(self._scale_point(pt))
                    self.drawVertex(vrtx_path, idx)
                if self._closed:
                    line_path.lineTo(origin)

            painter.drawPath(line_path)
            has_vertices = vrtx_path.length() > 0
            if has_vertices:
                painter.drawPath(vrtx_path)
                painter.fillPath(vrtx_path, self._current_vertex_fill_color)
            if self.fill and self.shape_type not in [
                "line",
                "linestrip",
                "points",
                "mask",
            ]:
                fill = self.select_fill_color if self.selected else self.fill_color
                painter.fillPath(line_path, fill)

            pen.setColor(QtGui.QColor(255, 0, 0, 255))
            painter.setPen(pen)
            painter.drawPath(negative_vrtx_path)
            painter.fillPath(negative_vrtx_path, QtGui.QColor(255, 0, 0, 255))

    def drawVertex(self, path: QtGui.QPainterPath, i: int) -> None:
        diameter = float(self.point_size)
        vertex_shape = self.point_type
        vertex_pos = self._scale_point(self.points[i])
        if i == self._highlightIndex:
            scale_factor, vertex_shape = self._highlightSettings[self._highlightMode]
            diameter = diameter * scale_factor
        self._current_vertex_fill_color = (
            self.hvertex_fill_color
            if self._highlightIndex is not None
            else self.vertex_fill_color
        )
        half = diameter / 2.0
        if vertex_shape == self.P_SQUARE:
            x0 = vertex_pos.x() - half
            y0 = vertex_pos.y() - half
            path.addRect(x0, y0, diameter, diameter)
        elif vertex_shape == self.P_ROUND:
            path.addEllipse(vertex_pos, half, half)
        else:
            raise AssertionError("unsupported vertex shape")

    def nearestVertex(self, point: QtCore.QPointF, epsilon: float) -> int | None:
        scaled_target = self._scale_point(point)
        closest_idx: int | None = None
        closest_dist = float("inf")
        for idx, pt in enumerate(self.points):
            scaled_pt = self._scale_point(pt)
            d = labelme.utils.distance(scaled_pt - scaled_target)
            if d <= epsilon and d < closest_dist:
                closest_dist = d
                closest_idx = idx
        return closest_idx

    def nearestEdge(self, point: QtCore.QPointF, epsilon: float) -> int | None:
        scaled_target = self._scale_point(point)
        closest_idx: int | None = None
        closest_dist = float("inf")
        n = len(self.points)
        for idx in range(n):
            edge_start = self._scale_point(self.points[idx - 1])
            edge_end = self._scale_point(self.points[idx])
            d = labelme.utils.distancetoline(scaled_target, (edge_start, edge_end))
            if d <= epsilon and d < closest_dist:
                closest_dist = d
                closest_idx = idx
        return closest_idx

    def containsPoint(self, point: QtCore.QPointF) -> bool:
        if self.shape_type in ["line", "linestrip", "points"]:
            return False
        if self.shape_type == "point":
            if not self.points:
                return False
            return labelme.utils.distance(point - self.points[0]) <= self.point_size / 2
        if self.mask is not None:
            raw_y = int(round(point.y() - self.points[0].y()))
            raw_x = int(round(point.x() - self.points[0].x()))
            if (
                raw_y < 0
                or raw_y >= self.mask.shape[0]
                or raw_x < 0
                or raw_x >= self.mask.shape[1]
            ):
                return False
            return bool(self.mask[raw_y, raw_x])
        geom_path = self.makePath()
        return geom_path.contains(point)

    def makePath(self) -> QtGui.QPainterPath:
        path = QtGui.QPainterPath()
        if self.shape_type in ["rectangle", "mask"]:
            if len(self.points) == 2:
                rect = QtCore.QRectF(self.points[0], self.points[1])
                path.addRect(rect)
        elif self.shape_type == "circle":
            if len(self.points) == 2:
                r = labelme.utils.distance(self.points[0] - self.points[1])
                path.addEllipse(self.points[0], r, r)
        else:
            path.moveTo(self.points[0])
            for pt in self.points[1:]:
                path.lineTo(pt)
        return path

    def boundingRect(self) -> QtCore.QRectF:
        return self.makePath().boundingRect()

    def moveBy(self, offset: QtCore.QPointF) -> None:
        self.points = [pt + offset for pt in self.points]

    def moveVertex(self, i: int, pos: QtCore.QPointF) -> None:
        self.points[i] = pos

    def highlightVertex(self, i: int, action: int) -> None:
        self._highlightIndex = i
        self._highlightMode = action

    def highlightClear(self) -> None:
        self._highlightIndex = None

    def copy(self) -> Shape:
        return copy.deepcopy(self)

    def __len__(self) -> int:
        return len(self.points)

    def __getitem__(self, key: int) -> QtCore.QPointF:
        return self.points[key]

    def __setitem__(self, key: int, value: QtCore.QPointF) -> None:
        self.points[key] = value
