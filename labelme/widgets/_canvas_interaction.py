from __future__ import annotations

import dataclasses
import enum
from typing import Final

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

from labelme._shape import Shape
from labelme._shape import nearest_edge_index
from labelme._shape import nearest_rotation_point_index
from labelme._shape import nearest_vertex_index
from labelme.widgets._shape_render import is_hit_by_point


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
    priority_shape: Shape | None,
) -> HitTarget | None:
    candidates = _build_candidates(
        shapes=shapes,
        priority_shape=priority_shape,
    )

    # Pass 1: vertex proximity
    for shape in candidates:
        idx = nearest_vertex_index(
            shape=shape, point=point, scale=scale, epsilon=epsilon
        )
        if idx is not None:
            return HitTarget(kind=HitKind.VERTEX, shape=shape, index=idx)

    # Pass 2: rotation handle proximity
    for shape in candidates:
        idx = nearest_rotation_point_index(
            shape=shape, point=point, scale=scale, epsilon=epsilon
        )
        if idx is not None:
            return HitTarget(kind=HitKind.ROTATION_HANDLE, shape=shape, index=idx)

    # Pass 3: edge proximity (only shapes that support adding a point)
    for shape in candidates:
        if not shape.can_add_point():
            continue
        idx = nearest_edge_index(shape=shape, point=point, scale=scale, epsilon=epsilon)
        if idx is not None:
            return HitTarget(kind=HitKind.EDGE, shape=shape, index=idx)

    # Pass 4: body hit
    for shape in candidates:
        hit = is_hit_by_point(
            shape=shape,
            point=point,
            scale=scale,
            point_size=point_size,
            epsilon=epsilon,
        )
        if hit:
            return HitTarget(kind=HitKind.BODY, shape=shape, index=None)

    return None


def _build_candidates(
    *,
    shapes: list[Shape],
    priority_shape: Shape | None,
) -> list[Shape]:
    candidates: list[Shape] = []
    if priority_shape is not None:
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


def cursor_shape_for(role: CursorRole) -> Qt.CursorShape:
    return _CURSOR_SHAPE_MAP[role]


@dataclasses.dataclass
class ContextMenuPair:
    without_selection: QMenu
    with_selection: QMenu

    def menu_for(self, *, has_selection: bool) -> QMenu:
        if has_selection:
            return self.with_selection
        return self.without_selection
