from __future__ import annotations

import copy

import numpy as np
import numpy.typing as npt
import skimage.measure
from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui

import labelme.utils


class Shape:
    # Vertex handle drawing styles
    P_SQUARE = 0
    P_ROUND = 1

    # Vertex highlight modes
    MOVE_VERTEX = 0
    NEAR_VERTEX = 1

    # Outline stroke width
    PEN_WIDTH = 2

    # The following class variables influence the drawing of all shape objects.
    line_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 128)
    fill_color: QtGui.QColor = QtGui.QColor(0, 0, 0, 64)
    vertex_fill_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 255)
    select_line_color: QtGui.QColor = QtGui.QColor(255, 255, 255, 255)
    select_fill_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 64)
    hvertex_fill_color: QtGui.QColor = QtGui.QColor(255, 255, 255, 255)

    # Default handle style, size, and zoom scale
    point_type = P_ROUND
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
        self.point_labels: list[int] = []
        self.shape_type = shape_type
        self._shape_raw = None
        self._points_raw: list[QtCore.QPointF] = []
        self._shape_type_raw = None
        self.selected = False
        self.fill = False
        self.description = description
        self.flags = flags
        self.mask = mask
        self.other_data: dict = {}

        self._closed = False

        # Highlight state: which vertex is highlighted and how it appears
        self._highlightIndex: int | None = None
        self._highlightMode: int = self.NEAR_VERTEX
        self._highlightSettings: dict[int, tuple[float, int]] = {
            self.NEAR_VERTEX: (4, self.P_ROUND),
            self.MOVE_VERTEX: (1.5, self.P_SQUARE),
        }

        if line_color is not None:
            # Override instance line color (e.g. for the pending guide line)
            self.line_color = line_color

    def _scale_point(self, point: QtCore.QPointF) -> QtCore.QPointF:
        s = self.scale
        return QtCore.QPointF(point.x() * s, point.y() * s)

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

    _VALID_SHAPE_TYPES = frozenset(
        [
            "polygon", "rectangle", "point", "line",
            "circle", "linestrip", "points", "mask",
        ]
    )

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
        if self.points and self.points[0] == point:
            self.close()
            return
        self.points.append(point)
        self.point_labels.append(label)

    def canAddPoint(self) -> bool:
        return self.shape_type in ("polygon", "linestrip")

    def popPoint(self) -> QtCore.QPointF | None:
        if not self.points:
            return None
        if self.point_labels:
            self.point_labels.pop()
        return self.points.pop()

    def insertPoint(self, i: int, point: QtCore.QPointF, label: int = 1) -> None:
        self.points.insert(i, point)
        self.point_labels.insert(i, label)

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
        self.points.pop(i)
        self.point_labels.pop(i)

    def isClosed(self) -> bool:
        return self._closed

    def setOpen(self) -> None:
        self._closed = False

    def paint(self, painter: QtGui.QPainter) -> None:
        if self.mask is None and not self.points:
            return

        color = self.select_line_color if self.selected else self.line_color
        pen = QtGui.QPen(color)
        # Try using integer sizes for smoother drawing(?)
        pen.setWidth(max(1, self.PEN_WIDTH))
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
                for c_pt in contour[1:]:
                    line_path.lineTo(
                        self._scale_point(QtCore.QPointF(c_pt[1], c_pt[0]))
                    )
            painter.drawPath(line_path)

        if self.points:
            line_path = QtGui.QPainterPath()
            vrtx_path = QtGui.QPainterPath()
            negative_vrtx_path = QtGui.QPainterPath()

            if self.shape_type in ("rectangle", "mask"):
                assert len(self.points) in (1, 2)
                if len(self.points) == 2:
                    rect = QtCore.QRectF(
                        self._scale_point(self.points[0]),
                        self._scale_point(self.points[1]),
                    )
                    line_path.addRect(rect)
                if self.shape_type == "rectangle":
                    for idx in range(len(self.points)):
                        self.drawVertex(vrtx_path, idx)
            elif self.shape_type == "circle":
                assert len(self.points) in (1, 2)
                if len(self.points) == 2:
                    circle_radius = labelme.utils.distance(
                        self._scale_point(self.points[0] - self.points[1])
                    )
                    center_scaled = self._scale_point(self.points[0])
                    line_path.addEllipse(center_scaled, circle_radius, circle_radius)
                for idx in range(len(self.points)):
                    self.drawVertex(vrtx_path, idx)
            elif self.shape_type == "linestrip":
                line_path.moveTo(self._scale_point(self.points[0]))
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
            if not vrtx_path.isEmpty():
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

    def drawVertex(self, path: QtGui.QPainterPath, i: int) -> None:
        handle_size = self.point_size
        handle_style = self.point_type
        vertex = self._scale_point(self.points[i])
        if i == self._highlightIndex:
            scale_factor, handle_style = self._highlightSettings[self._highlightMode]
            handle_size = handle_size * scale_factor
        self._current_vertex_fill_color = (
            self.hvertex_fill_color
            if self._highlightIndex is not None
            else self.vertex_fill_color
        )
        half = handle_size / 2.0
        if handle_style == self.P_SQUARE:
            path.addRect(vertex.x() - half, vertex.y() - half, handle_size, handle_size)
        elif handle_style == self.P_ROUND:
            path.addEllipse(vertex, half, half)
        else:
            raise ValueError(f"unsupported vertex shape: {handle_style}")

    def nearestVertex(self, point: QtCore.QPointF, epsilon: float) -> int | None:
        closest_dist = float("inf")
        closest_idx: int | None = None
        scaled_pt = self._scale_point(point)
        for idx, vertex in enumerate(self.points):
            scaled_v = self._scale_point(vertex)
            d = labelme.utils.distance(scaled_v - scaled_pt)
            if d <= epsilon and d < closest_dist:
                closest_dist = d
                closest_idx = idx
        return closest_idx

    def nearestEdge(self, point: QtCore.QPointF, epsilon: float) -> int | None:
        closest_dist = float("inf")
        closest_edge: int | None = None
        scaled_pt = self._scale_point(point)
        for idx in range(len(self.points)):
            seg_start = self._scale_point(self.points[idx - 1])
            seg_end = self._scale_point(self.points[idx])
            d = labelme.utils.distancetoline(scaled_pt, (seg_start, seg_end))
            if d <= epsilon and d < closest_dist:
                closest_dist = d
                closest_edge = idx
        return closest_edge

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
        return self.makePath().contains(point)

    def makePath(self) -> QtGui.QPainterPath:
        if self.shape_type in ("rectangle", "mask"):
            path = QtGui.QPainterPath()
            if len(self.points) == 2:
                rect = QtCore.QRectF(self.points[0], self.points[1])
                path.addRect(rect)
        elif self.shape_type == "circle":
            path = QtGui.QPainterPath()
            if len(self.points) == 2:
                r = labelme.utils.distance(self.points[0] - self.points[1])
                path.addEllipse(self.points[0], r, r)
        else:
            path = QtGui.QPainterPath(self.points[0])
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
