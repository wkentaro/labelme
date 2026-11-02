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


def test_zoom_widget_accepts_one_decimal(*, widget: ZoomWidget) -> None:
    widget.setValue(150.5)
    assert widget.value() == pytest.approx(150.5)


def test_zoom_widget_rounds_to_one_decimal(*, widget: ZoomWidget) -> None:
    widget.setValue(150.56)
    assert widget.value() == pytest.approx(150.6)


def test_zoom_widget_clamps_to_range(*, widget: ZoomWidget) -> None:
    widget.setValue(10000)
    assert widget.value() == 1000
    widget.setValue(0)
    assert widget.value() == 1.0


def test_zoom_widget_scale_is_percent_as_factor(*, widget: ZoomWidget) -> None:
    widget.setValue(150)
    assert widget.scale == pytest.approx(1.5)


def test_zoom_widget_shows_whole_percent(*, widget: ZoomWidget) -> None:
    widget.setValue(188.4)
    assert widget.text() == "188%"
    assert widget.value() == pytest.approx(188.4)


def test_zoom_widget_enter_keeps_fractional_value(
    *, widget: ZoomWidget, qtbot: QtBot
) -> None:
    widget.setValue(188.4)
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == pytest.approx(188.4)


def test_zoom_widget_parses_typed_value(*, widget: ZoomWidget, qtbot: QtBot) -> None:
    widget.lineEdit().selectAll()
    qtbot.keyClicks(widget.lineEdit(), "150.5")
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == pytest.approx(150.5)
    assert widget.text() == "150%"


@pytest.mark.parametrize("typed", ["188", "188%"])
def test_zoom_widget_typed_whole_value_replaces_fraction(
    *, widget: ZoomWidget, qtbot: QtBot, typed: str
) -> None:
    widget.setValue(188.4)
    widget.lineEdit().selectAll()
    qtbot.keyClicks(widget.lineEdit(), typed)
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == 188.0


def test_zoom_widget_retyped_single_digit_replaces_fraction(
    *, widget: ZoomWidget, qtbot: QtBot
) -> None:
    widget.setValue(1.4)
    widget.lineEdit().selectAll()
    qtbot.keyClicks(widget.lineEdit(), "1")
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == 1.0


def test_zoom_widget_enter_after_same_value_keeps_fraction(
    *, widget: ZoomWidget, qtbot: QtBot
) -> None:
    widget.setValue(188.4)
    widget.lineEdit().selectAll()
    qtbot.keyClicks(widget.lineEdit(), "188.4")
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == pytest.approx(188.4)


def test_zoom_widget_reverted_invalid_edit_keeps_fraction(
    *, widget: ZoomWidget, qtbot: QtBot
) -> None:
    widget.setValue(188.4)
    widget.lineEdit().selectAll()
    qtbot.keyClicks(widget.lineEdit(), "0")
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == pytest.approx(188.4)
