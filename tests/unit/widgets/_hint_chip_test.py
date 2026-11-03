from __future__ import annotations

from typing import Final

import pytest
from PySide6 import QtGui
from PySide6.QtCore import QRectF

from labelme._widgets._hint_chip import HintItem
from labelme._widgets._hint_chip import place_hint_chip

_ROWS: Final = [[HintItem("Add", key="Enter"), HintItem("Discard", key="Esc")]]
_BOUNDS: Final = QRectF(0, 0, 400, 300)


@pytest.mark.gui
@pytest.mark.usefixtures("qapp")
@pytest.mark.parametrize(
    ("anchor", "where"),
    [
        (QRectF(150, 50, 100, 100), "below"),
        (QRectF(150, 180, 100, 100), "above"),
        (QRectF(150, 10, 100, 280), "inside"),
    ],
)
def test_place_hint_chip_prefers_below_then_above_then_inside(
    *, anchor: QRectF, where: str
) -> None:
    rect = place_hint_chip(
        rows=_ROWS, font=QtGui.QFont(), anchor=anchor, bounds=_BOUNDS
    )

    assert _BOUNDS.contains(rect)
    assert rect.center().x() == pytest.approx(anchor.center().x())
    if where == "below":
        assert rect.top() > anchor.bottom()
    elif where == "above":
        assert rect.bottom() < anchor.top()
    else:
        assert rect.bottom() < _BOUNDS.bottom()
        assert anchor.intersects(rect)


@pytest.mark.gui
@pytest.mark.usefixtures("qapp")
def test_place_hint_chip_stays_inside_the_side_edges() -> None:
    rect = place_hint_chip(
        rows=_ROWS, font=QtGui.QFont(), anchor=QRectF(0, 50, 10, 10), bounds=_BOUNDS
    )

    assert rect.left() > _BOUNDS.left()
