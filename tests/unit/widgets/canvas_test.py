from __future__ import annotations

from typing import Final

import pytest
from PyQt5 import QtGui
from PyQt5.QtCore import QPointF

from labelme.shape import Shape
from labelme.widgets.canvas import Canvas, CanvasMode

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
    ],
)
def test_intersectionPoint(
    canvas: Canvas, p1: QPointF, p2: QPointF, pt_intersection: QPointF
):
    assert canvas.intersectionPoint(p1, p2) == pt_intersection


@pytest.mark.gui
@pytest.mark.parametrize(
    ("create_mode", "num_points", "expect_finish_hint"),
    [
        # polygon: no hint with < 3 points
        ("polygon", 0, False),
        ("polygon", 2, False),
        # polygon: finish hint appears at ≥ 3 points
        ("polygon", 3, True),
        ("polygon", 5, True),
        # linestrip: no hint with < 3 points
        ("linestrip", 1, False),
        ("linestrip", 2, False),
        # linestrip: finish hint appears at ≥ 3 points
        ("linestrip", 3, True),
        # other modes: never show finish hint
        ("line", 1, False),
        ("circle", 1, False),
        ("rectangle", 1, False),
    ],
)
def test_get_create_mode_message_finish_hint(
    canvas: Canvas,
    create_mode: str,
    num_points: int,
    expect_finish_hint: bool,
):
    """Verify that a double-click/Enter finish hint appears when ≥ 3 points exist."""
    canvas.mode = CanvasMode.CREATE
    canvas.createMode = create_mode

    if num_points > 0:
        canvas.current = Shape(shape_type=create_mode)
        for i in range(num_points):
            canvas.current.addPoint(QPointF(float(i * 10), float(i * 10)))
    else:
        canvas.current = None

    msg = canvas._get_create_mode_message()
    has_finish_hint = "double-click" in msg.lower() or "to finish" in msg.lower()
    assert has_finish_hint is expect_finish_hint, (
        f"Mode={create_mode!r}, points={num_points}: "
        f"expected finish_hint={expect_finish_hint}, got message={msg!r}"
    )
