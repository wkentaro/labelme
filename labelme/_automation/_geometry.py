from __future__ import annotations

from typing import NamedTuple

import numpy as np
import scipy.spatial
import skimage
from loguru import logger
from numpy.typing import NDArray

from labelme._shape import Shape


class Circle(NamedTuple):
    cx: float
    cy: float
    radius: float


def shape_to_xyxy_bbox(*, shape: Shape) -> NDArray[np.float32] | None:
    """Returns None only when a supported shape is mid-draw (too few points);
    raises ValueError for shape types that have no bbox interpretation.
    """
    if shape.shape_type == "circle":
        if len(shape.points) != 2:
            return None
        center, edge = shape.points
        radius = float(np.linalg.norm(edge - center))
        return np.array(
            [
                center[0] - radius,
                center[1] - radius,
                center[0] + radius,
                center[1] + radius,
            ],
            dtype=np.float32,
        )
    minimum_points_by_shape_type = {
        "rectangle": 2,
        "mask": 2,
        "polygon": 3,
        "oriented_rectangle": 4,
    }
    if shape.shape_type not in minimum_points_by_shape_type:
        raise ValueError(f"Unsupported shape_type: {shape.shape_type!r}")
    if len(shape.points) < minimum_points_by_shape_type[shape.shape_type]:
        return None
    xmin, ymin = shape.points.min(axis=0)
    xmax, ymax = shape.points.max(axis=0)
    return np.array([xmin, ymin, xmax, ymax], dtype=np.float32)


def compute_circle_from_mask(mask: NDArray[np.bool_]) -> Circle | None:
    if not mask.any():
        return None
    ys, xs = np.nonzero(mask)
    # Area-equivalent radius: matches the mask's pixel area, not its extent.
    # For elongated or sparse masks the resulting circle may be smaller than
    # the tightest enclosing one.
    return Circle(
        cx=float(xs.mean()),
        cy=float(ys.mean()),
        radius=float(np.sqrt(mask.sum() / np.pi)),
    )


def compute_oriented_rectangle_from_mask(
    mask: NDArray[np.bool_],
) -> NDArray[np.float32] | None:
    if not mask.any():
        return None
    ys, xs = np.nonzero(mask)
    if len(xs) < 3:
        return None
    points = np.stack([xs, ys], axis=1).astype(np.float64)
    try:
        # Qhull returns 2D hull vertices in CCW order, which the rotating
        # calipers loop below relies on for the right-handed perpendicular.
        hull_indices = scipy.spatial.ConvexHull(points=points).vertices
    except scipy.spatial.QhullError:
        # All pixels are collinear, so no rectangle can be fit; let callers
        # fall back to the axis-aligned bbox.
        return None
    return _min_area_rect(hull=points[hull_indices]).astype(np.float32)


def _min_area_rect(hull: NDArray[np.float64]) -> NDArray[np.float64]:
    # Rotating calipers: the minimum-area enclosing rectangle must have one
    # side flush with an edge of the convex hull. Try each hull edge as the
    # rect orientation and keep the smallest-area candidate.
    best_area = float("inf")
    best_corners: NDArray[np.float64] | None = None
    n = len(hull)
    for i in range(n):
        edge = hull[(i + 1) % n] - hull[i]
        length = float(np.linalg.norm(edge))
        if length == 0:
            continue
        u = edge / length
        perp = np.array([-u[1], u[0]])
        u_coords = hull @ u
        p_coords = hull @ perp
        u_min, u_max = float(u_coords.min()), float(u_coords.max())
        p_min, p_max = float(p_coords.min()), float(p_coords.max())
        u_extent = u_max - u_min
        p_extent = p_max - p_min
        area = u_extent * p_extent
        if area >= best_area:
            continue
        best_area = area
        center = (u_min + u_max) / 2 * u + (p_min + p_max) / 2 * perp
        if u_extent >= p_extent:
            long_axis, half_long, half_short = u, u_extent / 2, p_extent / 2
        else:
            long_axis, half_long, half_short = perp, p_extent / 2, u_extent / 2
        # Pin the long axis to the right half-plane (or to the lower
        # half-plane when it is exactly vertical) so the corner sequence is
        # platform-independent.
        if long_axis[0] < 0 or (long_axis[0] == 0 and long_axis[1] < 0):
            long_axis = -long_axis
        # Right-handed perpendicular yields a deterministic corner traversal:
        # p0 → p1 along the long axis, then p1 → p2 along the short axis.
        short_axis = np.array([-long_axis[1], long_axis[0]])
        best_corners = np.array(
            [
                center - long_axis * half_long - short_axis * half_short,
                center + long_axis * half_long - short_axis * half_short,
                center + long_axis * half_long + short_axis * half_short,
                center - long_axis * half_long + short_axis * half_short,
            ]
        )
    # Callers filter hulls with fewer than three distinct points, so the loop
    # above always finds at least one positive-length edge.
    assert best_corners is not None
    return best_corners


def _get_contour_length(contour: NDArray[np.float32]) -> float:
    contour_start: NDArray[np.float32] = contour
    contour_end: NDArray[np.float32] = np.r_[contour[1:], contour[0:1]]
    return np.linalg.norm(contour_end - contour_start, axis=1).sum()


def compute_polygon_from_mask(mask: NDArray[np.bool_]) -> NDArray[np.float32]:
    contours: NDArray[np.float32] = skimage.measure.find_contours(
        np.pad(mask, pad_width=1)
    )
    if len(contours) == 0:
        logger.warning("No contour found, so returning empty polygon.")
        return np.empty((0, 2), dtype=np.float32)

    contour: NDArray[np.float32] = max(contours, key=_get_contour_length)
    POLYGON_APPROX_TOLERANCE: float = 0.004
    polygon: NDArray[np.float32] = skimage.measure.approximate_polygon(
        coords=contour,
        tolerance=np.ptp(contour, axis=0).max() * POLYGON_APPROX_TOLERANCE,
    )
    polygon = np.clip(polygon, (0, 0), (mask.shape[0] - 1, mask.shape[1] - 1))
    polygon = polygon[:-1]  # drop last point that is duplicate of first point

    return polygon[:, ::-1]  # yx -> xy
