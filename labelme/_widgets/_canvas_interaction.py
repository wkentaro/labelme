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
from ._shape_render import marker_half_size


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
    hovered: HitTarget | None,
    selected: Collection[Shape],
) -> HitTarget | None:
    # Proximity is measured in image space, so the screen-pixel threshold is
    # converted here rather than scaling every shape's points.
    image_epsilon = epsilon / scale
    reach = max(epsilon, marker_half_size(point_size=point_size)) / scale
    hovered_reach = (
        max(epsilon, hovered_marker_half_size(point_size=point_size)) / scale
    )

    # Every pass below costs array work per shape, so drop the shapes the
    # pointer is nowhere near once, up front.
    enlarged = (
        hovered.shape
        if hovered is not None
        and hovered.kind in (HitKind.VERTEX, HitKind.ROTATION_HANDLE)
        else None
    )
    shapes = [
        shape
        for shape in shapes
        if _is_near_extent(
            shape=shape,
            point=point,
            margin=hovered_reach if shape is enlarged else reach,
        )
    ]
    marker = _find_nearest_marker(
        shapes=shapes,
        point=point,
        reach=reach,
        hovered_reach=hovered_reach,
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

    priority_shape = None if hovered is None else hovered.shape
    for shape in _build_candidates(shapes=shapes, priority_shape=priority_shape):
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
    hovered_reach: float,
    hovered: HitTarget | None,
    selected: Collection[Shape],
) -> HitTarget | None:
    nearest = np.inf
    tied: list[tuple[int, HitTarget]] = []
    for order, shape in enumerate(shapes):
        if not shape.visible or shape.locked:
            continue
        for kind, centers_of in (
            (HitKind.VERTEX, vertex_centers),
            (HitKind.ROTATION_HANDLE, rotation_handle_centers),
        ):
            centers = centers_of(shape=shape)
            if len(centers) == 0:
                continue
            offsets = centers - point
            distances = np.einsum("ij,ij->i", offsets, offsets)
            eligible = distances <= reach**2
            if (
                hovered is not None
                and hovered.shape is shape
                and hovered.kind is kind
                and hovered.index is not None
                and hovered.index < len(centers)
            ):
                eligible[hovered.index] = distances[hovered.index] <= hovered_reach**2
            index = int(np.argmin(np.where(eligible, distances, np.inf)))
            closest = distances[index]
            if not eligible[index] or closest > nearest:
                continue
            if closest < nearest:
                nearest = closest
                tied = []
            tied.append((order, HitTarget(kind=kind, shape=shape, index=index)))
    if not tied:
        return None
    has_corner = any(_is_corner(target=target) for _, target in tied)
    hovered_shape = None if hovered is None else hovered.shape
    _, best = min(
        tied,
        key=lambda candidate: (
            has_corner and candidate[1].kind is HitKind.ROTATION_HANDLE,
            candidate[1].shape not in selected,
            candidate[1].shape is not hovered_shape,
            -candidate[0],
        ),
    )
    return best


def _is_corner(*, target: HitTarget) -> bool:
    return target.kind is HitKind.VERTEX and target.shape.shape_type != "point"


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
