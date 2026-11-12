from __future__ import annotations

from typing import Final
from typing import NamedTuple

import numpy as np
import skimage
from loguru import logger
from numpy.typing import NDArray

from .._shape import CIRCLE_POINT_COUNT
from .._shape import MIN_POLYGON_POINT_COUNT
from .._shape import Shape

# Highest value of the mask polygonization detail slider.
_DETAIL_MAX: Final = 100
_FLOAT32_EPS: Final = float(np.finfo(np.float32).eps)


class Circle(NamedTuple):
    cx: float
    cy: float
    radius: float


def round_bbox_to_int(
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
    # None means a supported shape is mid-draw (too few points); shape types
    # with no bbox interpretation raise ValueError.
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
    import scipy.spatial  # noqa: PLC0415 -- deferred: ~160ms, only AI output needs it

    try:
        # Qhull returns 2D hull vertices in CCW order, which the rotating
        # calipers loop below relies on for the right-handed perpendicular.
        hull_indices = scipy.spatial.ConvexHull(points=points).vertices
    except scipy.spatial.QhullError:
        # All pixels are collinear, so no rectangle can be fit; let callers
        # fall back to the axis-aligned bbox.
        return None
    return _min_area_rect(hull=points[hull_indices]).astype(np.float32)


def _min_area_rect(*, hull: NDArray[np.float64]) -> NDArray[np.float64]:
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


def _compute_signed_area(*, points: NDArray[np.float64]) -> float:
    local_points = points - points[0]
    x = local_points[:, 0]
    y = local_points[:, 1]
    return float(
        np.sum(
            x * np.roll(y, shift=-1) - np.roll(x, shift=-1) * y,
        )
        / 2
    )


def _compute_relative_deviation(*, detail: int) -> float:
    # How far a polygon may stray from a shape, as a fraction of the shape's
    # thickness (area / perimeter): the IoU a polygon loses grows with that
    # fraction, so one detail keeps alike any image resolution or shape size.
    # Past 0.15, a circle drops to an octagon (IoU 0.90); up to it, every
    # shape tried keeps an IoU of 0.95 at detail 0. The curve reserves finer
    # control near the detailed end, where small slider changes show most.
    MAX_RELATIVE_DEVIATION: Final = 0.15
    return MAX_RELATIVE_DEVIATION * ((_DETAIL_MAX - detail) / _DETAIL_MAX) ** 1.5


def _compute_mask_deviation(*, detail: int, mask: NDArray[np.bool_]) -> float:
    # A mask's outline is only accurate to half a pixel, so its stair steps go
    # whatever the shape's size: the floor ramps up to half a pixel by detail
    # 80 and is 0 at the exact outline (100).
    if detail >= _DETAIL_MAX:
        return 0.0
    pixel_floor = 0.5 * min(1.0, (_DETAIL_MAX - detail) / 20) ** 1.5
    return max(
        _compute_relative_deviation(detail=detail) * _compute_thickness(mask=mask),
        pixel_floor,
    )


def _compute_thickness(*, mask: NDArray[np.bool_]) -> float:
    # Area / perimeter of each 4-connected land, weighted by area, so specks
    # and pepper noise don't thin a mask out. Counted from pixels rather than
    # traced, since the specks the filter drops can number in the tens of
    # thousands: pixel edges overcount a boundary at random angles by 4 / pi.
    import scipy.ndimage  # noqa: PLC0415 -- deferred: ~140ms, only AI output needs it

    labels, _ = scipy.ndimage.label(mask)
    areas = np.bincount(labels.ravel())[1:]
    padded = np.pad(labels, pad_width=1)
    # Neighboring pixels of two lands are never 4-adjacent, so each pixel edge
    # where the label changes borders exactly one land.
    edges = np.concatenate(
        [
            np.maximum(padded[:, 1:], padded[:, :-1])[padded[:, 1:] != padded[:, :-1]],
            np.maximum(padded[1:], padded[:-1])[padded[1:] != padded[:-1]],
        ]
    )
    perimeters = np.bincount(edges, minlength=len(areas) + 1)[1:] * np.pi / 4
    return float((areas * areas / perimeters).sum() / areas.sum())


def _find_outer_contours(*, mask: NDArray[np.bool_]) -> list[NDArray[np.float64]]:
    # Pad so a region touching the image border still has a background ring to
    # close its contour against; the resulting offset is removed below.
    PAD: Final[int] = 1
    contours = [
        (contour - PAD)[:, ::-1]
        for contour in skimage.measure.find_contours(
            np.pad(mask, pad_width=PAD),
            fully_connected="low",
            positive_orientation="low",
        )
    ]
    # Holes wind the other way; Polygon Shapes have no rings to hold them.
    return [c for c in contours if _compute_signed_area(points=c) > 0]


def _filter_lands_beyond_deviation(
    *,
    mask: NDArray[np.bool_],
    deviation: float,
) -> NDArray[np.bool_]:
    import scipy.ndimage  # noqa: PLC0415 -- deferred: ~140ms, only AI output needs it

    filled = scipy.ndimage.binary_fill_holes(
        mask,
        structure=np.ones((3, 3), dtype=bool),
    )
    # Raster distances start at pixel centers, half a pixel inside the boundary.
    # A pixel survives eroding by a disk of this radius when no background
    # pixel lies within it; the padding is the background around the mask.
    # Squared distances between pixel centers are whole numbers, so rounding
    # recovers them exactly. A distance field costs the same at any radius,
    # where an erosion grows with the disk.
    radius = deviation + 0.5
    # Under a pixel, the disk is the pixel itself and removes nothing.
    if radius < 1:
        return mask
    squared = scipy.ndimage.distance_transform_edt(np.pad(filled, pad_width=1))
    np.square(squared, out=squared)
    np.rint(squared, out=squared)
    eroded = squared[1:-1, 1:-1] > radius**2
    surviving_lands = scipy.ndimage.binary_propagation(eroded, mask=filled)
    return mask & surviving_lands


def _simplify_contours(
    *,
    contours: list[NDArray[np.float64]],
    deviation: float,
    mask_shape: tuple[int, int],
) -> list[NDArray[np.float32]]:
    # Douglas-Peucker takes closed chains, ending where they start.
    smoothed = [
        _smooth_contour(points=points, deviation=deviation) for points in contours
    ]
    simplified = _approximate_polygons(
        chains=[np.vstack([points, points[0]]) for points, _ in smoothed],
        tolerances=[tolerance for _, tolerance in smoothed],
    )
    clipped = [
        _clip_to_mask(points=chain[:-1], mask_shape=mask_shape) for chain in simplified
    ]
    collinear_free = _approximate_polygons(
        chains=[np.vstack([points, points[0]]) for points in clipped],
        tolerances=[_FLOAT32_EPS] * len(clipped),
    )
    return [
        chain[:-1].astype(np.float32)
        for chain in collinear_free
        if len(chain) - 1 >= MIN_POLYGON_POINT_COUNT
    ]


def _smooth_contour(
    *, points: NDArray[np.float64], deviation: float
) -> tuple[NDArray[np.float64], float]:
    # Returns the smoothed points and the tolerance left to simplify them.
    if np.array_equal(points[0], points[-1]):
        points = points[:-1]

    smoothing_sigma = deviation / 2
    simplification_tolerance = deviation
    if smoothing_sigma > 0:
        import scipy.ndimage  # noqa: PLC0415 -- deferred: ~140ms, only AI output needs it

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
    return points, max(simplification_tolerance, _FLOAT32_EPS)


def _clip_to_mask(
    *, points: NDArray[np.float64], mask_shape: tuple[int, int]
) -> NDArray[np.float64]:
    # Clipping can stack vertices on the border; repeats are dropped.
    points = np.clip(points, (0, 0), (mask_shape[1], mask_shape[0]))
    keep = np.r_[True, np.any(np.diff(points, axis=0) != 0, axis=1)]
    return points[keep]


def _approximate_polygons(
    *, chains: list[NDArray[np.float64]], tolerances: list[float]
) -> list[NDArray[np.float64]]:
    # skimage.measure.approximate_polygon (Douglas-Peucker) on every chain at
    # once, with its arithmetic: each round splits every open segment of
    # every chain, so Python loops once per tree level, not once per vertex.
    if not chains:
        return []
    lengths = np.array([len(chain) for chain in chains])
    firsts = np.r_[0, np.cumsum(lengths)[:-1]]
    coords = np.concatenate(chains)
    keep = np.zeros(len(coords), dtype=bool)
    starts, ends = firsts, firsts + lengths - 1
    keep[starts] = keep[ends] = True
    tols = np.asarray(tolerances, dtype=np.float64)
    while True:
        has_inside = ends - starts > 1
        starts, ends, tols = starts[has_inside], ends[has_inside], tols[has_inside]
        if len(starts) == 0:
            break
        counts = ends - starts - 1
        offsets = np.r_[0, np.cumsum(counts)[:-1]]
        segment = np.repeat(np.arange(len(starts)), counts)
        index = starts[segment] + 1 + np.arange(len(segment)) - offsets[segment]
        r0, c0 = coords[starts, 0], coords[starts, 1]
        r1, c1 = coords[ends, 0], coords[ends, 1]
        dr = r1 - r0
        dc = c1 - c0
        angle = -np.arctan2(dr, dc)
        sin, cos = np.sin(angle), np.cos(angle)
        distance = c0 * sin + r0 * cos
        r, c = coords[index, 0], coords[index, 1]
        dr0 = r - r0[segment]
        dc0 = c - c0[segment]
        dr1 = r - r1[segment]
        dc1 = c - c1[segment]
        segment_dr, segment_dc = dr[segment], dc[segment]
        perp = (dr0 * segment_dr + dc0 * segment_dc > 0) & (
            -dr1 * segment_dr - dc1 * segment_dc > 0
        )
        dists = np.where(
            perp,
            np.abs(r * cos[segment] + c * sin[segment] - distance[segment]),
            np.minimum(np.sqrt(dc0**2 + dr0**2), np.sqrt(dc1**2 + dr1**2)),
        )
        farthest = np.maximum.reduceat(dists, offsets)
        split = farthest > tols
        # The first point at the largest distance, as np.argmax picks.
        middles = np.minimum.reduceat(
            np.where(dists == farthest[segment], index, len(coords)), offsets
        )[split]
        keep[middles] = True
        starts = np.r_[starts[split], middles]
        ends = np.r_[middles, ends[split]]
        tols = np.r_[tols[split], tols[split]]
    return [
        coords[first : first + length][keep[first : first + length]]
        for first, length in zip(firsts, lengths, strict=True)
    ]


def compute_polygon_from_circle(
    *,
    center: NDArray[np.floating],
    radius: float,
    detail: int,
    start_angle: float = 0.0,
) -> NDArray[np.float64]:
    # The same detail curve as masks: no edge strays further from the circle
    # than a mask outline of the same thickness may, so the vertex count
    # depends on the detail alone. 12 vertices keep an IoU of 0.95 (an
    # octagon's is 0.90); past 360 more edges no longer show.
    MIN_VERTICES: Final = 12
    MAX_VERTICES: Final = 360
    if not 0 <= detail <= _DETAIL_MAX:
        raise ValueError(f"detail must be between 0 and 100, got {detail}")
    # A circle's area / perimeter is half its radius, so the deviation over
    # the radius is half the relative one.
    relative = _compute_relative_deviation(detail=detail) / 2
    if relative <= 0:
        count = MAX_VERTICES
    else:
        # An edge of a regular n-gon on the circle bulges r(1 - cos(pi/n)) in.
        count = int(np.ceil(np.pi / np.arccos(1 - relative)))
    count = int(np.clip(count, MIN_VERTICES, MAX_VERTICES))
    angles = start_angle + 2 * np.pi * np.arange(count) / count
    return center + radius * np.stack([np.cos(angles), np.sin(angles)], axis=1)


def compute_polygons_from_mask(
    *, mask: NDArray[np.bool_], detail: int = 60
) -> list[NDArray[np.float32]]:
    if not 0 <= detail <= _DETAIL_MAX:
        raise ValueError(f"detail must be between 0 and 100, got {detail}")
    if not mask.any():
        logger.warning("No contour found, so returning no polygons.")
        return []

    deviation = _compute_mask_deviation(detail=detail, mask=mask)
    if deviation > 0:
        mask = _filter_lands_beyond_deviation(mask=mask, deviation=deviation)
        if not mask.any():
            return []
    return _simplify_contours(
        contours=_find_outer_contours(mask=mask),
        deviation=deviation,
        mask_shape=mask.shape,
    )
