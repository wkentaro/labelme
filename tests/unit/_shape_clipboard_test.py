from __future__ import annotations

from PyQt5 import QtCore

from labelme._shape_clipboard import ShapeClipboard
from labelme.shape import Shape


def _make_shape(label: str, x: float, y: float) -> Shape:
    shape = Shape(label=label, shape_type="point")
    shape.add_point(QtCore.QPointF(x, y))
    return shape


def test_paste_returns_independent_copies() -> None:
    clipboard = ShapeClipboard()
    clipboard.store([_make_shape("a", 1.0, 2.0)])

    first = clipboard.paste()
    first[0].label = "mutated"
    first[0].points[0].setX(999.0)

    second = clipboard.paste()
    assert second[0].label == "a"
    assert second[0].points[0].x() == 1.0
    assert first[0] is not second[0]
