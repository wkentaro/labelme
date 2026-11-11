from __future__ import annotations

from typing import Final
from typing import Literal

import numpy as np

from ._model import MIN_POLYGON_POINT_COUNT
from ._model import Shape
from ._model import ShapeType

# Every kind a user can create, in the draw menu's order; "points" is only
# a circle being drawn.
ConvertTarget = Literal[
    "polygon",
    "rectangle",
    "oriented_rectangle",
    "circle",
    "line",
    "point",
    "linestrip",
    "mask",
]
ConvertBlocker = Literal[
    "no_selection", "already_target", "wrong_type", "too_few_points", "locked"
]

# Targets missing here are listed in the menu but not convertible yet.
_SOURCES: Final[dict[ConvertTarget, frozenset[ShapeType]]] = {
    "polygon": frozenset({"rectangle", "linestrip"}),
    "rectangle": frozenset({"polygon"}),
    "linestrip": frozenset({"polygon"}),
}


def convert_blocker(
    *, shapes: list[Shape], target: ConvertTarget
) -> ConvertBlocker | None:
    # Shapes already of the target kind are left as they are, so Select All
    # can bring every shape to one kind. Ordered by what the user fixes first,
    # like merge_blocker: a locked circle reports "wrong_type", since
    # unlocking it would still not make it convertible.
    if not shapes:
        return "no_selection"
    sources = [s for s in shapes if s.shape_type != target]
    if not sources:
        return "already_target"
    if any(s.shape_type not in _SOURCES.get(target, ()) for s in sources):
        return "wrong_type"
    # Distinct vertices, as drawing counts them: a linestrip may revisit one.
    if any(
        s.shape_type == "linestrip"
        and len(np.unique(s.points, axis=0)) < MIN_POLYGON_POINT_COUNT
        for s in sources
    ):
        return "too_few_points"
    if any(s.locked for s in sources):
        return "locked"
    return None


def convert_shape(*, shape: Shape, target: ConvertTarget) -> Shape:
    if convert_blocker(shapes=[shape], target=target) is not None:
        raise ValueError(f"cannot convert {shape.shape_type} to {target}")
    converted = shape.copy()
    converted.shape_type = target
    if target == "rectangle":
        converted.points = np.array(
            [shape.points.min(axis=0), shape.points.max(axis=0)]
        )
    elif shape.shape_type == "rectangle":
        (x0, y0), (x1, y1) = shape.points
        converted.points = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    else:
        # polygon <-> linestrip keeps every vertex, so it keeps their labels too.
        return converted
    converted.point_labels = np.ones(len(converted.points), dtype=np.int_)
    return converted
