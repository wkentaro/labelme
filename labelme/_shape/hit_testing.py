from __future__ import annotations

import numpy as np
import numpy.typing as npt

from .model import Shape
from .oriented_rectangle import _get_rotation_handles
from .oriented_rectangle import _is_full_oriented_rectangle


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
    if not _is_full_oriented_rectangle(shape):
        return None
    distances = np.linalg.norm(_get_rotation_handles(shape.points) - point, axis=1)
    return _find_closest_index_within(distances=distances, epsilon=image_epsilon)
