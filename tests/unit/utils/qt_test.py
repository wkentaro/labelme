from __future__ import annotations

import math

import pytest
from PyQt5.QtCore import QPointF

from labelme.utils.qt import direction_angle
from labelme.utils.qt import distance_to_line
from labelme.utils.qt import project_point_on_line
from labelme.utils.qt import project_point_on_perpendicular_line


def test_distance_to_line() -> None:
    line = (QPointF(0, 0), QPointF(10, 0))

    assert distance_to_line(QPointF(5, 0), line) == 0
    assert distance_to_line(QPointF(5, 5), line) == 5
    assert distance_to_line(QPointF(0, 0), line) == 0
    assert distance_to_line(QPointF(-5, 0), line) == 5
    assert distance_to_line(QPointF(15, 0), line) == 5


@pytest.mark.parametrize(
    "end, expected",
    [
        ((5.0, 0.0), 0.0),
        ((0.0, 5.0), math.pi / 2),
        ((-5.0, 0.0), math.pi),
        ((0.0, -5.0), -math.pi / 2),
    ],
)
def test_direction_angle(end: tuple[float, float], expected: float) -> None:
    assert direction_angle(start=(0.0, 0.0), end=end) == pytest.approx(expected)


@pytest.mark.parametrize(
    "point, expected",
    [
        (QPointF(15.0, 7.0), (10.0, 7.0)),
        (QPointF(10.0, 7.0), (10.0, 7.0)),
        (QPointF(0.0, 7.0), (10.0, 7.0)),
    ],
)
def test_project_point_on_perpendicular_line(
    point: QPointF, expected: tuple[float, float]
) -> None:
    projected = project_point_on_perpendicular_line(
        point=point, line_start=QPointF(0.0, 0.0), line_end=QPointF(10.0, 0.0)
    )
    assert (projected.x(), projected.y()) == pytest.approx(expected)


@pytest.mark.parametrize(
    "point, expected",
    [
        (QPointF(4.0, 0.0), (4.0, 0.0)),
        (QPointF(4.0, 7.0), (4.0, 0.0)),
    ],
)
def test_project_point_on_line(point: QPointF, expected: tuple[float, float]) -> None:
    projected = project_point_on_line(
        point=point, line_start=QPointF(0.0, 0.0), line_end=QPointF(10.0, 0.0)
    )
    assert (projected.x(), projected.y()) == pytest.approx(expected)
