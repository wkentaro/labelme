from __future__ import annotations

from typing import Final

import pytest
from PyQt5 import QtGui
from PyQt5.QtCore import QPointF

from labelme.widgets.canvas import Canvas

_WIDTH: Final = 100
_HEIGHT: Final = 50


@pytest.fixture()
def canvas(qtbot) -> Canvas:
    canvas = Canvas()
    canvas.pixmap = QtGui.QPixmap(_WIDTH, _HEIGHT)
    qtbot.addWidget(canvas)
    return canvas


@pytest.mark.gui
@pytest.mark.parametrize(
    ("point", "is_outside"),
    [
        (QPointF(_WIDTH / 2, _HEIGHT / 2), False),
        (QPointF(0, 0), False),
        (QPointF(_WIDTH, _HEIGHT), False),
        (QPointF(_WIDTH, _HEIGHT / 2), False),
        (QPointF(_WIDTH / 2, _HEIGHT), False),
        (QPointF(_WIDTH + 0.1, _HEIGHT / 2), True),
        (QPointF(_WIDTH / 2, _HEIGHT + 0.1), True),
        (QPointF(-0.1, _HEIGHT / 2), True),
        (QPointF(_WIDTH / 2, -0.1), True),
    ],
)
def test_outOfPixmap(canvas: Canvas, point: QPointF, is_outside: bool):
    assert canvas.outOfPixmap(point) is is_outside
