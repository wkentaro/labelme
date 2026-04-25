from __future__ import annotations

import math

import pytest
from PyQt5.QtCore import QPointF

from labelme.utils.qt import angleRad
from labelme.utils.qt import distancetoline
from labelme.utils.qt import projectPointAtRightAngle
from labelme.utils.qt import projectPointOnLine


def test_distancetoline() -> None:
    line = (QPointF(0, 0), QPointF(10, 0))

    assert distancetoline(QPointF(5, 0), line) == 0
    assert distancetoline(QPointF(5, 5), line) == 5
    assert distancetoline(QPointF(0, 0), line) == 0
    assert distancetoline(QPointF(-5, 0), line) == 5
    assert distancetoline(QPointF(15, 0), line) == 5


@pytest.mark.parametrize(
    "p2, expected",
    [
        (QPointF(5.0, 0.0), 0.0),
        (QPointF(0.0, 5.0), math.pi / 2),
        (QPointF(-5.0, 0.0), math.pi),
        (QPointF(0.0, -5.0), -math.pi / 2),
    ],
)
def test_angle_rad(p2: QPointF, expected: float) -> None:
    assert angleRad(p1=QPointF(0.0, 0.0), p2=p2) == pytest.approx(expected)


def test_angle_rad_flip_y_inverts_sign() -> None:
    p1, p2 = QPointF(0.0, 0.0), QPointF(3.0, 4.0)
    assert angleRad(p1=p1, p2=p2, flip_y=True) == pytest.approx(-angleRad(p1=p1, p2=p2))


@pytest.mark.parametrize(
    "p3, expected",
    [
        (QPointF(15.0, 7.0), (10.0, 7.0)),  # off-axis to the right
        (QPointF(10.0, 7.0), (10.0, 7.0)),  # already on perpendicular
        (QPointF(0.0, 7.0), (10.0, 7.0)),  # left of base, height preserved
    ],
)
def test_project_point_at_right_angle(
    p3: QPointF, expected: tuple[float, float]
) -> None:
    projected = projectPointAtRightAngle(
        p1=QPointF(0.0, 0.0), p2=QPointF(10.0, 0.0), p3=p3
    )
    assert (projected.x(), projected.y()) == pytest.approx(expected)


@pytest.mark.parametrize(
    "p3, expected",
    [
        (QPointF(4.0, 0.0), (4.0, 0.0)),  # collinear is identity
        (QPointF(4.0, 7.0), (4.0, 0.0)),  # off-axis drops perpendicular
    ],
)
def test_project_point_on_line(p3: QPointF, expected: tuple[float, float]) -> None:
    projected = projectPointOnLine(p1=QPointF(0.0, 0.0), p2=QPointF(10.0, 0.0), p3=p3)
    assert (projected.x(), projected.y()) == pytest.approx(expected)
