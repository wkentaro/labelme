from __future__ import annotations

import collections
import dataclasses
import sys
import typing
from typing import Final
from typing import Literal

import numpy as np
import numpy.typing as npt
from PySide6 import QtCore
from PySide6 import QtGui

from .._automation import find_mask_contours
from .._shape import CIRCLE_POINT_COUNT
from .._shape import LINE_POINT_COUNT
from .._shape import ORIENTED_RECTANGLE_POINT_COUNT
from .._shape import RECTANGLE_POINT_COUNT
from .._shape import Shape
from .._shape import get_rotation_handle
from .._shape import image_extent
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
    def from_rgb(cls, *, rgb: tuple[int, int, int]) -> Palette:
        r, g, b = rgb
        return cls(
            line=QtGui.QColor(r, g, b),
            fill=QtGui.QColor(r, g, b, 128),
            select_line=QtGui.QColor(255, 255, 255),
            select_fill=QtGui.QColor(r, g, b, 155),
            vertex_fill=QtGui.QColor(r, g, b),
            hvertex_fill=QtGui.QColor(255, 255, 255),
        )

    @classmethod
    def from_shape_config(cls, *, shape: dict) -> Palette:
        return cls(
            line=QtGui.QColor(*shape["line_color"]),
            fill=QtGui.QColor(*shape["fill_color"]),
            select_line=QtGui.QColor(*shape["select_line_color"]),
            select_fill=QtGui.QColor(*shape["select_fill_color"]),
            vertex_fill=QtGui.QColor(*shape["vertex_fill_color"]),
            hvertex_fill=QtGui.QColor(*shape["hvertex_fill_color"]),
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
    show_vertices: bool = True
    line_style: QtCore.Qt.PenStyle = QtCore.Qt.PenStyle.SolidLine
    # A mask is filled even when fill is off, as every unselected mask Shape
    # is; False draws its contour alone.
    fill_mask: bool = True
    # False draws the fill alone, with no edge or vertex markers.
    outline: bool = True


# Shapes are stroked in widget space, so the outline keeps this many screen
# pixels at every zoom level.
_OUTLINE_WIDTH: Final[float] = 2.0

# Red marks an excluding prompt, a negative point or a counter-example box; a
# "−" goes with it, since red and green are the pair color-blind users confuse.
NEGATIVE_RGB: Final[tuple[int, int, int]] = (255, 0, 0)


class ShapeRenderCache:
    max_bytes: int
    _max_entries: int
    _entries: collections.OrderedDict[
        tuple[object, ...], tuple[QtGui.QImage | QtGui.QPainterPath | _ShapePaths, int]
    ]
    _size_bytes: int
    _used: set[int]

    def __init__(
        self, *, max_bytes: int = 64 * 1024 * 1024, max_entries: int = 512
    ) -> None:
        self.max_bytes = max_bytes
        self._max_entries = max_entries
        self._entries = collections.OrderedDict()
        self._size_bytes = 0
        self._used = set()

    def begin_paint(self) -> None:
        self._used.clear()

    def clear(self) -> None:
        self._entries.clear()
        self._used.clear()
        self._size_bytes = 0

    def _get(
        self, *, key: tuple[object, ...]
    ) -> QtGui.QImage | QtGui.QPainterPath | _ShapePaths | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        self._used.add(id(entry[0]))
        self._entries.move_to_end(key)
        return entry[0]

    def _put(
        self,
        *,
        key: tuple[object, ...],
        value: QtGui.QImage | QtGui.QPainterPath | _ShapePaths,
        size_bytes: int,
    ) -> None:
        # Qt allocations are estimated; include keys and conservative entry overhead.
        size_bytes += sys.getsizeof(key) + sum(sys.getsizeof(v) for v in key) + 256
        if size_bytes > self.max_bytes or self._max_entries < 1:
            return
        while (
            self._size_bytes + size_bytes > self.max_bytes
            or len(self._entries) >= self._max_entries
        ):
            # Protect this paint's residents so an oversized scene cannot thrash.
            victim = next(
                (
                    k
                    for k, (asset, _) in self._entries.items()
                    if id(asset) not in self._used
                ),
                None,
            )
            if victim is None:
                return
            _, removed_bytes = self._entries.pop(victim)
            self._size_bytes -= removed_bytes
        self._entries[key] = value, size_bytes
        self._size_bytes += size_bytes
        self._used.add(id(value))


def render_shape(
    *,
    painter: QtGui.QPainter,
    shape: Shape,
    context: ShapeRenderContext,
    cache: ShapeRenderCache | None = None,
) -> None:
    if shape.mask is None and len(shape.points) == 0:
        return

    palette = context.palette
    color = palette.select_line if context.selected else palette.line
    painter.setPen(
        QtGui.QPen(color, _OUTLINE_WIDTH, context.line_style)
        if context.outline
        else QtCore.Qt.PenStyle.NoPen
    )

    if shape.shape_type == "mask" and shape.mask is not None:
        _paint_mask(painter=painter, shape=shape, context=context, cache=cache)

    if len(shape.points) > 0:
        _paint_shape_points(painter=painter, shape=shape, context=context, cache=cache)

    if context.show_label:
        _paint_label(painter=painter, shape=shape, context=context)


_LARGEST_HIGHLIGHT: Final = VertexHighlight(index=0, mode="near")


def intersects_rect(
    *,
    painter: QtGui.QPainter,
    shape: Shape,
    context: ShapeRenderContext,
    rect: QtCore.QRectF,
) -> bool:
    # A cheap, conservative test in painter space, so a shape scrolled out of
    # view costs a few array ops instead of a full render.
    points = shape.points
    if len(points) == 0:
        return True
    anchor = points.min(axis=0)
    lo, hi = image_extent(shape=shape)
    largest_marker = context.point_size * _LARGEST_HIGHLIGHT.size_factor
    pad = largest_marker / 2 + _OUTLINE_WIDTH
    left, top = lo * context.scale - pad
    right, bottom = hi * context.scale + pad
    extent = QtCore.QRectF(left, top, right - left, bottom - top)
    if context.show_label and shape.label:
        # _paint_label draws from the points' top-left corner, with the
        # baseline lifted by the outline width; descenders hang below it.
        metrics = painter.fontMetrics()
        text = _label_text(label=shape.label, group_id=shape.group_id)
        label_x, label_y = anchor * context.scale
        # The font's ascent-to-descent box, padded by a line height on every
        # side: glyphs from a fallback font (stacked marks in Burmese, for
        # example) overhang it, and on Windows boundingRect(text) came out
        # far larger than the drawn text.
        line = metrics.height()
        text_rect = QtCore.QRectF(
            label_x,
            label_y - _OUTLINE_WIDTH - metrics.ascent(),
            metrics.horizontalAdvance(text),
            metrics.ascent() + metrics.descent(),
        ).adjusted(-line, -line, line, line)
        extent = extent.united(text_rect)
    return rect.intersects(extent)


def _paint_label(
    *, painter: QtGui.QPainter, shape: Shape, context: ShapeRenderContext
) -> None:
    if not shape.label or len(shape.points) == 0:
        return
    text = _label_text(label=shape.label, group_id=shape.group_id)
    # Anchor at the points' top-left corner so the label stays close to the
    # shape and tracks pan/zoom; lift it above the outline stroke.
    anchor = shape.points.min(axis=0) * context.scale
    painter.setPen(QtGui.QPen(context.palette.line))
    painter.drawText(
        QtCore.QPointF(float(anchor[0]), float(anchor[1]) - _OUTLINE_WIDTH), text
    )


def _label_text(*, label: str, group_id: int | None) -> str:
    return label if group_id is None else f"{label} ({group_id})"


def _paint_mask(
    *,
    painter: QtGui.QPainter,
    shape: Shape,
    context: ShapeRenderContext,
    cache: ShapeRenderCache | None,
) -> None:
    assert shape.mask is not None
    mask = shape.mask
    origin = shape.points[0] * context.scale
    # Avoid copying a large key for an asset that cannot fit even without overhead.
    data = (
        mask.tobytes()
        if cache is not None
        and (
            (context.outline and mask.nbytes <= cache.max_bytes)
            or (context.fill_mask and mask.nbytes * 5 <= cache.max_bytes)
        )
        else None
    )
    if context.fill_mask:
        fill_color = (
            context.palette.select_fill if context.selected else context.palette.fill
        ).getRgb()
        fill_key = ("mask-fill", mask.shape, data, fill_color)
        cache_fill = (
            cache is not None
            and data is not None
            and mask.nbytes * 5 <= cache.max_bytes
        )
        bitmap = cache._get(key=fill_key) if cache is not None and cache_fill else None
        if bitmap is None:
            rgba = np.zeros(mask.shape + (4,), dtype=np.uint8)
            rgba[mask] = fill_color
            height, width = mask.shape
            # Own the pixels so cached images outlive the temporary numpy array.
            bitmap = QtGui.QImage(
                rgba.data, width, height, 4 * width, QtGui.QImage.Format.Format_RGBA8888
            ).copy()
            if cache_fill:
                assert cache is not None
                cache._put(key=fill_key, value=bitmap, size_bytes=bitmap.sizeInBytes())
        assert isinstance(bitmap, QtGui.QImage)
        painter.drawImage(
            QtCore.QRectF(
                origin[0],
                origin[1],
                bitmap.width() * context.scale,
                bitmap.height() * context.scale,
            ),
            bitmap,
        )
    if not context.outline:
        return

    outline_key = ("mask-outline", mask.shape, data)
    contour_path = (
        cache._get(key=outline_key) if cache is not None and data is not None else None
    )
    if contour_path is None:
        contour_path = QtGui.QPainterPath()
        for contour in find_mask_contours(mask=mask):
            contour_path.addPolygon(
                QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in contour])
            )
        if cache is not None and data is not None:
            cache._put(
                key=outline_key,
                value=contour_path,
                size_bytes=contour_path.capacity() * 32 + 128,
            )
    assert isinstance(contour_path, QtGui.QPainterPath)
    painter.drawPath(
        QtGui.QTransform(context.scale, 0, 0, context.scale, origin[0], origin[1]).map(
            contour_path
        )
    )


_Vertex = tuple[QtCore.QRectF, Literal["square", "round"]]


@dataclasses.dataclass(frozen=True)
class _ShapePaths:
    line: QtGui.QPainterPath = dataclasses.field(default_factory=QtGui.QPainterPath)
    vertices: list[_Vertex] = dataclasses.field(default_factory=list)
    negative_vertices: list[_Vertex] = dataclasses.field(default_factory=list)
    rotation_vertices: list[_Vertex] = dataclasses.field(default_factory=list)
    # Marker centers grouped by size and type, for batched painting.
    vertex_points: dict[tuple[float, str], QtGui.QPolygonF] = dataclasses.field(
        default_factory=dict
    )
    orientation_arrow: QtGui.QPainterPath = dataclasses.field(
        default_factory=QtGui.QPainterPath
    )


def _paint_shape_points(
    *,
    painter: QtGui.QPainter,
    shape: Shape,
    context: ShapeRenderContext,
    cache: ShapeRenderCache | None,
) -> None:
    palette = context.palette
    key = None
    if (
        cache is not None
        and shape.shape_type == "polygon"
        and shape.points.nbytes <= cache.max_bytes
    ):
        key = (
            "polygon",
            shape.points.shape,
            shape.points.dtype.str,
            shape.points.tobytes(),
            shape.closed,
            context.scale,
            context.point_size,
            context.point_type,
            context.highlight,
            context.show_vertices,
        )
    paths = cache._get(key=key) if cache is not None and key is not None else None
    if paths is None:
        paths = _build_shape_points_paths(shape=shape, context=context)
        for rect, point_type in paths.vertices:
            # A zero-width pen is cosmetic in Qt and would still paint a dot.
            if rect.isEmpty():
                continue
            paths.vertex_points.setdefault(
                (rect.width(), point_type), QtGui.QPolygonF()
            ).append(rect.center())
        if cache is not None and key is not None:
            cache._put(
                key=key,
                value=paths,
                size_bytes=paths.line.capacity() * 32
                + sys.getsizeof(paths)
                + sys.getsizeof(paths.vertices)
                + len(paths.vertices) * (256 + 16),
            )
    assert isinstance(paths, _ShapePaths)

    if context.outline:
        painter.drawPath(paths.line)
        _paint_filled_vertices(
            painter=painter,
            vertices=paths.vertices,
            fill=palette.hvertex_fill
            if context.highlight is not None
            else palette.vertex_fill,
            points=paths.vertex_points,
        )
        _paint_filled_vertices(
            painter=painter,
            vertices=paths.rotation_vertices,
            fill=(
                palette.hvertex_fill
                if context.rotation_highlight is not None
                else palette.vertex_fill
            ),
        )
    if context.fill and shape.shape_type not in ["line", "linestrip", "points", "mask"]:
        fill = palette.select_fill if context.selected else palette.fill
        painter.fillPath(paths.line, fill)
    if not context.outline:
        return
    if paths.orientation_arrow.length() > 0:
        painter.setPen(QtGui.QPen(palette.vertex_fill, _OUTLINE_WIDTH))
        painter.drawPath(paths.orientation_arrow)

    if paths.negative_vertices:
        neg_color = QtGui.QColor(*NEGATIVE_RGB)
        painter.setPen(QtGui.QPen(neg_color, _OUTLINE_WIDTH))
        _paint_filled_vertices(
            painter=painter, vertices=paths.negative_vertices, fill=neg_color
        )
        _paint_minus_marks(painter=painter, vertices=paths.negative_vertices)


def _paint_minus_marks(*, painter: QtGui.QPainter, vertices: list[_Vertex]) -> None:
    pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 2.0)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
    painter.setPen(pen)
    for rect, _ in vertices:
        center = rect.center()
        half = QtCore.QPointF(rect.width() * 0.35, 0.0)
        painter.drawLine(center - half, center + half)


def _paint_filled_vertices(
    *,
    painter: QtGui.QPainter,
    vertices: list[_Vertex],
    fill: QtGui.QColor,
    points: dict[tuple[float, str], QtGui.QPolygonF] | None = None,
) -> None:
    # Independent translucent strokes accumulate opacity where markers overlap.
    # Keep their combined outline, and only split ordinary opaque strokes.
    pen = painter.pen()
    draw_individually = (
        pen.color().alphaF() == 1
        and pen.style() == QtCore.Qt.PenStyle.SolidLine
        and painter.opacity() == 1
        and painter.brush().style() == QtCore.Qt.BrushStyle.NoBrush
        and painter.compositionMode()
        == QtGui.QPainter.CompositionMode.CompositionMode_SourceOver
    )
    # Batching paints every outline before every fill, which would cover a
    # translucent fill and hide a contrasting outline between overlapping
    # markers. One opaque color for both looks the same either way.
    if points is not None and draw_individually and fill == pen.color():
        _paint_vertex_points(painter=painter, points=points, fill=fill)
        return
    path = QtGui.QPainterPath()
    for rect, point_type in vertices:
        if point_type == "round":
            if draw_individually:
                painter.drawEllipse(rect)
            path.addEllipse(rect)
        else:
            if draw_individually:
                painter.drawRect(rect)
            path.addRect(rect)
    if not draw_individually:
        painter.drawPath(path)
    # The shared fill retains the holes and highlights where markers overlap.
    painter.fillPath(path, fill)


def _paint_vertex_points(
    *,
    painter: QtGui.QPainter,
    points: dict[tuple[float, str], QtGui.QPolygonF],
    fill: QtGui.QColor,
) -> None:
    # One wide capped pen paints all markers of a size in a single call, far
    # cheaper than an ellipse each on dense Shapes.
    pen = painter.pen()
    for (size, point_type), centers in points.items():
        cap = (
            QtCore.Qt.PenCapStyle.RoundCap
            if point_type == "round"
            else QtCore.Qt.PenCapStyle.SquareCap
        )
        for color, width in ((pen.color(), size + pen.widthF()), (fill, size)):
            marker = QtGui.QPen(color, width)
            marker.setCapStyle(cap)
            painter.setPen(marker)
            painter.drawPoints(centers)
    painter.setPen(pen)


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


def _append_shape_vertex(
    *,
    vertices: list[_Vertex],
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
    _append_vertex(vertices=vertices, pos=pos, size=size, point_type=point_type)


def _append_shape_rotation_vertex(
    *,
    vertices: list[_Vertex],
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
    _append_vertex(vertices=vertices, pos=pos, size=size, point_type=point_type)


def _append_vertex(
    *,
    vertices: list[_Vertex],
    pos: QtCore.QPointF,
    size: float,
    point_type: Literal["square", "round"],
) -> None:
    half = size / 2.0
    vertices.append(
        (QtCore.QRectF(pos.x() - half, pos.y() - half, size, size), point_type)
    )


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
    if shape.shape_type in ("rectangle", "mask", "circle"):
        assert len(points) in [1, 2]
    elif shape.shape_type == "oriented_rectangle":
        assert len(points) in [1, 2, 4]
    elif shape.shape_type == "points":
        assert len(points) == len(shape.point_labels)

    if shape.shape_type == "points":
        # Prompt points are standalone markers; their outline only bounds them.
        for i, point_label in enumerate(shape.point_labels):
            vertices = paths.vertices if point_label == 1 else paths.negative_vertices
            _append_shape_vertex(
                vertices=vertices, shape=shape, context=context, vertex_index=i
            )
        return paths

    paths.line.addPath(
        QtGui.QTransform.fromScale(scale, scale).map(_build_outline_path(shape=shape))
    )
    # A mask's corners are not draggable, and an oriented rectangle's first
    # corner is drawn by the drag preview until its first edge is locked.
    if shape.shape_type == "mask" or (
        shape.shape_type == "oriented_rectangle" and len(points) == 1
    ):
        return paths
    for i in range(len(points)):
        if context.show_vertices or (
            context.highlight is not None and context.highlight.index == i
        ):
            _append_shape_vertex(
                vertices=paths.vertices, shape=shape, context=context, vertex_index=i
            )
    if (
        shape.shape_type == "oriented_rectangle"
        and len(points) == ORIENTED_RECTANGLE_POINT_COUNT
    ):
        for i in range(len(points)):
            _append_shape_rotation_vertex(
                vertices=paths.rotation_vertices,
                shape=shape,
                context=context,
                vertex_index=i,
            )
        _build_shape_oriented_rectangle_arrow_path(
            path=paths.orientation_arrow, shape=shape, scale=scale
        )
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
        return _hits_mask_pixel(shape=shape, point=point)
    return _build_outline_path(shape=shape).contains(QtCore.QPointF(*point))


def bounds(*, shape: Shape) -> QtCore.QRectF:
    return _build_outline_path(shape=shape).boundingRect()


def _build_outline_path(*, shape: Shape) -> QtGui.QPainterPath:
    # The single image-space outline behind painting, hit-testing and bounds,
    # so a shape is picked exactly where it is drawn.
    points = shape.points
    path = QtGui.QPainterPath()
    if shape.shape_type in ("rectangle", "mask", "circle"):
        path.addPath(_build_two_point_outline(shape=shape))
    elif shape.shape_type == "oriented_rectangle" and len(points) not in (
        LINE_POINT_COUNT,
        ORIENTED_RECTANGLE_POINT_COUNT,
    ):
        # Neither the first edge being dragged nor a finished loop yet.
        pass
    elif len(points) > 0:
        # lineTo, unlike addPolygon, drops a repeated point instead of adding a
        # zero-length segment the stroker would cap with a dot.
        path.moveTo(QtCore.QPointF(*points[0]))
        for point in points[1:]:
            path.lineTo(QtCore.QPointF(*point))
        # An oriented rectangle is a loop exactly when finished, whatever its
        # flag says (a preview inherits the flag from the previous mode). A
        # linestrip is flagged closed on commit like every shape, yet stays
        # open by definition.
        if shape.shape_type == "oriented_rectangle":
            is_loop = len(points) == ORIENTED_RECTANGLE_POINT_COUNT
        else:
            is_loop = shape.closed and shape.shape_type != "linestrip"
        if is_loop:
            path.lineTo(QtCore.QPointF(*points[0]))
    return path


def _build_rect_between(
    *, corner: npt.NDArray[np.float64], opposite: npt.NDArray[np.float64]
) -> QtCore.QRectF:
    x0, y0 = corner
    x1, y1 = opposite
    return QtCore.QRectF(x0, y0, x1 - x0, y1 - y0)


def _build_two_point_outline(*, shape: Shape) -> QtGui.QPainterPath:
    # A rectangle, a mask shape's bounding box, and a circle are each fully
    # described by two points, so one image-space path shape covers all three.
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
        if shape.mask is not None:
            # The frame wraps the mask's pixels, which span c to c + 1.
            opposite = corner + shape.mask.shape[::-1]
        path.addRect(_build_rect_between(corner=corner, opposite=opposite))
    return path


def _hits_mask_pixel(*, shape: Shape, point: npt.NDArray[np.float64]) -> bool:
    assert shape.mask is not None
    col, row = np.floor(point - shape.points[0]).astype(int)
    if row < 0 or row >= shape.mask.shape[0] or col < 0 or col >= shape.mask.shape[1]:
        return False
    return bool(shape.mask[row, col])
