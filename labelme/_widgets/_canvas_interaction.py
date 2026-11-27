from __future__ import annotations

import dataclasses
import enum
from collections.abc import Collection
from typing import Final
from typing import Literal
from typing import NamedTuple

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import Qt

from .._shape import Shape
from .._shape import get_rotation_handle
from .._shape import image_extent
from .._shape import nearest_edge_index
from .._shape import nearest_rotation_point
from .._shape import nearest_vertex
from ._shape_render import VertexHighlight
from ._shape_render import drawn_marker_radius
from ._shape_render import is_hit_by_point
from ._shape_render import is_marker_hit_by_point


class HitKind(enum.Enum):
    VERTEX = "vertex"
    ROTATION_HANDLE = "rotation_handle"
    EDGE = "edge"
    BODY = "body"


@dataclasses.dataclass(frozen=True)
class HitTarget:
    kind: HitKind
    shape: Shape
    index: int | None


def find_hover_target(
    *,
    shapes: list[Shape],
    point: npt.NDArray[np.float64],
    scale: float,
    epsilon: float,
    point_size: int,
    point_type: Literal["square", "round"],
    hovered: Shape | None,
    highlight: VertexHighlight | None,
    rotation_highlight: VertexHighlight | None,
    selected: Collection[Shape],
) -> HitTarget | None:
    # Proximity is measured in image space, so the screen-pixel threshold is
    # converted here rather than scaling every shape's points.
    image_epsilon = epsilon / scale

    # Every pass below costs array work per shape, so drop the shapes the
    # pointer is nowhere near once, up front.
    hovered_marker_size = point_size * max(
        (h.size_factor for h in (highlight, rotation_highlight) if h is not None),
        default=1.0,
    )
    margin = max(
        image_epsilon,
        drawn_marker_radius(point_size=hovered_marker_size, scale=scale),
    )
    shapes = [
        shape
        for shape in shapes
        if _is_near_extent(shape=shape, point=point, margin=margin)
    ]

    def precedence(shape: Shape) -> tuple[bool, bool]:
        return shape not in selected, shape is not hovered

    painted: _Marker | None = None
    in_reach: list[tuple[float, HitTarget]] = []
    for shape in reversed(shapes):
        if not shape.visible:
            continue
        if shape.shape_type == "point":
            if painted is None and is_hit_by_point(
                shape=shape,
                point=point,
                scale=scale,
                point_size=point_size,
                point_type=point_type,
                epsilon=epsilon,
            ):
                return HitTarget(kind=HitKind.BODY, shape=shape, index=None)
            continue
        if shape.locked:
            continue
        handles = (
            (
                HitKind.ROTATION_HANDLE,
                nearest_rotation_point(shape=shape, point=point),
                rotation_highlight if shape is hovered else None,
            ),
            (
                HitKind.VERTEX,
                nearest_vertex(shape=shape, point=point),
                highlight if shape is hovered else None,
            ),
        )
        for kind, nearest, marker_highlight in handles:
            if nearest is None:
                continue
            marker = _find_marker_under(
                shape=shape,
                kind=kind,
                nearest_index=nearest.index,
                highlight=marker_highlight,
                point=point,
                scale=scale,
                point_size=point_size,
                point_type=point_type,
            )
            if marker is not None and (
                painted is None
                or (
                    np.array_equal(marker.center, painted.center)
                    and precedence(shape) < precedence(painted.target.shape)
                )
            ):
                painted = marker
            if nearest.distance <= image_epsilon:
                in_reach.append(
                    (
                        nearest.distance,
                        HitTarget(kind=kind, shape=shape, index=nearest.index),
                    )
                )
    if painted is not None:
        return painted.target
    if in_reach:
        _, nearest_handle = min(
            in_reach,
            key=lambda reached: (reached[0], precedence(reached[1].shape)),
        )
        return nearest_handle

    for shape in _build_candidates(shapes=shapes, priority_shape=hovered):
        if shape.locked or not shape.can_add_point():
            continue
        idx = nearest_edge_index(shape=shape, point=point, image_epsilon=image_epsilon)
        if idx is not None:
            return HitTarget(kind=HitKind.EDGE, shape=shape, index=idx)

    top = find_shape_at(
        shapes=[shape for shape in shapes if shape.shape_type != "point"],
        point=point,
        scale=scale,
        point_size=point_size,
        point_type=point_type,
        epsilon=epsilon,
    )
    if top is not None:
        return HitTarget(kind=HitKind.BODY, shape=top, index=None)

    return None


class _Marker(NamedTuple):
    target: HitTarget
    center: npt.NDArray[np.float64]


def _find_marker_under(
    *,
    shape: Shape,
    kind: HitKind,
    nearest_index: int,
    highlight: VertexHighlight | None,
    point: npt.NDArray[np.float64],
    scale: float,
    point_size: int,
    point_type: Literal["square", "round"],
) -> _Marker | None:
    indices = [nearest_index] if highlight is None else [highlight.index, nearest_index]
    for index in indices:
        if kind is HitKind.ROTATION_HANDLE:
            center = get_rotation_handle(shape=shape, index=index)
        else:
            center = shape.points[index]
        if is_marker_hit_by_point(
            center=center,
            index=index,
            highlight=highlight,
            point=point,
            scale=scale,
            point_size=point_size,
            point_type=point_type,
        ):
            return _Marker(
                target=HitTarget(kind=kind, shape=shape, index=index), center=center
            )
    return None


def find_shape_at(
    *,
    shapes: list[Shape],
    point: npt.NDArray[np.float64],
    scale: float,
    point_size: int,
    point_type: Literal["square", "round"],
    epsilon: float,
) -> Shape | None:
    # Topmost first, with point shapes ahead of the shapes they sit on. Below
    # the first hit only a point shape can still win, so skip the rest.
    first: Shape | None = None
    for shape in reversed(shapes):
        if not shape.visible:
            continue
        if first is not None and shape.shape_type != "point":
            continue
        if not is_hit_by_point(
            shape=shape,
            point=point,
            scale=scale,
            point_size=point_size,
            point_type=point_type,
            epsilon=epsilon,
        ):
            continue
        if shape.shape_type == "point":
            return shape
        first = shape
    return first


def _is_near_extent(
    *, shape: Shape, point: npt.NDArray[np.float64], margin: float
) -> bool:
    if len(shape.points) == 0:
        return False
    lo, hi = image_extent(shape=shape)
    return bool(np.all(point >= lo - margin) and np.all(point <= hi + margin))


def _build_candidates(
    *,
    shapes: list[Shape],
    priority_shape: Shape | None,
) -> list[Shape]:
    candidates: list[Shape] = []
    if priority_shape is not None and priority_shape.visible:
        candidates.append(priority_shape)
    for shape in reversed(shapes):
        if not shape.visible:
            continue
        if shape is priority_shape:
            continue
        candidates.append(shape)
    return candidates


def is_within_pick_threshold(
    *,
    a: npt.NDArray[np.float64],
    b: npt.NDArray[np.float64],
    scale: float,
    epsilon: float,
) -> bool:
    return bool(np.linalg.norm(a - b) < epsilon / scale)


class CursorRole(enum.Enum):
    DEFAULT = "default"
    DRAW = "draw"
    HANDLE = "handle"
    GRAB = "grab"
    MOVE = "move"


_CURSOR_SHAPE_MAP: Final[dict[CursorRole, Qt.CursorShape]] = {
    CursorRole.DEFAULT: Qt.CursorShape.ArrowCursor,
    CursorRole.DRAW: Qt.CursorShape.CrossCursor,
    CursorRole.HANDLE: Qt.CursorShape.PointingHandCursor,
    CursorRole.GRAB: Qt.CursorShape.OpenHandCursor,
    CursorRole.MOVE: Qt.CursorShape.ClosedHandCursor,
}
assert set(_CURSOR_SHAPE_MAP) == set(CursorRole), (
    f"_CURSOR_SHAPE_MAP missing roles: {set(CursorRole) - set(_CURSOR_SHAPE_MAP)}"
)


def cursor_shape_for(*, role: CursorRole) -> Qt.CursorShape:
    return _CURSOR_SHAPE_MAP[role]
