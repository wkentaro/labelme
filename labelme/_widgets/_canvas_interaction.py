from __future__ import annotations

import dataclasses
import enum
import itertools
import math
from collections.abc import Collection
from typing import Final
from typing import Literal

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import Qt

from .._shape import Shape
from .._shape import get_rotation_handle
from .._shape import image_extent
from .._shape import nearest_edge_index
from .._shape import rotation_handles_near
from .._shape import vertices_near
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
    marker_radius = drawn_marker_radius(point_size=hovered_marker_size, scale=scale)
    shapes = [
        shape
        for shape in shapes
        if _is_near_extent(
            shape=shape, point=point, margin=max(image_epsilon, marker_radius)
        )
    ]
    search_radius = max(image_epsilon, math.sqrt(2) * marker_radius)

    under_cursor: list[tuple[tuple[float, ...], HitTarget]] = []
    in_reach: list[tuple[tuple[float, ...], HitTarget]] = []
    for paint_order, shape in enumerate(shapes):
        if not shape.visible:
            continue
        precedence = (shape not in selected, shape is not hovered, -paint_order)
        if shape.shape_type == "point":
            dot = shape.points[0]
            if is_marker_hit_by_point(
                center=dot,
                index=0,
                highlight=None,
                point=point,
                scale=scale,
                point_size=point_size,
                point_type=point_type,
            ):
                under_cursor.append(
                    (
                        (float(np.linalg.norm(point - dot)), *precedence, 0),
                        HitTarget(kind=HitKind.BODY, shape=shape, index=None),
                    )
                )
            continue
        if shape.locked:
            continue
        handles = (
            (
                HitKind.VERTEX,
                vertices_near(shape=shape, point=point, radius=search_radius),
                highlight,
            ),
            (
                HitKind.ROTATION_HANDLE,
                rotation_handles_near(shape=shape, point=point, radius=search_radius),
                rotation_highlight,
            ),
        )
        for layer, (kind, nearby, kind_highlight) in enumerate(handles):
            nearest = next(nearby, None)
            if nearest is None:
                continue
            marker_highlight = kind_highlight if shape is hovered else None
            covering = next(
                (
                    handle
                    for handle in itertools.chain([nearest], nearby)
                    if is_marker_hit_by_point(
                        center=_handle_center(
                            shape=shape, kind=kind, index=handle.index
                        ),
                        index=handle.index,
                        highlight=marker_highlight,
                        point=point,
                        scale=scale,
                        point_size=point_size,
                        point_type=point_type,
                    )
                ),
                None,
            )
            if covering is not None:
                under_cursor.append(
                    (
                        (covering.distance, *precedence, -layer),
                        HitTarget(kind=kind, shape=shape, index=covering.index),
                    )
                )
            if nearest.distance <= image_epsilon:
                in_reach.append(
                    (
                        (nearest.distance, *precedence, -layer),
                        HitTarget(kind=kind, shape=shape, index=nearest.index),
                    )
                )
    for candidates in (under_cursor, in_reach):
        if candidates:
            return min(candidates, key=lambda candidate: candidate[0])[1]

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


def _handle_center(
    *, shape: Shape, kind: HitKind, index: int
) -> npt.NDArray[np.float64]:
    if kind is HitKind.ROTATION_HANDLE:
        return get_rotation_handle(shape=shape, index=index)
    return shape.points[index]


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
