from __future__ import annotations

import dataclasses
import enum
from collections.abc import Callable
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

from .._shape import Shape
from .._shape import nearest_edge_index
from .._shape import nearest_rotation_point_index
from .._shape import nearest_vertex_index
from ._shape_render import is_hit_by_point


class CursorRole(enum.Enum):
    DEFAULT = "default"
    DRAW = "draw"
    HANDLE = "handle"
    GRAB = "grab"
    MOVE = "move"


def cursor_shape_for(role: CursorRole, /) -> Qt.CursorShape:
    match role:
        case CursorRole.DEFAULT:
            return Qt.CursorShape.ArrowCursor
        case CursorRole.DRAW:
            return Qt.CursorShape.CrossCursor
        case CursorRole.HANDLE:
            return Qt.CursorShape.PointingHandCursor
        case CursorRole.GRAB:
            return Qt.CursorShape.OpenHandCursor
        case CursorRole.MOVE:
            return Qt.CursorShape.ClosedHandCursor


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


def is_within_pick_threshold(
    *,
    a: npt.NDArray[np.float64],
    b: npt.NDArray[np.float64],
    scale: float,
    epsilon: float,
) -> bool:
    return bool(np.linalg.norm(a - b) < epsilon / scale)


def _candidates_in_hit_order(
    *, shapes: list[Shape], priority_shape: Shape | None
) -> list[Shape]:
    # The most recently interacted-with shape is tried before everything
    # else; the rest follow in reverse paint order (topmost drawn first) so
    # a hit resolves to whatever the user sees on top.
    ordered: list[Shape] = []
    if priority_shape is not None and priority_shape.visible:
        ordered.append(priority_shape)
    ordered.extend(
        shape
        for shape in reversed(shapes)
        if shape.visible and shape is not priority_shape
    )
    return ordered


def _match_vertex(
    *, candidates: Sequence[Shape], point: npt.NDArray[np.float64], image_epsilon: float
) -> HitTarget | None:
    for shape in candidates:
        index = nearest_vertex_index(
            shape=shape, point=point, image_epsilon=image_epsilon
        )
        if index is not None:
            return HitTarget(kind=HitKind.VERTEX, shape=shape, index=index)
    return None


def _match_rotation_handle(
    *, candidates: Sequence[Shape], point: npt.NDArray[np.float64], image_epsilon: float
) -> HitTarget | None:
    for shape in candidates:
        index = nearest_rotation_point_index(
            shape=shape, point=point, image_epsilon=image_epsilon
        )
        if index is not None:
            return HitTarget(kind=HitKind.ROTATION_HANDLE, shape=shape, index=index)
    return None


def _match_edge(
    *, candidates: Sequence[Shape], point: npt.NDArray[np.float64], image_epsilon: float
) -> HitTarget | None:
    for shape in candidates:
        # Only polygon/linestrip shapes accept an inserted vertex, so only
        # they are worth testing for an edge hit.
        if not shape.can_add_point():
            continue
        index = nearest_edge_index(
            shape=shape, point=point, image_epsilon=image_epsilon
        )
        if index is not None:
            return HitTarget(kind=HitKind.EDGE, shape=shape, index=index)
    return None


def _match_body(
    *,
    candidates: Sequence[Shape],
    point: npt.NDArray[np.float64],
    scale: float,
    point_size: int,
    epsilon: float,
) -> HitTarget | None:
    for shape in candidates:
        if is_hit_by_point(
            shape=shape,
            point=point,
            scale=scale,
            point_size=point_size,
            epsilon=epsilon,
        ):
            return HitTarget(kind=HitKind.BODY, shape=shape, index=None)
    return None


def find_hover_target(
    *,
    shapes: list[Shape],
    point: npt.NDArray[np.float64],
    scale: float,
    epsilon: float,
    point_size: int,
    priority_shape: Shape | None,
) -> HitTarget | None:
    candidates = _candidates_in_hit_order(shapes=shapes, priority_shape=priority_shape)
    # Proximity is measured in image space, so the screen-pixel threshold is
    # converted once here rather than scaling every shape's points.
    image_epsilon = epsilon / scale

    # Categories are resolved in this fixed order across *all* candidates
    # before falling through to the next one, so e.g. a vertex on a
    # lower-paint-order shape still beats a body hit on a topmost shape.
    passes: tuple[Callable[[], HitTarget | None], ...] = (
        lambda: _match_vertex(
            candidates=candidates, point=point, image_epsilon=image_epsilon
        ),
        lambda: _match_rotation_handle(
            candidates=candidates, point=point, image_epsilon=image_epsilon
        ),
        lambda: _match_edge(
            candidates=candidates, point=point, image_epsilon=image_epsilon
        ),
        lambda: _match_body(
            candidates=candidates,
            point=point,
            scale=scale,
            point_size=point_size,
            epsilon=epsilon,
        ),
    )
    for resolve in passes:
        target = resolve()
        if target is not None:
            return target
    return None


@dataclasses.dataclass
class ContextMenuPair:
    without_selection: QMenu
    with_selection: QMenu

    def menu_for(self, *, has_selection: bool) -> QMenu:
        return self.with_selection if has_selection else self.without_selection
