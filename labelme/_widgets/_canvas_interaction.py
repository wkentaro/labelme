from __future__ import annotations

import dataclasses
import enum
from collections.abc import Collection
from typing import Final

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import Qt

from .._shape import Shape
from .._shape import image_extent
from .._shape import nearest_edge_index
from .._shape import rotation_handle_centers
from .._shape import vertex_centers
from ._shape_render import hovered_marker_half_size
from ._shape_render import is_hit_by_point


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


_MARKER_KINDS: Final = (
    (HitKind.VERTEX, vertex_centers),
    (HitKind.ROTATION_HANDLE, rotation_handle_centers),
)


@dataclasses.dataclass(frozen=True)
class _Markers:
    centers: npt.NDArray[np.float64]
    shape_order: npt.NDArray[np.intp]
    kind_rank: npt.NDArray[np.intp]
    index: npt.NDArray[np.intp]


def find_hover_target(
    *,
    shapes: list[Shape],
    point: npt.NDArray[np.float64],
    scale: float,
    epsilon: float,
    point_size: int,
    hovered: Shape | None,
    selected: Collection[Shape],
) -> HitTarget | None:
    # Proximity is measured in image space, so the screen-pixel threshold is
    # converted here rather than scaling every shape's points.
    image_epsilon = epsilon / scale
    reach = max(epsilon, hovered_marker_half_size(point_size=point_size)) / scale

    # Every pass below costs array work per shape, so drop the shapes the
    # pointer is nowhere near once, up front.
    shapes = [
        shape
        for shape in shapes
        if _is_near_extent(shape=shape, point=point, margin=reach)
    ]
    marker = _find_nearest_marker(
        shapes=shapes,
        point=point,
        reach=reach,
        hovered=hovered,
        selected=selected,
    )
    if marker is not None:
        return marker

    top = find_shape_at(
        shapes=shapes,
        point=point,
        scale=scale,
        point_size=point_size,
        epsilon=epsilon,
    )
    if top is not None and top.shape_type == "point":
        return HitTarget(kind=HitKind.BODY, shape=top, index=None)

    for shape in _build_candidates(shapes=shapes, priority_shape=hovered):
        if shape.locked or not shape.can_add_point():
            continue
        idx = nearest_edge_index(shape=shape, point=point, image_epsilon=image_epsilon)
        if idx is not None:
            return HitTarget(kind=HitKind.EDGE, shape=shape, index=idx)

    if top is not None:
        return HitTarget(kind=HitKind.BODY, shape=top, index=None)

    return None


def _find_nearest_marker(
    *,
    shapes: list[Shape],
    point: npt.NDArray[np.float64],
    reach: float,
    hovered: Shape | None,
    selected: Collection[Shape],
) -> HitTarget | None:
    markers = _collect_markers(shapes=shapes)
    if markers is None:
        return None
    distances = np.linalg.norm(markers.centers - point, axis=1)
    nearest = distances.min()
    if nearest > reach:
        return None
    tied = np.flatnonzero(distances == nearest)
    order = markers.shape_order[tied]
    not_hovered = np.array([shapes[i] is not hovered for i in order])
    not_selected = np.array([shapes[i] not in selected for i in order])
    best = tied[
        np.lexsort((-order, not_hovered, not_selected, markers.kind_rank[tied]))[0]
    ]
    kind, _ = _MARKER_KINDS[markers.kind_rank[best]]
    return HitTarget(
        kind=kind,
        shape=shapes[markers.shape_order[best]],
        index=int(markers.index[best]),
    )


def _collect_markers(*, shapes: list[Shape]) -> _Markers | None:
    blocks = [
        (order, rank, centers)
        for order, shape in enumerate(shapes)
        if shape.visible and not shape.locked
        for rank, (_, centers_of) in enumerate(_MARKER_KINDS)
        if len(centers := centers_of(shape=shape)) > 0
    ]
    if not blocks:
        return None
    orders, ranks, centers = zip(*blocks, strict=True)
    sizes = [len(block) for block in centers]
    return _Markers(
        centers=np.concatenate(centers),
        shape_order=np.repeat(orders, sizes),
        kind_rank=np.repeat(ranks, sizes),
        index=np.concatenate([np.arange(size) for size in sizes]),
    )


def find_shape_at(
    *,
    shapes: list[Shape],
    point: npt.NDArray[np.float64],
    scale: float,
    point_size: int,
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
