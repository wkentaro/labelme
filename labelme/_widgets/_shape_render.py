from __future__ import annotations

import dataclasses
import typing
from typing import ClassVar
from typing import Final
from typing import Literal

import numpy as np
import numpy.typing as npt
import skimage.measure
from PySide6 import QtCore
from PySide6 import QtGui

from .. import _utils
from .._shape import CIRCLE_POINT_COUNT
from .._shape import ORIENTED_RECTANGLE_POINT_COUNT
from .._shape import RECTANGLE_POINT_COUNT
from .._shape import Shape
from .._shape import get_rotation_handle
from .._shape import nearest_edge_index
from .._shape import oriented_rectangle_arrow_points


@dataclasses.dataclass(frozen=True)
class VertexHighlight:
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


@dataclasses.dataclass(frozen=True)
class Palette:
    line: QtGui.QColor
    fill: QtGui.QColor
    select_line: QtGui.QColor
    select_fill: QtGui.QColor
    vertex_fill: QtGui.QColor
    hvertex_fill: QtGui.QColor

    @classmethod
    def from_rgb(cls, rgb: tuple[int, int, int], /) -> Palette:
        r, g, b = rgb
        return cls(
            line=QtGui.QColor(r, g, b),
            fill=QtGui.QColor(r, g, b, 128),
            select_line=QtGui.QColor(255, 255, 255),
            select_fill=QtGui.QColor(r, g, b, 155),
            vertex_fill=QtGui.QColor(r, g, b),
            hvertex_fill=QtGui.QColor(255, 255, 255),
        )


@dataclasses.dataclass(frozen=True)
class ShapeRenderContext:
    scale: float
    palette: Palette
    point_size: int
    point_type: Literal["square", "round"]
    selected: bool
    fill: bool
    highlight: VertexHighlight | None
    rotation_highlight: VertexHighlight | None
    show_label: bool = False
    line_style: QtCore.Qt.PenStyle = QtCore.Qt.PenStyle.SolidLine
    # Outline stroke width in screen pixels, shared by every pen this module
    # draws with so the label offset clears the stroke.
    pen_width: ClassVar[int] = 2


def render_shape(
    *, painter: QtGui.QPainter, shape: Shape, context: ShapeRenderContext
) -> None:
    if shape.mask is None and len(shape.points) == 0:
        return

    palette = context.palette
    color = palette.select_line if context.selected else palette.line
    pen = QtGui.QPen(color)
    pen.setWidth(context.pen_width)
    pen.setStyle(context.line_style)
    painter.setPen(pen)

    if shape.shape_type == "mask" and shape.mask is not None:
        _paint_shape_mask(painter=painter, shape=shape, context=context)

    if len(shape.points) > 0:
        _paint_shape_points(painter=painter, shape=shape, context=context)

    if context.show_label:
        _paint_shape_label(painter=painter, shape=shape, context=context)


def _paint_shape_label(
    *,
    painter: QtGui.QPainter,
    shape: Shape,
    context: ShapeRenderContext,
) -> None:
    if not shape.label or len(shape.points) == 0:
        return
    # Anchor at the points' top-left so the text stays close to the shape and
    # tracks zoom/pan; lift it by the pen width to clear the outline stroke.
    top_left = shape.points.min(axis=0) * context.scale
    text = shape.label
    if shape.group_id is not None:
        text += f" ({shape.group_id})"
    painter.setPen(QtGui.QPen(context.palette.line))
    painter.drawText(
        QtCore.QPointF(float(top_left[0]), float(top_left[1]) - context.pen_width),
        text,
    )


def _paint_shape_mask(
    *,
    painter: QtGui.QPainter,
    shape: Shape,
    context: ShapeRenderContext,
) -> None:
    assert shape.mask is not None
    fill = context.palette.select_fill if context.selected else context.palette.fill
    image_to_draw = np.zeros(shape.mask.shape + (4,), dtype=np.uint8)
    image_to_draw[shape.mask] = fill.getRgb()
    qimage = QtGui.QImage.fromData(_utils.img_arr_to_data(image_to_draw))
    origin = shape.points[0]
    target_top_left = origin * context.scale
    target_rect = QtCore.QRectF(
        target_top_left[0],
        target_top_left[1],
        qimage.width() * context.scale,
        qimage.height() * context.scale,
    )
    painter.drawImage(target_rect, qimage)

    path = QtGui.QPainterPath()
    # Pad so a region touching the mask border still has a background ring to
    # close its contour against; the resulting offset is removed below.
    PAD: Final[int] = 1
    contours = skimage.measure.find_contours(np.pad(shape.mask, pad_width=PAD))
    for contour in contours:
        contour = contour - PAD + [origin[1], origin[0]]
        path.moveTo(QtCore.QPointF(contour[0, 1], contour[0, 0]) * context.scale)
        for point in contour[1:]:
            path.lineTo(QtCore.QPointF(point[1], point[0]) * context.scale)
    painter.drawPath(path)


@dataclasses.dataclass(frozen=True)
class _ShapePaths:
    line: QtGui.QPainterPath = dataclasses.field(default_factory=QtGui.QPainterPath)
    vertices: QtGui.QPainterPath = dataclasses.field(default_factory=QtGui.QPainterPath)
    negative_vertices: QtGui.QPainterPath = dataclasses.field(
        default_factory=QtGui.QPainterPath
    )
    rotation_vertices: QtGui.QPainterPath = dataclasses.field(
        default_factory=QtGui.QPainterPath
    )
    orientation_arrow: QtGui.QPainterPath = dataclasses.field(
        default_factory=QtGui.QPainterPath
    )


def _paint_shape_points(
    *,
    painter: QtGui.QPainter,
    shape: Shape,
    context: ShapeRenderContext,
) -> None:
    palette = context.palette
    paths = _build_shape_points_paths(shape=shape, context=context)

    painter.drawPath(paths.line)
    _paint_filled_vertices(
        painter=painter,
        path=paths.vertices,
        highlighted=context.highlight is not None,
        palette=palette,
    )
    _paint_filled_vertices(
        painter=painter,
        path=paths.rotation_vertices,
        highlighted=context.rotation_highlight is not None,
        palette=palette,
    )
    if context.fill and shape.shape_type not in ["line", "linestrip", "points", "mask"]:
        fill = palette.select_fill if context.selected else palette.fill
        painter.fillPath(paths.line, fill)
    if paths.orientation_arrow.length() > 0:
        arrow_pen = QtGui.QPen(palette.vertex_fill)
        arrow_pen.setWidth(context.pen_width)
        painter.setPen(arrow_pen)
        painter.drawPath(paths.orientation_arrow)

    if paths.negative_vertices.length() > 0:
        neg_color = QtGui.QColor(255, 0, 0, 255)
        neg_pen = QtGui.QPen(neg_color)
        neg_pen.setWidth(context.pen_width)
        painter.setPen(neg_pen)
        painter.drawPath(paths.negative_vertices)
        painter.fillPath(paths.negative_vertices, neg_color)


def _paint_filled_vertices(
    *,
    painter: QtGui.QPainter,
    path: QtGui.QPainterPath,
    highlighted: bool,
    palette: Palette,
) -> None:
    if path.length() == 0:
        return
    fill = palette.hvertex_fill if highlighted else palette.vertex_fill
    painter.drawPath(path)
    painter.fillPath(path, fill)


def _resolve_vertex_style(
    *,
    highlight: VertexHighlight | None,
    vertex_index: int,
    default_size: int,
    default_point_type: Literal["square", "round"],
) -> tuple[float, Literal["square", "round"]]:
    if highlight is not None and highlight.index == vertex_index:
        return default_size * highlight.size_factor, highlight.point_type
    return default_size, default_point_type


def _build_shape_point_path(
    *,
    path: QtGui.QPainterPath,
    shape: Shape,
    context: ShapeRenderContext,
    vertex_index: int,
) -> None:
    size, point_type = _resolve_vertex_style(
        highlight=context.highlight,
        vertex_index=vertex_index,
        default_size=context.point_size,
        default_point_type=context.point_type,
    )
    pos = QtCore.QPointF(*(shape.points[vertex_index] * context.scale))
    _draw_vertex(path=path, pos=pos, size=size, point_type=point_type)


def _build_shape_rotation_point_path(
    *,
    path: QtGui.QPainterPath,
    shape: Shape,
    context: ShapeRenderContext,
    vertex_index: int,
) -> None:
    size, point_type = _resolve_vertex_style(
        highlight=context.rotation_highlight,
        vertex_index=vertex_index,
        default_size=context.point_size,
        default_point_type=context.point_type,
    )
    handle = get_rotation_handle(shape=shape, index=vertex_index)
    pos = QtCore.QPointF(*(handle * context.scale))
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
    *, path: QtGui.QPainterPath, shape: Shape, scale: float
) -> None:
    points = oriented_rectangle_arrow_points(shape=shape)
    head_right, tip, head_left, tail = (QtCore.QPointF(*(p * scale)) for p in points)
    path.moveTo(head_right)
    path.lineTo(tip)
    path.lineTo(head_left)
    path.moveTo(tail)
    path.lineTo(tip)


def _build_shape_points_paths(
    *,
    shape: Shape,
    context: ShapeRenderContext,
) -> _ShapePaths:
    paths = _ShapePaths()
    scale = context.scale
    points = shape.points
    if shape.shape_type in ["rectangle", "mask"]:
        assert len(points) in [1, 2]
        paths.line.addPath(_build_two_point_shape_path(shape=shape, scale=scale))
        if shape.shape_type == "rectangle":
            for i in range(len(points)):
                _build_shape_point_path(
                    path=paths.vertices, shape=shape, context=context, vertex_index=i
                )
    elif shape.shape_type == "oriented_rectangle":
        assert len(points) in [1, 2, 4]
        if len(points) == ORIENTED_RECTANGLE_POINT_COUNT:
            paths.line.moveTo(QtCore.QPointF(*(points[0] * scale)))
            for i in range(len(points)):
                paths.line.lineTo(QtCore.QPointF(*(points[i] * scale)))
                _build_shape_point_path(
                    path=paths.vertices, shape=shape, context=context, vertex_index=i
                )
            paths.line.lineTo(QtCore.QPointF(*(points[0] * scale)))
            for i in range(len(points)):
                _build_shape_rotation_point_path(
                    path=paths.rotation_vertices,
                    shape=shape,
                    context=context,
                    vertex_index=i,
                )
            _build_shape_oriented_rectangle_arrow_path(
                path=paths.orientation_arrow, shape=shape, scale=scale
            )
        elif len(points) == CIRCLE_POINT_COUNT:
            paths.line.moveTo(QtCore.QPointF(*(points[0] * scale)))
            paths.line.lineTo(QtCore.QPointF(*(points[1] * scale)))
            for i in range(2):
                _build_shape_point_path(
                    path=paths.vertices, shape=shape, context=context, vertex_index=i
                )
    elif shape.shape_type == "circle":
        assert len(points) in [1, 2]
        paths.line.addPath(_build_two_point_shape_path(shape=shape, scale=scale))
        for i in range(len(points)):
            _build_shape_point_path(
                path=paths.vertices, shape=shape, context=context, vertex_index=i
            )
    elif shape.shape_type == "linestrip":
        paths.line.moveTo(QtCore.QPointF(*(points[0] * scale)))
        for i in range(len(points)):
            paths.line.lineTo(QtCore.QPointF(*(points[i] * scale)))
            _build_shape_point_path(
                path=paths.vertices, shape=shape, context=context, vertex_index=i
            )
    elif shape.shape_type == "points":
        assert len(points) == len(shape.point_labels)
        for i, point_label in enumerate(shape.point_labels):
            path = paths.vertices if point_label == 1 else paths.negative_vertices
            _build_shape_point_path(
                path=path, shape=shape, context=context, vertex_index=i
            )
    else:
        paths.line.moveTo(QtCore.QPointF(*(points[0] * scale)))
        for i in range(len(points)):
            paths.line.lineTo(QtCore.QPointF(*(points[i] * scale)))
            _build_shape_point_path(
                path=paths.vertices, shape=shape, context=context, vertex_index=i
            )
        if shape.closed:
            paths.line.lineTo(QtCore.QPointF(*(points[0] * scale)))
    return paths


def is_hit_by_point(
    *,
    shape: Shape,
    point: npt.NDArray[np.float64],
    scale: float,
    point_size: int,
    epsilon: float,
) -> bool:
    if shape.shape_type in ("line", "linestrip"):
        return (
            nearest_edge_index(shape=shape, point=point, image_epsilon=epsilon / scale)
            is not None
        )
    if shape.shape_type == "points":
        return False
    if shape.shape_type == "point":
        if len(shape.points) == 0:
            return False
        return bool(np.linalg.norm(point - shape.points[0]) <= point_size / 2 / scale)
    if shape.mask is not None:
        raw_y = int(round(float(point[1]) - float(shape.points[0][1])))
        raw_x = int(round(float(point[0]) - float(shape.points[0][0])))
        if (
            raw_y < 0
            or raw_y >= shape.mask.shape[0]
            or raw_x < 0
            or raw_x >= shape.mask.shape[1]
        ):
            return False
        return bool(shape.mask[raw_y, raw_x])
    return _build_image_path(shape=shape).contains(QtCore.QPointF(*point))


def bounds(*, shape: Shape) -> QtCore.QRectF:
    return _build_image_path(shape=shape).boundingRect()


def _build_image_path(*, shape: Shape) -> QtGui.QPainterPath:
    points = shape.points
    out = QtGui.QPainterPath()
    if shape.shape_type in ("rectangle", "mask", "circle"):
        out.addPath(_build_two_point_shape_path(shape=shape, scale=1.0))
    elif shape.shape_type == "oriented_rectangle":
        if len(points) == ORIENTED_RECTANGLE_POINT_COUNT:
            out.moveTo(QtCore.QPointF(*points[0]))
            for p in points[1:]:
                out.lineTo(QtCore.QPointF(*p))
            out.lineTo(QtCore.QPointF(*points[0]))
    else:
        if len(points) > 0:
            out.moveTo(QtCore.QPointF(*points[0]))
            for p in points[1:]:
                out.lineTo(QtCore.QPointF(*p))
    return out


def _build_rect_between(
    *, corner: npt.NDArray[np.float64], opposite: npt.NDArray[np.float64]
) -> QtCore.QRectF:
    x0, y0 = corner
    x1, y1 = opposite
    return QtCore.QRectF(x0, y0, x1 - x0, y1 - y0)


def _build_two_point_shape_path(*, shape: Shape, scale: float) -> QtGui.QPainterPath:
    # A rectangle, a Mask Shape's bounding box, and a circle are each fully
    # described by two points, so one image-space rect covers all three.
    path = QtGui.QPainterPath()
    if shape.shape_type == "circle" and len(shape.points) == CIRCLE_POINT_COUNT:
        center, rim = shape.points
        radius = float(np.linalg.norm(rim - center))
        path.addEllipse(
            _build_rect_between(corner=center - radius, opposite=center + radius)
        )
    elif (
        shape.shape_type in ("rectangle", "mask")
        and len(shape.points) == RECTANGLE_POINT_COUNT
    ):
        corner, opposite = shape.points
        path.addRect(_build_rect_between(corner=corner, opposite=opposite))
    return QtGui.QTransform.fromScale(scale, scale).map(path)
