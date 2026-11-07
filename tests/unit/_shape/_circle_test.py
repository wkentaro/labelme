from __future__ import annotations

import math

import pytest

from labelme._shape import circle_from_three_points
from labelme._shape import compute_circumcircle


def test_compute_circumcircle_unit_circle() -> None:
    p1 = (1.0, 0.0)
    p2 = (0.0, 1.0)
    p3 = (-1.0, 0.0)
    res = compute_circumcircle(p1=p1, p2=p2, p3=p3)
    assert res is not None
    center, radius = res
    assert pytest.approx(center[0], abs=1e-7) == 0.0
    assert pytest.approx(center[1], abs=1e-7) == 0.0
    assert pytest.approx(radius, abs=1e-7) == 1.0


def test_compute_circumcircle_arbitrary_circle() -> None:
    cx, cy, r = 12.5, 45.0, 8.0
    p1 = (cx + r * math.cos(0.2), cy + r * math.sin(0.2))
    p2 = (cx + r * math.cos(2.1), cy + r * math.sin(2.1))
    p3 = (cx + r * math.cos(4.5), cy + r * math.sin(4.5))

    res = compute_circumcircle(p1=p1, p2=p2, p3=p3)
    assert res is not None
    center, radius = res
    assert pytest.approx(center[0], abs=1e-5) == cx
    assert pytest.approx(center[1], abs=1e-5) == cy
    assert pytest.approx(radius, abs=1e-5) == r


def test_compute_circumcircle_collinear_returns_none() -> None:
    p1 = (0.0, 0.0)
    p2 = (1.0, 1.0)
    p3 = (2.0, 2.0)
    assert compute_circumcircle(p1=p1, p2=p2, p3=p3) is None


def test_compute_circumcircle_coincident_points_returns_none() -> None:
    p1 = (5.0, 5.0)
    p2 = (5.0, 5.0)
    p3 = (10.0, 10.0)
    assert compute_circumcircle(p1=p1, p2=p2, p3=p3) is None


def test_circle_from_three_points_returns_two_points() -> None:
    p1 = (0.0, 2.0)
    p2 = (2.0, 0.0)
    p3 = (0.0, -2.0)
    res = circle_from_three_points(p1=p1, p2=p2, p3=p3)
    assert res is not None
    (cx, cy), (ex, ey) = res
    assert pytest.approx(cx, abs=1e-7) == 0.0
    assert pytest.approx(cy, abs=1e-7) == 0.0
    assert pytest.approx(ex, abs=1e-7) == 2.0
    assert pytest.approx(ey, abs=1e-7) == 0.0
    # Distance between center and edge point equals radius
    assert pytest.approx(math.hypot(ex - cx, ey - cy), abs=1e-7) == 2.0


def test_circle_from_three_points_collinear_returns_none() -> None:
    assert circle_from_three_points(p1=(0.0, 0.0), p2=(1.0, 0.0), p3=(2.0, 0.0)) is None
