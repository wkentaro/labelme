from __future__ import annotations

import math
from typing import Final


def compute_circumcircle(
    *,
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> tuple[tuple[float, float], float] | None:
    """Compute the center and radius of the circumcircle defined by three points.

    Returns ((center_x, center_y), radius) or None if the points are collinear
    or nearly collinear.
    """
    COLLINEAR_EPSILON: Final[float] = 1e-9

    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    d = 2.0 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < COLLINEAR_EPSILON:
        return None
    sq1 = x1 * x1 + y1 * y1
    sq2 = x2 * x2 + y2 * y2
    sq3 = x3 * x3 + y3 * y3
    xc = (sq1 * (y2 - y3) + sq2 * (y3 - y1) + sq3 * (y1 - y2)) / d
    yc = (sq1 * (x3 - x2) + sq2 * (x1 - x3) + sq3 * (x2 - x1)) / d
    radius = math.hypot(x1 - xc, y1 - yc)
    return ((xc, yc), radius)


def circle_from_three_points(
    *,
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Compute standard circle points (center, edge) from three points.

    Returns ((center_x, center_y), (edge_x, edge_y)) or None if points are collinear.
    """
    res = compute_circumcircle(p1=p1, p2=p2, p3=p3)
    if res is None:
        return None
    (xc, yc), radius = res
    return ((xc, yc), (xc + radius, yc))
