from __future__ import annotations

from typing import Final
from typing import Literal

import numpy as np
import numpy.typing as npt

from ._model import LINE_POINT_COUNT
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
    "no_selection",
    "already_target",
    "wrong_type",
    "too_few_points",
    "too_many_points",
    "no_area",
    "locked",
]

# Each route here has one possible result, so it converts without asking.
# Targets missing here are listed in the menu but not convertible yet.
_SOURCES: Final[dict[ConvertTarget, frozenset[ShapeType]]] = {
    "polygon": frozenset({"rectangle", "oriented_rectangle", "linestrip"}),
    "rectangle": frozenset(
        {"polygon", "oriented_rectangle", "circle", "linestrip", "mask"}
    ),
    "line": frozenset({"linestrip"}),
    "linestrip": frozenset({"polygon", "line"}),
}


def convert_blocker(
    *,
    shapes: list[Shape],
    target: ConvertTarget,
    image_size: tuple[int, int] | None = None,
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
    if target == "polygon" and any(
        s.shape_type == "linestrip"
        and len(np.unique(s.points, axis=0)) < MIN_POLYGON_POINT_COUNT
        for s in sources
    ):
        return "too_few_points"
    # A line stores exactly its two ends, so count stored points here.
    if target == "line" and any(
        len(s.points) != LINE_POINT_COUNT
        for s in sources
        if s.shape_type == "linestrip"
    ):
        return "too_many_points"
    if target == "rectangle" and any(
        np.any(box[1] <= box[0])
        for box in (_bounding_box(shape=s, image_size=image_size) for s in sources)
    ):
        return "no_area"
    if any(s.locked for s in sources):
        return "locked"
    return None


def convert_shape(
    *,
    shape: Shape,
    target: ConvertTarget,
    image_size: tuple[int, int] | None = None,
) -> Shape:
    # image_size (width, height) keeps new points inside the image, for when
    # out-of-bounds points are off (ADR 0004): a circle's box can overhang.
    if convert_blocker(shapes=[shape], target=target, image_size=image_size):
        raise ValueError(f"cannot convert {shape.shape_type} to {target}")
    converted = shape.copy()
    converted.shape_type = target
    converted.mask = None
    if target == "rectangle":
        converted.points = _bounding_box(shape=shape, image_size=image_size)
    elif shape.shape_type == "rectangle":
        (x0, y0), (x1, y1) = shape.points
        converted.points = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    else:
        # The rest keep every vertex in order, so they keep their labels too.
        return converted
    converted.point_labels = np.ones(len(converted.points), dtype=np.int_)
    return converted


def _bounding_box(
    *, shape: Shape, image_size: tuple[int, int] | None
) -> npt.NDArray[np.float64]:
    box = _unclipped_bounding_box(shape=shape)
    # The canvas takes coordinates up to the image's width and height.
    return box if image_size is None else np.clip(box, 0, image_size)


def _unclipped_bounding_box(*, shape: Shape) -> npt.NDArray[np.float64]:
    if shape.shape_type == "circle":
        center, edge = shape.points
        radius = np.linalg.norm(edge - center)
        return np.array([center - radius, center + radius])
    if shape.shape_type == "mask" and shape.mask is not None:
        # The stored corners frame the array; the box hugs its pixels.
        (ys,) = np.nonzero(shape.mask.any(axis=1))
        (xs,) = np.nonzero(shape.mask.any(axis=0))
        if len(xs) == 0:
            return np.zeros((2, 2))
        origin = shape.points[0]
        return origin + np.array([[xs[0], ys[0]], [xs[-1], ys[-1]]])
    return np.array([shape.points.min(axis=0), shape.points.max(axis=0)])
