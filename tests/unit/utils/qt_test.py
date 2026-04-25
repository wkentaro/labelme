from __future__ import annotations

from PyQt5.QtCore import QPointF

from labelme.utils.qt import distance_to_line


def test_distance_to_line() -> None:
    line = (QPointF(0, 0), QPointF(10, 0))

    assert distance_to_line(QPointF(5, 0), line) == 0
    assert distance_to_line(QPointF(5, 5), line) == 5
    assert distance_to_line(QPointF(0, 0), line) == 0
    assert distance_to_line(QPointF(-5, 0), line) == 5
    assert distance_to_line(QPointF(15, 0), line) == 5
