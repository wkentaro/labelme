from __future__ import annotations

import dataclasses
import enum
from typing import Final

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import Qt

from .._shape import Shape
from .._shape import image_extent
from .._shape import nearest_derived_corner_index
from .._shape import nearest_edge_index
from .._shape import nearest_rotation_point_index
from .._shape import nearest_vertex_index
from ._shape_render import drawn_marker_half_size
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
    priority_shape: Shape | None


def find_hover_target(
    *,
    shapes: list[Shape],
    point: npt.NDArray[np.float64],
    scale: float,
    epsilon: float,
    point_size: int,
    priority_shape: Shape | None,
    highlighted_vertex: tuple[Shape, int] | None,
) -> HitTarget | None:
    # Proximity is measured in image space, so the screen-pixel threshold is
    # converted here rather than scaling every shape's points.
    image_epsilon = epsilon / scale

    # Every pass below costs array work per shape, so drop the shapes the
    # pointer is nowhere near once, up front.
    highlight_half_size = (
        drawn_marker_half_size(point_size=point_size, highlighted=True) / scale
    )
    margin = max(image_epsilon, highlight_half_size)
    shapes = [
        shape
        for shape in shapes
        if _is_near_extent(shape=shape, point=point, margin=margin)
    ]
    paint_order = [
        shape for shape in reversed(shapes) if shape.visible and not shape.locked
    ]
    handle_order = paint_order
    if (
        priority_shape is not None
        and priority_shape.visible
        and not priority_shape.locked
    ):
        handle_order = [
            priority_shape,
            *(shape for shape in paint_order if shape is not priority_shape),
        ]

    # Pass 1: vertex proximity
    for shape in handle_order:
        idx = nearest_vertex_index(
            shape=shape, point=point, image_epsilon=image_epsilon
        )
        if idx is not None:
            return HitTarget(
                kind=HitKind.VERTEX, shape=shape, index=idx, priority_shape=shape
            )

    # Pass 2: rotation handle proximity
    for shape in handle_order:
        idx = nearest_rotation_point_index(
            shape=shape, point=point, image_epsilon=image_epsilon
        )
        if idx is not None:
            return HitTarget(
                kind=HitKind.ROTATION_HANDLE,
                shape=shape,
                index=idx,
                priority_shape=shape,
            )

    # Pass 3: point dot. A point shape's dot is drawn over the shapes around
    # it, so it outranks their edges. Bodies follow paint order, not the
    # priority shape, so hover picks the shape a click selects.
    top = find_shape_at(
        shapes=shapes,
        point=point,
        scale=scale,
        point_size=point_size,
        epsilon=epsilon,
    )
    if top is not None and top.shape_type == "point":
        return HitTarget(kind=HitKind.BODY, shape=top, index=None, priority_shape=top)

    # Pass 4: edge proximity (only shapes that support adding a point)
    for shape in handle_order:
        if not shape.can_add_point():
            continue
        idx = nearest_edge_index(shape=shape, point=point, image_epsilon=image_epsilon)
        if idx is not None:
            return HitTarget(
                kind=HitKind.EDGE, shape=shape, index=idx, priority_shape=shape
            )

    marker_radius = drawn_marker_half_size(point_size=point_size, highlighted=False)
    for shape in paint_order:
        idx = nearest_derived_corner_index(
            shape=shape,
            point=point,
            image_epsilon=image_epsilon,
            marker_radius=marker_radius / scale,
            highlighted=(
                highlighted_vertex[1]
                if highlighted_vertex is not None and highlighted_vertex[0] is shape
                else None
            ),
            highlight_half_size=highlight_half_size,
        )
        if idx is not None:
            return HitTarget(
                kind=HitKind.VERTEX, shape=shape, index=idx, priority_shape=top
            )

    # Pass 5: body hit
    if top is not None:
        return HitTarget(kind=HitKind.BODY, shape=top, index=None, priority_shape=top)

    return None


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
