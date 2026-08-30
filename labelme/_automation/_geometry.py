from __future__ import annotations

from typing import Final
from typing import NamedTuple

import numpy as np
import scipy.ndimage
import scipy.spatial
import skimage
from loguru import logger
from numpy.typing import NDArray

from .._shape import CIRCLE_POINT_COUNT
from .._shape import MIN_POLYGON_POINT_COUNT
from .._shape import Shape

# Highest value of the mask polygonization detail slider.
_DETAIL_MAX: Final = 100


class Circle(NamedTuple):
    cx: float
    cy: float
    radius: float


def _round_bbox_to_int(
    *,
    bbox: tuple[float, float, float, float] | NDArray[np.floating],
) -> tuple[int, int, int, int]:
    xmin, ymin, xmax, ymax = bbox
    return (
        int(round(float(xmin))),
        int(round(float(ymin))),
        int(round(float(xmax))),
        int(round(float(ymax))),
    )


def shape_to_xyxy_bbox(*, shape: Shape) -> NDArray[np.float32] | None:
    """Returns None only when a supported shape is mid-draw (too few points);
    raises ValueError for shape types that have no bbox interpretation.
    """
    if shape.shape_type == "circle":
        if len(shape.points) != CIRCLE_POINT_COUNT:
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


def compute_circle_from_mask(*, mask: NDArray[np.bool_]) -> Circle | None:
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
    *,
    mask: NDArray[np.bool_],
) -> NDArray[np.float32] | None:
    if not mask.any():
        return None
    ys, xs = np.nonzero(mask)
    if len(xs) < MIN_POLYGON_POINT_COUNT:
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
    return _min_area_rect(points[hull_indices]).astype(np.float32)


def _min_area_rect(hull: NDArray[np.float64], /) -> NDArray[np.float64]:
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


def _compute_signed_area(points: NDArray[np.float64], /) -> float:
    local_points = points - points[0]
    x = local_points[:, 0]
    y = local_points[:, 1]
    return float(
        np.sum(
            x * np.roll(y, shift=-1) - np.roll(x, shift=-1) * y,
        )
        / 2
    )


def _compute_polygon_deviation(*, detail: int) -> float:
    # The default maps to half a pixel; the curve reserves finer control near
    # the detailed end, where small slider changes are most visible.
    detail_loss = (_DETAIL_MAX - detail) / 20
    return 0.5 * detail_loss**1.5


def _filter_lands_beyond_deviation(
    *,
    mask: NDArray[np.bool_],
    deviation: float,
) -> NDArray[np.bool_]:
    filled = scipy.ndimage.binary_fill_holes(
        mask,
        structure=np.ones((3, 3), dtype=bool),
    )
    # Raster distances start at pixel centers, half a pixel inside the boundary.
    radius = deviation + 0.5
    axis = np.arange(-np.ceil(radius), np.ceil(radius) + 1)
    footprint = axis[:, np.newaxis] ** 2 + axis[np.newaxis, :] ** 2 <= radius**2
    eroded = scipy.ndimage.binary_erosion(filled, structure=footprint)
    surviving_lands = scipy.ndimage.binary_propagation(eroded, mask=filled)
    return mask & surviving_lands


def _simplify_contour(
    *,
    contour: NDArray[np.float64],
    detail: int,
    mask_shape: tuple[int, int],
) -> NDArray[np.float32]:
    points = contour[:, ::-1]
    if np.array_equal(points[0], points[-1]):
        points = points[:-1]

    deviation = _compute_polygon_deviation(detail=detail)
    smoothing_sigma = deviation / 2
    simplification_tolerance = deviation
    if smoothing_sigma > 0:
        smoothed = scipy.ndimage.gaussian_filter1d(
            points,
            sigma=smoothing_sigma,
            axis=0,
            mode="wrap",
        )
        smoothing_shift = float(np.linalg.norm(smoothed - points, axis=1).max())
        smoothing_budget = deviation / 2
        # Smoothing moves the boundary before simplification, so its
        # displacement spends part of the same error budget instead of
        # compounding it.
        if smoothing_shift > smoothing_budget:
            smoothed = points + (smoothed - points) * (
                smoothing_budget / smoothing_shift
            )
            smoothing_shift = smoothing_budget
        points = smoothed
        simplification_tolerance -= smoothing_shift

    closed = np.vstack([points, points[0]])
    simplified = skimage.measure.approximate_polygon(
        coords=closed,
        tolerance=max(simplification_tolerance, np.finfo(np.float32).eps),
    )
    if np.array_equal(simplified[0], simplified[-1]):
        simplified = simplified[:-1]
    simplified = np.clip(
        simplified,
        (0, 0),
        (mask_shape[1], mask_shape[0]),
    )
    keep = np.r_[True, np.any(np.diff(simplified, axis=0) != 0, axis=1)]
    simplified = simplified[keep]
    simplified = skimage.measure.approximate_polygon(
        coords=np.vstack([simplified, simplified[0]]),
        tolerance=np.finfo(np.float32).eps,
    )
    return simplified[:-1].astype(np.float32)


def compute_polygons_from_mask(
    *, mask: NDArray[np.bool_], detail: int = 80
) -> list[NDArray[np.float32]]:
    if not 0 <= detail <= _DETAIL_MAX:
        raise ValueError(f"detail must be between 0 and 100, got {detail}")
    if not mask.any():
        logger.warning("No contour found, so returning no polygons.")
        return []

    # Pad so a region touching the image border still has a background ring to
    # close its contour against; the resulting offset is removed below.
    PAD: Final[int] = 1
    deviation = _compute_polygon_deviation(detail=detail)
    if deviation > 0:
        mask = _filter_lands_beyond_deviation(mask=mask, deviation=deviation)
    if not mask.any():
        return []

    contours = skimage.measure.find_contours(
        np.pad(mask, pad_width=PAD),
        fully_connected="low",
        positive_orientation="low",
    )
    polygons: list[NDArray[np.float32]] = []
    for contour in contours:
        contour = contour - PAD
        raw_points = contour[:, ::-1]
        if _compute_signed_area(raw_points) <= 0:
            continue
        polygon = _simplify_contour(
            contour=contour,
            detail=detail,
            mask_shape=mask.shape,
        )
        if len(polygon) >= MIN_POLYGON_POINT_COUNT:
            polygons.append(polygon)
    return polygons
