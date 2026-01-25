from PyQt5.QtCore import QPointF

from labelme.utils.qt import distancetoline


def test_distancetoline():
    line = (QPointF(0, 0), QPointF(10, 0))

    assert distancetoline(QPointF(5, 0), line) == 0
    assert distancetoline(QPointF(5, 5), line) == 5
    assert distancetoline(QPointF(0, 0), line) == 0
    assert distancetoline(QPointF(-5, 0), line) == 5
    assert distancetoline(QPointF(15, 0), line) == 5
