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

# Targets missing here are listed in the menu but not convertible yet.
_SOURCES: Final[dict[ConvertTarget, frozenset[ShapeType]]] = {
    "polygon": frozenset({"rectangle", "oriented_rectangle", "circle", "linestrip"}),
    "rectangle": frozenset(
        {"polygon", "oriented_rectangle", "circle", "linestrip", "mask"}
    ),
    "line": frozenset({"linestrip"}),
    "linestrip": frozenset({"polygon", "line"}),
}

# Routes with more than one possible result: the user picks a Polygon Detail.
# The rest have one result, so they convert without asking.
_DETAIL_ROUTES: Final[frozenset[tuple[ShapeType, ConvertTarget]]] = frozenset(
    {("circle", "polygon")}
)


def conversion_needs_detail(*, shapes: list[Shape], target: ConvertTarget) -> bool:
    return any((s.shape_type, target) in _DETAIL_ROUTES for s in shapes)


def convert_blocker(
    *,
    shapes: list[Shape],
    target: ConvertTarget,
    image_size: tuple[int, int] | None = None,
) -> ConvertBlocker | None:
    # Shapes already of the target kind are left as they are, so Select All
    # can bring every shape to one kind. Ordered by what the user fixes first,
    # like merge_blocker: a locked point reports "wrong_type", since
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
    # A box, or a circle's polygon, is clipped to the image, which can leave
    # nothing of it.
    if target == "rectangle" and any(
        np.any(box[1] <= box[0])
        for box in (_bounding_box(shape=s, image_size=image_size) for s in sources)
    ):
        return "no_area"
    if target == "polygon" and any(
        not _circle_polygon_has_area(shape=s, image_size=image_size)
        for s in sources
        if s.shape_type == "circle"
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
    detail: int | None = None,
) -> Shape:
    # image_size (width, height) keeps new points inside the image, for when
    # out-of-bounds points are off (ADR 0004): a circle can overhang it.
    if convert_blocker(shapes=[shape], target=target, image_size=image_size):
        raise ValueError(f"cannot convert {shape.shape_type} to {target}")
    if detail is None and conversion_needs_detail(shapes=[shape], target=target):
        raise ValueError(f"converting {shape.shape_type} to {target} needs detail")
    converted = shape.copy()
    converted.shape_type = target
    converted.mask = None
    if target == "rectangle":
        converted.points = _bounding_box(shape=shape, image_size=image_size)
    elif shape.shape_type == "rectangle":
        (x0, y0), (x1, y1) = shape.points
        converted.points = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
    elif shape.shape_type == "circle":
        # Deferred: _automation imports _shape, and owns the detail curve.
        from .._automation import compute_polygon_from_circle  # noqa: PLC0415

        assert detail is not None
        center, edge = shape.points
        # A vertex aimed at the image keeps a circle that only overhangs it
        # with an area inside, however few vertices the detail gives.
        toward = (
            np.zeros(2)
            if image_size is None
            else np.clip(center, 0, image_size) - center
        )
        points = compute_polygon_from_circle(
            center=center,
            radius=float(np.linalg.norm(edge - center)),
            detail=detail,
            start_angle=float(np.arctan2(toward[1], toward[0])),
        )
        converted.points = (
            points
            if image_size is None
            else _clip_polygon(points=points, image_size=image_size)
        )
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


def _circle_polygon_has_area(
    *, shape: Shape, image_size: tuple[int, int] | None
) -> bool:
    # The polygon holds the segment from the center to its vertex aimed at
    # the image, which enters the image whenever the circle does.
    center, edge = shape.points
    nearest = center if image_size is None else np.clip(center, 0, image_size)
    return bool(np.linalg.norm(center - nearest) < np.linalg.norm(edge - center))


def _clip_polygon(
    *, points: npt.NDArray[np.float64], image_size: tuple[int, int]
) -> npt.NDArray[np.float64]:
    # Sutherland-Hodgman against each image edge: an edge crossing the border
    # ends where it crosses, so the polygon keeps its area inside the image.
    # sign makes the distance from each edge positive inside the image.
    for axis, bound, sign in (
        (0, 0.0, 1.0),
        (0, float(image_size[0]), -1.0),
        (1, 0.0, 1.0),
        (1, float(image_size[1]), -1.0),
    ):
        # A vertex a rounding error off the border, like sin(pi), is on it:
        # 1e-6 px is far below what an edit can pick, far above the error.
        points = points.copy()
        on_border = np.abs(points[:, axis] - bound) < 1e-6  # noqa: PLR2004
        points[on_border, axis] = bound
        clipped: list[npt.NDArray[np.float64]] = []
        for start, end in zip(points, np.roll(points, -1, axis=0), strict=True):
            start_inside = sign * (start[axis] - bound)
            end_inside = sign * (end[axis] - bound)
            if start_inside >= 0:
                clipped.append(start)
            # Only a strict crossing adds a point: a vertex on the border is
            # already kept, and adding it again would leave a hidden corner.
            if start_inside * end_inside < 0:
                t = start_inside / (start_inside - end_inside)
                clipped.append(start + t * (end - start))
        points = np.array(clipped)
    return points
