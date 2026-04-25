from __future__ import annotations

from typing import Final

import pytest
from PyQt5 import QtGui
from PyQt5.QtCore import QPointF
from pytestqt.qtbot import QtBot

from labelme.widgets.canvas import Canvas
from labelme.widgets.canvas import _compute_intersection_edges_image

_WIDTH: Final = 100
_HEIGHT: Final = 50


@pytest.fixture()
def canvas(qtbot: QtBot) -> Canvas:
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
def test_is_out_of_pixmap(canvas: Canvas, point: QPointF, is_outside: bool) -> None:
    assert canvas.is_out_of_pixmap(point) is is_outside


@pytest.mark.gui
@pytest.mark.parametrize(
    ("p1", "p2", "pt_intersection"),
    [
        (
            pt_center := QPointF(_WIDTH / 2, _HEIGHT / 2),
            QPointF(_WIDTH + 50, _HEIGHT / 2),  # to the right
            QPointF(_WIDTH, _HEIGHT / 2),  # right edge
        ),
        (
            pt_center,
            QPointF(_WIDTH / 2, -10),  # to the top
            QPointF(_WIDTH / 2, 0),  # top edge
        ),
        (
            pt_center,
            QPointF(-10, _HEIGHT / 2),  # to the left
            QPointF(0, _HEIGHT / 2),  # left edge
        ),
        (
            pt_center,
            QPointF(_WIDTH / 2, _HEIGHT + 30),  # to the bottom
            QPointF(_WIDTH / 2, _HEIGHT),  # bottom edge
        ),
        (
            QPointF(0, _HEIGHT / 2),  # on left edge
            QPointF(-5, _HEIGHT / 2),  # further left
            QPointF(0, _HEIGHT / 2),  # stays on left edge
        ),
        (
            QPointF(_WIDTH / 2, 0),  # on top edge
            QPointF(_WIDTH / 2, -5),  # further up
            QPointF(_WIDTH / 2, 0),  # stays on top edge
        ),
        (
            QPointF(0, _HEIGHT / 2),  # on left edge
            QPointF(-5, _HEIGHT / 2 + 10),  # further left and down
            QPointF(0, _HEIGHT / 2 + 10),  # slides down along left edge
        ),
        (
            QPointF(0, 0),  # top-left corner
            QPointF(-5, -5),  # diagonally out
            QPointF(0, 0),  # stays at corner
        ),
        (
            QPointF(_WIDTH, _HEIGHT),  # bottom-right corner
            QPointF(_WIDTH + 5, _HEIGHT + 5),  # diagonally out
            QPointF(_WIDTH, _HEIGHT),  # stays at corner
        ),
    ],
)
def test_intersectionPoint(
    canvas: Canvas, p1: QPointF, p2: QPointF, pt_intersection: QPointF
) -> None:
    assert (
        _compute_intersection_edges_image(p1, p2, image_size=canvas.pixmap.size())
        == pt_intersection
    )
