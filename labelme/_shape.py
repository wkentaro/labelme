from __future__ import annotations

import copy
import dataclasses
import typing
from collections.abc import Iterable
from typing import Any
from typing import Final
from typing import Literal
from typing import TypeAlias
from typing import cast

import numpy as np
import numpy.typing as npt
import skimage.measure
from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui

from . import utils

ShapeType: TypeAlias = Literal[
    "polygon",
    "rectangle",
    "oriented_rectangle",
    "point",
    "line",
    "circle",
    "linestrip",
    "points",
    "mask",
]

POLYLINE_SHAPE_TYPES: Final[tuple[ShapeType, ...]] = ("polygon", "linestrip")


@dataclasses.dataclass(frozen=True)
class _VertexHighlight:
    index: int
    mode: Literal["move", "near"]

    @property
    def size_factor(self) -> float:
        return {
            "move": 1.5,
            "near": 4.0,
        }[self.mode]

    @property
    def point_type(self) -> Literal["square", "round"]:
        match self.mode:
            case "move":
                return "square"
            case "near":
                return "round"
            case _:
                typing.assert_never(self.mode)


class Shape:
    PEN_WIDTH: Final[int] = 2

    line_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 128)
    fill_color: QtGui.QColor = QtGui.QColor(0, 0, 0, 64)
    vertex_fill_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 255)
    select_line_color: QtGui.QColor = QtGui.QColor(255, 255, 255, 255)
    select_fill_color: QtGui.QColor = QtGui.QColor(0, 255, 0, 64)
    hvertex_fill_color: QtGui.QColor = QtGui.QColor(255, 255, 255, 255)

    point_type: Literal["square", "round"] = "round"
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
        if shape_type is None:
            shape_type = "polygon"
        if shape_type not in typing.get_args(ShapeType):
            raise ValueError(f"Unexpected shape_type: {shape_type}")
        self._shape_type = cast(ShapeType, shape_type)
        self.fill = False
        self.selected = False
        self.visible = True
        self.flags = flags
        self.description = description
        self.other_data: dict[str, Any] = {}
        self.mask = mask
        self._closed = False
        self.highlight: _VertexHighlight | None = None
        self.rotation_highlight: _VertexHighlight | None = None

        if line_color is not None:
            # Per-instance line color override (used for the pending line).
            self.line_color = line_color

    @property
    def shape_type(self) -> ShapeType:
        return self._shape_type

    def close(self) -> None:
        self._closed = True

    def add_point(
        self, point: QtCore.QPointF, label: int = 1, *, autoclose: bool = False
    ) -> None:
        if autoclose and self.points and self.points[0] == point:
            self.close()
            return
        self.points.append(point)
        self.point_labels.append(label)

    def can_add_point(self) -> bool:
        return self.shape_type in POLYLINE_SHAPE_TYPES

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

    def move_vertex(self, i: int, pos: QtCore.QPointF) -> None:
        self.points[i] = pos

    def translate(self, offset: QtCore.QPointF) -> None:
        for i, point in enumerate(self.points):
            self.points[i] = point + offset

    def highlight_vertex(self, index: int, mode: Literal["move", "near"]) -> None:
        self.highlight = _VertexHighlight(index=index, mode=mode)
        self.rotation_highlight = None

    def highlight_rotation_point(
        self, index: int, mode: Literal["move", "near"]
    ) -> None:
        self.rotation_highlight = _VertexHighlight(index=index, mode=mode)
        self.highlight = None

    def clear_highlight(self) -> None:
        self.highlight = None
        self.rotation_highlight = None

    def copy(self) -> Shape:
        return copy.deepcopy(self)


def _argmin(values: Iterable[float]) -> tuple[int, float] | None:
    return min(enumerate(values), key=lambda item: item[1], default=None)


def nearest_vertex_index(
    *,
    shape: Shape,
    point: QtCore.QPointF,
    epsilon: float,
) -> int | None:
    if shape.shape_type == "mask":
        return None
    scaled_point = point * shape.scale
    nearest = _argmin(
        utils.distance(p * shape.scale - scaled_point) for p in shape.points
    )
    if nearest is None or nearest[1] > epsilon:
        return None
    return nearest[0]


def nearest_edge_index(
    *,
    shape: Shape,
    point: QtCore.QPointF,
    epsilon: float,
) -> int | None:
    scaled_point = point * shape.scale
    scaled_points = [p * shape.scale for p in shape.points]
    nearest = _argmin(
        utils.distance_to_line(scaled_point, (scaled_points[i - 1], scaled_points[i]))
        for i in range(len(shape.points))
    )
    if nearest is None or nearest[1] > epsilon:
        return None
    return nearest[0]


def nearest_rotation_point_index(
    *,
    shape: Shape,
    point: QtCore.QPointF,
    epsilon: float,
) -> int | None:
    if shape.shape_type != "oriented_rectangle" or len(shape.points) != 4:
        return None
    scaled_point = point * shape.scale
    nearest = _argmin(
        utils.distance(
            get_rotation_handle(shape=shape, index=i) * shape.scale - scaled_point
        )
        for i in range(len(shape.points))
    )
    if nearest is None or nearest[1] > epsilon:
        return None
    return nearest[0]


def get_rotation_handle(*, shape: Shape, index: int) -> QtCore.QPointF:
    if shape.shape_type != "oriented_rectangle" or len(shape.points) != 4:
        raise ValueError(
            "Rotation handles are only defined for 4-point oriented rectangles, "
            f"got shape_type={shape.shape_type!r}, len(points)={len(shape.points)}"
        )
    return (shape.points[index] + shape.points[index - 1]) / 2


def oriented_rectangle_center(*, shape: Shape) -> QtCore.QPointF:
    if shape.shape_type != "oriented_rectangle":
        raise ValueError(
            f"Center is only defined for oriented rectangles, got {shape.shape_type!r}"
        )
    if len(shape.points) != 4:
        raise ValueError(
            f"Oriented rectangle center requires 4 points, got {len(shape.points)}"
        )
    return (shape.points[0] + shape.points[2]) / 2


def rotate(
    *,
    shape: Shape,
    center: QtCore.QPointF,
    angle: float,
    source_points: list[QtCore.QPointF] | None = None,
) -> None:
    if shape.shape_type != "oriented_rectangle":
        raise ValueError(
            "Shape rotation is only supported for oriented rectangles, "
            f"got {shape.shape_type!r}"
        )
    points = source_points if source_points is not None else list(shape.points)
    if len(points) != 4 or len(shape.points) != 4:
        raise ValueError(
            "Shape rotation requires 4 points, got "
            f"len(source_points)={len(points)}, len(shape.points)={len(shape.points)}"
        )
    cx, cy = center.x(), center.y()
    for i, p in enumerate(points):
        rotated = _rotate_point_around_origin(
            point=np.array([p.x() - cx, p.y() - cy]), angle=angle
        )
        shape.move_vertex(
            i=i,
            pos=QtCore.QPointF(float(rotated[0] + cx), float(rotated[1] + cy)),
        )


def _rotate_point_around_origin(
    *,
    point: npt.NDArray[np.floating],
    angle: float,
) -> npt.NDArray[np.floating]:
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)
    rotation = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    return rotation @ point


def is_hit_by_point(*, shape: Shape, point: QtCore.QPointF, epsilon: float) -> bool:
    if shape.shape_type in ("line", "linestrip"):
        return nearest_edge_index(shape=shape, point=point, epsilon=epsilon) is not None
    if shape.shape_type == "points":
        return False
    if shape.shape_type == "point":
        if not shape.points:
            return False
        return utils.distance(point - shape.points[0]) <= shape.point_size / 2
    if shape.mask is not None:
        raw_y = int(round(point.y() - shape.points[0].y()))
        raw_x = int(round(point.x() - shape.points[0].x()))
        if (
            raw_y < 0
            or raw_y >= shape.mask.shape[0]
            or raw_x < 0
            or raw_x >= shape.mask.shape[1]
        ):
            return False
        return bool(shape.mask[raw_y, raw_x])
    return _build_path(shape=shape).contains(point)


def bounds(*, shape: Shape) -> QtCore.QRectF:
    return _build_path(shape=shape).boundingRect()


def _build_path_rectangle(*, points: list[QtCore.QPointF]) -> QtGui.QPainterPath:
    out = QtGui.QPainterPath()
    if len(points) == 2:
        out.addRect(QtCore.QRectF(points[0], points[1]))
    return out


def _build_path_circle(*, points: list[QtCore.QPointF]) -> QtGui.QPainterPath:
    out = QtGui.QPainterPath()
    if len(points) == 2:
        radius = utils.distance(points[0] - points[1])
        out.addEllipse(points[0], radius, radius)
    return out


def _build_path_polyline(*, points: list[QtCore.QPointF]) -> QtGui.QPainterPath:
    out = QtGui.QPainterPath()
    if not points:
        return out
    out.moveTo(points[0])
    for vertex in points[1:]:
        out.lineTo(vertex)
    return out


def _build_path_oriented_rectangle(
    *, points: list[QtCore.QPointF]
) -> QtGui.QPainterPath:
    out = QtGui.QPainterPath()
    if len(points) != 4:
        return out
    out.moveTo(points[0])
    for vertex in points[1:]:
        out.lineTo(vertex)
    out.lineTo(points[0])
    return out


def _build_path(*, shape: Shape) -> QtGui.QPainterPath:
    build_path_fn = {
        "rectangle": _build_path_rectangle,
        "mask": _build_path_rectangle,
        "circle": _build_path_circle,
        "oriented_rectangle": _build_path_oriented_rectangle,
    }.get(shape.shape_type, _build_path_polyline)
    return build_path_fn(points=shape.points)


def paint(*, shape: Shape, painter: QtGui.QPainter) -> None:
    if shape.mask is None and not shape.points:
        return

    color = shape.select_line_color if shape.selected else shape.line_color
    pen = QtGui.QPen(color)
    pen.setWidth(shape.PEN_WIDTH)
    painter.setPen(pen)

    if shape.shape_type == "mask" and shape.mask is not None:
        _paint_shape_mask(painter=painter, shape=shape)

    if shape.points:
        _paint_shape_points(painter=painter, shape=shape)


def _paint_shape_mask(*, painter: QtGui.QPainter, shape: Shape) -> None:
    assert shape.mask is not None
    fill = shape.select_fill_color if shape.selected else shape.fill_color
    image_to_draw = np.zeros(shape.mask.shape + (4,), dtype=np.uint8)
    image_to_draw[shape.mask] = fill.getRgb()
    qimage = QtGui.QImage.fromData(utils.img_arr_to_data(image_to_draw))
    origin = shape.points[0]
    target_top_left = origin * shape.scale
    target_rect = QtCore.QRectF(
        target_top_left.x(),
        target_top_left.y(),
        qimage.width() * shape.scale,
        qimage.height() * shape.scale,
    )
    painter.drawImage(target_rect, qimage)

    path = QtGui.QPainterPath()
    _build_shape_mask_contour_path(
        path=path, mask=shape.mask, origin=origin, scale=shape.scale
    )
    painter.drawPath(path)


def _paint_shape_points(*, painter: QtGui.QPainter, shape: Shape) -> None:
    path_line = QtGui.QPainterPath()
    path_vertices = QtGui.QPainterPath()
    path_negative_vertices = QtGui.QPainterPath()
    path_rotation_vertices = QtGui.QPainterPath()
    path_orientation_arrow = QtGui.QPainterPath()

    _build_shape_points_paths(
        shape=shape,
        path_line=path_line,
        path_vertices=path_vertices,
        path_negative_vertices=path_negative_vertices,
        path_rotation_vertices=path_rotation_vertices,
        path_orientation_arrow=path_orientation_arrow,
    )

    painter.drawPath(path_line)
    if path_vertices.length() > 0:
        vertex_fill = (
            shape.vertex_fill_color
            if shape.highlight is None
            else shape.hvertex_fill_color
        )
        painter.drawPath(path_vertices)
        painter.fillPath(path_vertices, vertex_fill)
    if path_rotation_vertices.length() > 0:
        rotation_fill = (
            shape.vertex_fill_color
            if shape.rotation_highlight is None
            else shape.hvertex_fill_color
        )
        painter.drawPath(path_rotation_vertices)
        painter.fillPath(path_rotation_vertices, rotation_fill)
    if shape.fill and shape.shape_type not in ["line", "linestrip", "points", "mask"]:
        fill = shape.select_fill_color if shape.selected else shape.fill_color
        painter.fillPath(path_line, fill)
    if path_orientation_arrow.length() > 0:
        arrow_pen = QtGui.QPen(shape.vertex_fill_color)
        arrow_pen.setWidth(shape.PEN_WIDTH)
        painter.setPen(arrow_pen)
        painter.drawPath(path_orientation_arrow)

    neg_color = QtGui.QColor(255, 0, 0, 255)
    neg_pen = QtGui.QPen(neg_color)
    neg_pen.setWidth(shape.PEN_WIDTH)
    painter.setPen(neg_pen)
    painter.drawPath(path_negative_vertices)
    painter.fillPath(path_negative_vertices, neg_color)


def _build_shape_mask_contour_path(
    *,
    path: QtGui.QPainterPath,
    mask: npt.NDArray[np.bool_],
    origin: QtCore.QPointF,
    scale: float,
) -> None:
    contours = skimage.measure.find_contours(np.pad(mask, pad_width=1))
    for contour in contours:
        contour = contour + [origin.y(), origin.x()]
        path.moveTo(QtCore.QPointF(contour[0, 1], contour[0, 0]) * scale)
        for point in contour[1:]:
            path.lineTo(QtCore.QPointF(point[1], point[0]) * scale)


def _build_shape_point_path(
    *, path: QtGui.QPainterPath, shape: Shape, vertex_index: int
) -> None:
    highlight = shape.highlight
    if highlight is not None and highlight.index == vertex_index:
        size = shape.point_size * highlight.size_factor
        point_type = highlight.point_type
    else:
        size = shape.point_size
        point_type = shape.point_type

    pos = shape.points[vertex_index] * shape.scale

    _draw_vertex(path=path, pos=pos, size=size, point_type=point_type)


def _build_shape_rotation_point_path(
    *, path: QtGui.QPainterPath, shape: Shape, vertex_index: int
) -> None:
    highlight = shape.rotation_highlight
    if highlight is not None and highlight.index == vertex_index:
        size = shape.point_size * highlight.size_factor
        point_type = highlight.point_type
    else:
        size = shape.point_size
        point_type = shape.point_type

    pos = get_rotation_handle(shape=shape, index=vertex_index) * shape.scale

    _draw_vertex(path=path, pos=pos, size=size, point_type=point_type)


def _draw_vertex(
    *,
    path: QtGui.QPainterPath,
    pos: QtCore.QPointF,
    size: float,
    point_type: Literal["square", "round"],
) -> None:
    half = size / 2.0
    if point_type == "square":
        path.addRect(pos.x() - half, pos.y() - half, size, size)
    elif point_type == "round":
        path.addEllipse(pos, half, half)
    else:
        raise ValueError(f"Unsupported vertex shape: {point_type}")


def _build_shape_oriented_rectangle_arrow_path(
    *, path: QtGui.QPainterPath, shape: Shape
) -> None:
    ARROW_HALF_LENGTH: Final[float] = 5.0
    ARROW_HEAD_BACK_OFFSET: Final[float] = 0.22
    local_points = [
        np.array([ARROW_HEAD_BACK_OFFSET, -0.5]) * ARROW_HALF_LENGTH,
        np.array([1.0, 0.0]) * ARROW_HALF_LENGTH,
        np.array([ARROW_HEAD_BACK_OFFSET, 0.5]) * ARROW_HALF_LENGTH,
        np.array([-1.0, 0.0]) * ARROW_HALF_LENGTH,
    ]
    center = oriented_rectangle_center(shape=shape)
    angle = utils.direction_angle(start=shape.points[0], end=shape.points[1])
    rotated = [_rotate_point_around_origin(point=p, angle=angle) for p in local_points]
    translated = np.add(rotated, [center.x(), center.y()])
    head_right, tip, head_left, tail = (
        QtCore.QPointF(float(p[0]), float(p[1])) * shape.scale for p in translated
    )
    path.moveTo(head_right)
    path.lineTo(tip)
    path.lineTo(head_left)
    path.moveTo(tail)
    path.lineTo(tip)


def _build_shape_points_paths(
    *,
    shape: Shape,
    path_line: QtGui.QPainterPath,
    path_vertices: QtGui.QPainterPath,
    path_negative_vertices: QtGui.QPainterPath,
    path_rotation_vertices: QtGui.QPainterPath,
    path_orientation_arrow: QtGui.QPainterPath,
) -> None:
    if shape.shape_type in ["rectangle", "mask"]:
        assert len(shape.points) in [1, 2]
        if len(shape.points) == 2:
            path_line.addRect(
                QtCore.QRectF(
                    shape.points[0] * shape.scale,
                    shape.points[1] * shape.scale,
                )
            )
        if shape.shape_type == "rectangle":
            for i in range(len(shape.points)):
                _build_shape_point_path(path=path_vertices, shape=shape, vertex_index=i)
    elif shape.shape_type == "oriented_rectangle":
        assert len(shape.points) in [1, 2, 4]
        if len(shape.points) == 4:
            path_line.moveTo(shape.points[0] * shape.scale)
            for i, p in enumerate(shape.points):
                path_line.lineTo(p * shape.scale)
                _build_shape_point_path(path=path_vertices, shape=shape, vertex_index=i)
            path_line.lineTo(shape.points[0] * shape.scale)
            for i in range(len(shape.points)):
                _build_shape_rotation_point_path(
                    path=path_rotation_vertices, shape=shape, vertex_index=i
                )
            _build_shape_oriented_rectangle_arrow_path(
                path=path_orientation_arrow, shape=shape
            )
        elif len(shape.points) == 2:
            path_line.moveTo(shape.points[0] * shape.scale)
            path_line.lineTo(shape.points[1] * shape.scale)
            for i in range(2):
                _build_shape_point_path(path=path_vertices, shape=shape, vertex_index=i)
    elif shape.shape_type == "circle":
        assert len(shape.points) in [1, 2]
        if len(shape.points) == 2:
            radius = utils.distance((shape.points[0] - shape.points[1]) * shape.scale)
            path_line.addEllipse(shape.points[0] * shape.scale, radius, radius)
        for i in range(len(shape.points)):
            _build_shape_point_path(path=path_vertices, shape=shape, vertex_index=i)
    elif shape.shape_type == "linestrip":
        path_line.moveTo(shape.points[0] * shape.scale)
        for i, p in enumerate(shape.points):
            path_line.lineTo(p * shape.scale)
            _build_shape_point_path(path=path_vertices, shape=shape, vertex_index=i)
    elif shape.shape_type == "points":
        assert len(shape.points) == len(shape.point_labels)
        for i, point_label in enumerate(shape.point_labels):
            path = path_vertices if point_label == 1 else path_negative_vertices
            _build_shape_point_path(path=path, shape=shape, vertex_index=i)
    else:
        path_line.moveTo(shape.points[0] * shape.scale)
        for i, p in enumerate(shape.points):
            path_line.lineTo(p * shape.scale)
            _build_shape_point_path(path=path_vertices, shape=shape, vertex_index=i)
        if shape.is_closed():
            path_line.lineTo(shape.points[0] * shape.scale)
