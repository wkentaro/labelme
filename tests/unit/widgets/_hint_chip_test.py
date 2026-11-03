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
        (QRectF(150, 700, 100, 100), "inside"),
    ],
)
def test_place_hint_chip_prefers_below_then_above_then_inside(
    *, anchor: QRectF, where: str
) -> None:
    rect, _ = place_hint_chip(
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


@pytest.mark.gui
@pytest.mark.usefixtures("qapp")
def test_place_hint_chip_stays_inside_the_side_edges() -> None:
    rect, _ = place_hint_chip(
        rows=_ROWS, font=QtGui.QFont(), anchor=QRectF(0, 50, 10, 10), bounds=_BOUNDS
    )

    assert rect.left() > _BOUNDS.left()


@pytest.mark.gui
@pytest.mark.usefixtures("qapp")
def test_place_hint_chip_wraps_a_row_that_is_too_wide() -> None:
    # Either item fits alone, but not both on one line.
    rows = [
        *_ROWS,
        [HintItem("Click to include " * 3), HintItem("Click to exclude " * 3)],
    ]
    anchor = QRectF(0, 0, 10, 10)

    wide, wrapped = place_hint_chip(
        rows=rows, font=QtGui.QFont(), anchor=anchor, bounds=QRectF(0, 0, 10_000, 300)
    )
    assert wrapped == [[row] for row in rows]
    narrow = QRectF(0, 0, wide.width() - 1, 300)
    rect, wrapped = place_hint_chip(
        rows=rows, font=QtGui.QFont(), anchor=anchor, bounds=narrow
    )

    assert wrapped == [[_ROWS[0]], [[item] for item in rows[1]]]
    assert narrow.contains(rect)


@pytest.mark.gui
@pytest.mark.usefixtures("qapp")
@pytest.mark.parametrize(
    "text",
    [
        "Drag around one example to find the rest",
        "例を1つドラッグで囲んで残りを探す",
    ],
)
def test_place_hint_chip_wraps_inside_an_item_that_is_too_wide(*, text: str) -> None:
    rows = [[HintItem(text, key="Shift")]]
    anchor = QRectF(0, 0, 10, 10)
    wide, _ = place_hint_chip(
        rows=rows, font=QtGui.QFont(), anchor=anchor, bounds=QRectF(0, 0, 10_000, 300)
    )
    narrow = QRectF(0, 0, wide.width() / 2 + 16, 300)

    rect, lines = place_hint_chip(
        rows=rows, font=QtGui.QFont(), anchor=anchor, bounds=narrow
    )

    assert narrow.contains(rect)
    (row_lines,) = lines
    assert len(row_lines) > 1
    assert row_lines[0][0].key == "Shift"
    pieces = [item.text for line in row_lines for item in line]
    assert " ".join(pieces).replace(" ", "") == text.replace(" ", "")


@pytest.mark.gui
@pytest.mark.usefixtures("qapp")
def test_place_hint_chip_drops_secondary_rows_when_too_short() -> None:
    rows = [*_ROWS, [HintItem("Click to include")], [HintItem("Click to exclude")]]
    anchor = QRectF(0, 0, 10, 10)
    tall, _ = place_hint_chip(
        rows=rows, font=QtGui.QFont(), anchor=anchor, bounds=QRectF(0, 0, 400, 1000)
    )
    short = QRectF(0, 0, 400, tall.height() + 15)

    rect, lines = place_hint_chip(
        rows=rows, font=QtGui.QFont(), anchor=anchor, bounds=short
    )

    assert lines == [[row] for row in rows[:2]]
    assert short.contains(rect)
