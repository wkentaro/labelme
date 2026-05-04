from __future__ import annotations

import copy
from collections.abc import Iterable
from typing import Any
from typing import Final
from typing import NamedTuple
from typing import Protocol

import numpy as np
import numpy.typing as npt
import skimage.measure
from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui

import labelme.utils

_P_SQUARE: Final[int] = 0
_P_ROUND: Final[int] = 1


class _Highlight(NamedTuple):
    index: int
    mode: int


class Shape:
    MOVE_VERTEX: Final[int] = 0
    NEAR_VERTEX: Final[int] = 1

    PEN_WIDTH: Final[int] = 2

    line_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 128)
    fill_color: QtGui.QColor = QtGui.QColor(0, 0, 0, 64)
    vertex_fill_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 255)
    select_line_color: QtGui.QColor = QtGui.QColor(255, 255, 255, 255)
    select_fill_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 64)
    hvertex_fill_color: QtGui.QColor = QtGui.QColor(255, 255, 255, 255)

    point_type: int = _P_ROUND
    point_size: int = 8
    scale: float = 1.0

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
        self.fill = False
        self.selected = False
        self.visible = True
        self.flags = flags
        self.description = description
        self.other_data: dict[str, Any] = {}
        self.mask = mask
        self._closed = False
        self.highlight: _Highlight | None = None

        if line_color is not None:
            # Per-instance line color override (used for the pending line).
            self.line_color = line_color

    def refine(
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

    def unrefine(self) -> None:
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

    def close(self) -> None:
        self._closed = True

    def add_point(self, point: QtCore.QPointF, label: int = 1) -> None:
        if self.points and self.points[0] == point:
            self.close()
            return
        self.points.append(point)
        self.point_labels.append(label)

    def can_add_point(self) -> bool:
        return self.shape_type in ["polygon", "linestrip"]

    def pop_point(self) -> QtCore.QPointF | None:
        if not self.points:
            return None
        if self.point_labels:
            self.point_labels.pop()
        return self.points.pop()

    def insert_point(self, i: int, point: QtCore.QPointF, label: int = 1) -> None:
        self.points.insert(i, point)
        self.point_labels.insert(i, label)

    def can_remove_point(self) -> bool:
        if not self.can_add_point():
            return False

        if self.shape_type == "polygon" and len(self.points) <= 3:
            return False

        if self.shape_type == "linestrip" and len(self.points) <= 2:
            return False

        return True

    def remove_point(self, i: int) -> None:
        if not self.can_remove_point():
            logger.warning(
                "Cannot remove point from: shape_type=%r, len(points)=%d",
                self.shape_type,
                len(self.points),
            )
            return

        self.points.pop(i)
        self.point_labels.pop(i)

    def is_closed(self) -> bool:
        return self._closed

    def open(self) -> None:
        self._closed = False

    def paint(self, painter: QtGui.QPainter) -> None:
        _paint_shape(painter=painter, shape=self)

    def nearest_vertex(self, point: QtCore.QPointF, epsilon: float) -> int | None:
        return _nearest_vertex_index(
            point=point, points=self.points, scale=self.scale, epsilon=epsilon
        )

    def nearest_edge(self, point: QtCore.QPointF, epsilon: float) -> int | None:
        return _nearest_edge_index(
            point=point, points=self.points, scale=self.scale, epsilon=epsilon
        )

    def contains_point(self, point: QtCore.QPointF) -> bool:
        return _shape_contains_point(
            point=point,
            shape_type=self.shape_type,
            points=self.points,
            mask=self.mask,
            point_size=self.point_size,
        )

    def bounds(self) -> QtCore.QRectF:
        path = _make_shape_path(shape_type=self.shape_type, points=self.points)
        return path.boundingRect()

    def move_vertex(self, i: int, pos: QtCore.QPointF) -> None:
        self.points[i] = pos

    def translate(self, offset: QtCore.QPointF) -> None:
        for i, point in enumerate(self.points):
            self.points[i] = point + offset

    def highlight_vertex(self, i: int, action: int) -> None:
        self.highlight = _Highlight(index=i, mode=action)

    def clear_highlight(self) -> None:
        self.highlight = None

    def copy(self) -> Shape:
        return copy.deepcopy(self)

    def __len__(self) -> int:
        return len(self.points)

    def __getitem__(self, key: int) -> QtCore.QPointF:
        return self.points[key]

    def __setitem__(self, key: int, value: QtCore.QPointF) -> None:
        self.points[key] = value


_HIGHLIGHT_STYLES: Final[dict[int, tuple[float, int]]] = {
    Shape.NEAR_VERTEX: (4.0, _P_ROUND),
    Shape.MOVE_VERTEX: (1.5, _P_SQUARE),
}


def _scale_point(*, point: QtCore.QPointF, scale: float) -> QtCore.QPointF:
    return QtCore.QPointF(point.x() * scale, point.y() * scale)


def _build_rectangle_path(*, points: list[QtCore.QPointF]) -> QtGui.QPainterPath:
    out = QtGui.QPainterPath()
    if len(points) == 2:
        out.addRect(QtCore.QRectF(points[0], points[1]))
    return out


def _build_circle_path(*, points: list[QtCore.QPointF]) -> QtGui.QPainterPath:
    out = QtGui.QPainterPath()
    if len(points) == 2:
        radius = labelme.utils.distance(points[0] - points[1])
        out.addEllipse(points[0], radius, radius)
    return out


def _build_polyline_path(*, points: list[QtCore.QPointF]) -> QtGui.QPainterPath:
    out = QtGui.QPainterPath()
    if not points:
        return out
    out.moveTo(points[0])
    for vertex in points[1:]:
        out.lineTo(vertex)
    return out


class _PathBuilder(Protocol):
    def __call__(self, *, points: list[QtCore.QPointF]) -> QtGui.QPainterPath: ...


_PATH_BUILDERS: Final[dict[str, _PathBuilder]] = {
    "rectangle": _build_rectangle_path,
    "mask": _build_rectangle_path,
    "circle": _build_circle_path,
}


def _make_shape_path(
    *, shape_type: str, points: list[QtCore.QPointF]
) -> QtGui.QPainterPath:
    builder = _PATH_BUILDERS.get(shape_type, _build_polyline_path)
    return builder(points=points)


def _argmin(values: Iterable[float]) -> tuple[int, float] | None:
    return min(enumerate(values), key=lambda item: item[1], default=None)


def _nearest_vertex_index(
    *,
    point: QtCore.QPointF,
    points: list[QtCore.QPointF],
    scale: float,
    epsilon: float,
) -> int | None:
    scaled_point = _scale_point(point=point, scale=scale)
    nearest = _argmin(
        labelme.utils.distance(_scale_point(point=p, scale=scale) - scaled_point)
        for p in points
    )
    if nearest is None or nearest[1] > epsilon:
        return None
    return nearest[0]


def _nearest_edge_index(
    *,
    point: QtCore.QPointF,
    points: list[QtCore.QPointF],
    scale: float,
    epsilon: float,
) -> int | None:
    scaled_point = _scale_point(point=point, scale=scale)
    scaled_points = [_scale_point(point=p, scale=scale) for p in points]
    nearest = _argmin(
        labelme.utils.distance_to_line(
            scaled_point, (scaled_points[i - 1], scaled_points[i])
        )
        for i in range(len(points))
    )
    if nearest is None or nearest[1] > epsilon:
        return None
    return nearest[0]


def _shape_contains_point(
    *,
    point: QtCore.QPointF,
    shape_type: str,
    points: list[QtCore.QPointF],
    mask: npt.NDArray[np.bool_] | None,
    point_size: int,
) -> bool:
    if shape_type in ["line", "linestrip", "points"]:
        return False
    if shape_type == "point":
        if not points:
            return False
        return labelme.utils.distance(point - points[0]) <= point_size / 2
    if mask is not None:
        raw_y = int(round(point.y() - points[0].y()))
        raw_x = int(round(point.x() - points[0].x()))
        if raw_y < 0 or raw_y >= mask.shape[0] or raw_x < 0 or raw_x >= mask.shape[1]:
            return False
        return bool(mask[raw_y, raw_x])
    return _make_shape_path(shape_type=shape_type, points=points).contains(point)


def _mask_contour_path(
    *,
    mask: npt.NDArray[np.bool_],
    origin: QtCore.QPointF,
    scale: float,
) -> QtGui.QPainterPath:
    contours = skimage.measure.find_contours(np.pad(mask, pad_width=1))
    output = QtGui.QPainterPath()
    for contour in contours:
        contour = contour + [origin.y(), origin.x()]
        output.moveTo(
            _scale_point(
                point=QtCore.QPointF(contour[0, 1], contour[0, 0]), scale=scale
            )
        )
        for point in contour[1:]:
            output.lineTo(
                _scale_point(point=QtCore.QPointF(point[1], point[0]), scale=scale)
            )
    return output


def _vertex_size_and_type(
    *,
    base_size: int,
    base_type: int,
    highlight: _Highlight | None,
    vertex_index: int,
) -> tuple[float, int]:
    if highlight is not None and highlight.index == vertex_index:
        size_factor, point_type = _HIGHLIGHT_STYLES[highlight.mode]
        return base_size * size_factor, point_type
    return base_size, base_type


def _add_vertex_to_path(
    path: QtGui.QPainterPath,
    *,
    pos: QtCore.QPointF,
    size: float,
    point_type: int,
) -> None:
    half = size / 2.0
    if point_type == _P_SQUARE:
        path.addRect(pos.x() - half, pos.y() - half, size, size)
    elif point_type == _P_ROUND:
        path.addEllipse(pos, half, half)
    else:
        raise ValueError(f"Unsupported vertex shape: {point_type}")


def _add_shape_vertex(
    path: QtGui.QPainterPath, *, shape: Shape, vertex_index: int
) -> None:
    size, point_type = _vertex_size_and_type(
        base_size=shape.point_size,
        base_type=shape.point_type,
        highlight=shape.highlight,
        vertex_index=vertex_index,
    )
    pos = _scale_point(point=shape.points[vertex_index], scale=shape.scale)
    _add_vertex_to_path(path, pos=pos, size=size, point_type=point_type)


def _paint_shape(*, painter: QtGui.QPainter, shape: Shape) -> None:
    if shape.mask is None and not shape.points:
        return

    color = shape.select_line_color if shape.selected else shape.line_color
    pen = QtGui.QPen(color)
    pen.setWidth(shape.PEN_WIDTH)
    painter.setPen(pen)

    if shape.shape_type == "mask" and shape.mask is not None:
        _paint_mask(painter=painter, shape=shape)

    if shape.points:
        _paint_points(painter=painter, shape=shape)


def _paint_mask(*, painter: QtGui.QPainter, shape: Shape) -> None:
    assert shape.mask is not None
    fill = shape.select_fill_color if shape.selected else shape.fill_color
    image_to_draw = np.zeros(shape.mask.shape + (4,), dtype=np.uint8)
    image_to_draw[shape.mask] = fill.getRgb()
    qimage = QtGui.QImage.fromData(labelme.utils.img_arr_to_data(image_to_draw))
    origin = shape.points[0]
    target_top_left = _scale_point(point=origin, scale=shape.scale)
    target_rect = QtCore.QRectF(
        target_top_left.x(),
        target_top_left.y(),
        qimage.width() * shape.scale,
        qimage.height() * shape.scale,
    )
    painter.drawImage(target_rect, qimage)
    painter.drawPath(
        _mask_contour_path(mask=shape.mask, origin=origin, scale=shape.scale)
    )


def _paint_points(*, painter: QtGui.QPainter, shape: Shape) -> None:
    line_path = QtGui.QPainterPath()
    vrtx_path = QtGui.QPainterPath()
    negative_vrtx_path = QtGui.QPainterPath()

    _build_shape_paths(
        shape=shape,
        line_path=line_path,
        vrtx_path=vrtx_path,
        negative_vrtx_path=negative_vrtx_path,
    )

    painter.drawPath(line_path)
    if vrtx_path.length() > 0:
        vertex_fill = (
            shape.hvertex_fill_color
            if shape.highlight is not None
            else shape.vertex_fill_color
        )
        painter.drawPath(vrtx_path)
        painter.fillPath(vrtx_path, vertex_fill)
    if shape.fill and shape.shape_type not in ["line", "linestrip", "points", "mask"]:
        fill = shape.select_fill_color if shape.selected else shape.fill_color
        painter.fillPath(line_path, fill)

    neg_color = QtGui.QColor(255, 0, 0, 255)
    neg_pen = QtGui.QPen(neg_color)
    neg_pen.setWidth(shape.PEN_WIDTH)
    painter.setPen(neg_pen)
    painter.drawPath(negative_vrtx_path)
    painter.fillPath(negative_vrtx_path, neg_color)


def _build_shape_paths(
    *,
    shape: Shape,
    line_path: QtGui.QPainterPath,
    vrtx_path: QtGui.QPainterPath,
    negative_vrtx_path: QtGui.QPainterPath,
) -> None:
    if shape.shape_type in ["rectangle", "mask"]:
        assert len(shape.points) in [1, 2]
        if len(shape.points) == 2:
            line_path.addRect(
                QtCore.QRectF(
                    _scale_point(point=shape.points[0], scale=shape.scale),
                    _scale_point(point=shape.points[1], scale=shape.scale),
                )
            )
        if shape.shape_type == "rectangle":
            for i in range(len(shape.points)):
                _add_shape_vertex(vrtx_path, shape=shape, vertex_index=i)
    elif shape.shape_type == "circle":
        assert len(shape.points) in [1, 2]
        if len(shape.points) == 2:
            radius = labelme.utils.distance(
                _scale_point(point=shape.points[0] - shape.points[1], scale=shape.scale)
            )
            line_path.addEllipse(
                _scale_point(point=shape.points[0], scale=shape.scale), radius, radius
            )
        for i in range(len(shape.points)):
            _add_shape_vertex(vrtx_path, shape=shape, vertex_index=i)
    elif shape.shape_type == "linestrip":
        line_path.moveTo(_scale_point(point=shape.points[0], scale=shape.scale))
        for i, p in enumerate(shape.points):
            line_path.lineTo(_scale_point(point=p, scale=shape.scale))
            _add_shape_vertex(vrtx_path, shape=shape, vertex_index=i)
    elif shape.shape_type == "points":
        assert len(shape.points) == len(shape.point_labels)
        for i, point_label in enumerate(shape.point_labels):
            target = vrtx_path if point_label == 1 else negative_vrtx_path
            _add_shape_vertex(target, shape=shape, vertex_index=i)
    else:
        line_path.moveTo(_scale_point(point=shape.points[0], scale=shape.scale))
        for i, p in enumerate(shape.points):
            line_path.lineTo(_scale_point(point=p, scale=shape.scale))
            _add_shape_vertex(vrtx_path, shape=shape, vertex_index=i)
        if shape.is_closed():
            line_path.lineTo(_scale_point(point=shape.points[0], scale=shape.scale))
