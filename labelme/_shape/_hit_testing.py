from __future__ import annotations

import numpy as np
import numpy.typing as npt

from ._model import CIRCLE_POINT_COUNT
from ._model import Shape
from ._oriented_rectangle import get_rotation_handles
from ._oriented_rectangle import is_full_oriented_rectangle
from ._oriented_rectangle import oriented_rectangle_arrow_points


def _find_closest_index_within(
    *, distances: npt.NDArray[np.float64], epsilon: float
) -> int | None:
    closest = int(np.argmin(distances))
    return closest if distances[closest] <= epsilon else None


def nearest_vertex_index(
    *,
    shape: Shape,
    point: npt.NDArray[np.float64],
    image_epsilon: float,
) -> int | None:
    # A mask's bbox corners are derived from its bitmap, and a point shape's
    # single point *is* the shape, not a draggable vertex; neither exposes one.
    if shape.shape_type in ("mask", "point") or len(shape.points) == 0:
        return None
    distances = np.linalg.norm(shape.points - point, axis=1)
    return _find_closest_index_within(distances=distances, epsilon=image_epsilon)


def nearest_edge_index(
    *,
    shape: Shape,
    point: npt.NDArray[np.float64],
    image_epsilon: float,
) -> int | None:
    if len(shape.points) == 0:
        return None
    # Edge i runs from points[i - 1] to points[i] (so edge 0 is the segment
    # that closes a polygon from its last point back to its first).
    edge_starts = np.roll(shape.points, shift=1, axis=0)
    edge_vectors = shape.points - edge_starts
    squared_lengths = np.einsum("ij,ij->i", edge_vectors, edge_vectors)
    # A repeated point yields a zero-length edge; substitute 1 as the divisor
    # so its (irrelevant) projection stays finite instead of NaN.
    safe_lengths = np.where(squared_lengths == 0, 1.0, squared_lengths)
    projection_t = np.clip(
        np.einsum("ij,ij->i", point - edge_starts, edge_vectors) / safe_lengths,
        0.0,
        1.0,
    )
    closest_points = edge_starts + projection_t[:, None] * edge_vectors
    distances = np.linalg.norm(point - closest_points, axis=1)
    if shape.shape_type == "linestrip":
        # Edge 0 above is the wrap-around segment np.roll manufactures from the
        # last point back to the first. A linestrip is open, so that segment
        # is never drawn and must never be picked as a hit.
        distances[0] = np.inf
    return _find_closest_index_within(distances=distances, epsilon=image_epsilon)


def nearest_rotation_point_index(
    *,
    shape: Shape,
    point: npt.NDArray[np.float64],
    image_epsilon: float,
) -> int | None:
    if not is_full_oriented_rectangle(shape=shape):
        return None
    distances = np.linalg.norm(
        get_rotation_handles(points=shape.points) - point, axis=1
    )
    return _find_closest_index_within(distances=distances, epsilon=image_epsilon)


def image_extent(
    *, shape: Shape
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    # The corners of a box, in image space, that holds everything the shape
    # draws and everything a pointer can hit: its points, a circle's rim, an
    # oriented rectangle's arrow and a mask's pixels. The shape has points.
    points = shape.points
    lo = points.min(axis=0)
    hi = points.max(axis=0)
    if shape.shape_type == "circle" and len(points) == CIRCLE_POINT_COUNT:
        radius = float(np.linalg.norm(points[1] - points[0]))
        lo = np.minimum(lo, points[0] - radius)
        hi = np.maximum(hi, points[0] + radius)
    elif is_full_oriented_rectangle(shape=shape):
        arrow = oriented_rectangle_arrow_points(shape=shape)
        lo = np.minimum(lo, arrow.min(axis=0))
        hi = np.maximum(hi, arrow.max(axis=0))
    if shape.mask is not None:
        # The contour is traced between pixel centers, half a pixel outside
        # the mask's first row and column.
        lo = np.minimum(lo, points[0] - 0.5)
        hi = np.maximum(hi, points[0] + shape.mask.shape[::-1])
    return lo, hi
