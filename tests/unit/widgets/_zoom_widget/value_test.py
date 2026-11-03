from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._widgets._zoom_widget import ZoomWidget


@pytest.fixture
def widget(*, qtbot: QtBot) -> ZoomWidget:
    zoom_widget = ZoomWidget()
    qtbot.addWidget(zoom_widget)
    return zoom_widget


def test_zoom_widget_defaults_to_100(*, widget: ZoomWidget) -> None:
    assert widget.value() == 100.0
    assert widget.text() == "100%"


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (1.234, "1.23%"),
        (1.5, "1.5%"),
        (12.34, "12.3%"),
        (50, "50%"),
        (188.4, "188%"),
        (1000, "1000%"),
    ],
)
def test_zoom_widget_shows_three_significant_digits(
    *, widget: ZoomWidget, value: float, text: str
) -> None:
    widget.setValue(value)
    assert widget.text() == text


def test_zoom_widget_keeps_the_exact_value(*, widget: ZoomWidget) -> None:
    widget.setValue(1.234567)
    assert widget.value() == 1.234567
    assert widget.scale == pytest.approx(0.01234567)


def test_zoom_widget_clamps_to_range(*, widget: ZoomWidget) -> None:
    widget.setValue(10000)
    assert widget.value() == 1000
    widget.setValue(0)
    assert widget.value() == 1.0


def test_enter_on_unedited_text_keeps_the_exact_value(
    *, qtbot: QtBot, widget: ZoomWidget
) -> None:
    widget.setValue(188.4)
    with qtbot.assertNotEmitted(widget.valueChanged):
        qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == 188.4


def test_typed_value_applies_on_enter_only(*, qtbot: QtBot, widget: ZoomWidget) -> None:
    widget.lineEdit().selectAll()
    with qtbot.assertNotEmitted(widget.valueChanged):
        qtbot.keyClicks(widget, "125.5")
    with qtbot.waitSignal(widget.valueChanged):
        qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == 125.5


def test_invalid_text_restores_the_value(*, qtbot: QtBot, widget: ZoomWidget) -> None:
    widget.setValue(76.24)
    widget.lineEdit().selectAll()
    qtbot.keyClicks(widget, "0")
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == 76.24
    assert widget.text() == "76.2%"


def test_steps_are_multiplicative(*, qtbot: QtBot, widget: ZoomWidget) -> None:
    widget.setValue(10)
    qtbot.keyClick(widget, Qt.Key.Key_Up)
    assert widget.value() == pytest.approx(11)
    qtbot.keyClick(widget, Qt.Key.Key_Down)
    assert widget.value() == pytest.approx(10)
