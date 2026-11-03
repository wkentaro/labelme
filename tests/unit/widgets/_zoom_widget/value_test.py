from __future__ import annotations

import pytest
from PySide6 import QtGui
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


def test_step_starts_from_typed_text(*, qtbot: QtBot, widget: ZoomWidget) -> None:
    widget.lineEdit().selectAll()
    qtbot.keyClicks(widget, "125")
    qtbot.keyClick(widget, Qt.Key.Key_Up)
    assert widget.value() == pytest.approx(137.5)


def test_size_hint_fits_the_widest_text(*, widget: ZoomWidget) -> None:
    widget.setValue(1000)
    text_width = widget.fontMetrics().horizontalAdvance(widget.text())
    assert widget.sizeHint().width() > text_width


@pytest.mark.parametrize(
    ("start", "typed", "key", "expected"),
    [(1000, "125", Qt.Key.Key_Up, 137.5), (1, "110", Qt.Key.Key_Down, 100)],
)
def test_step_from_typed_text_at_the_range_ends(
    *,
    qtbot: QtBot,
    widget: ZoomWidget,
    start: float,
    typed: str,
    key: Qt.Key,
    expected: float,
) -> None:
    widget.setValue(start)
    widget.lineEdit().selectAll()
    qtbot.keyClicks(widget, typed)
    qtbot.keyClick(widget, key)
    assert widget.value() == pytest.approx(expected)


def test_retyping_the_shown_number_keeps_the_exact_value(
    *, qtbot: QtBot, widget: ZoomWidget
) -> None:
    widget.setValue(188.4)
    widget.lineEdit().setSelection(0, 3)
    qtbot.keyClicks(widget, "188")
    with qtbot.assertNotEmitted(widget.valueChanged):
        qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == 188.4


def test_undo_then_enter_keeps_the_exact_value(
    *, qtbot: QtBot, widget: ZoomWidget
) -> None:
    widget.setValue(188.4)
    widget.lineEdit().setSelection(0, 3)
    qtbot.keyClicks(widget, "188")
    widget.lineEdit().undo()
    with qtbot.assertNotEmitted(widget.valueChanged):
        qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == 188.4


def test_accessible_value_reads_and_sets_the_zoom(*, widget: ZoomWidget) -> None:
    widget.setValue(76.24)
    interface = QtGui.QAccessible.queryAccessibleInterface(widget)
    value_interface = interface.valueInterface()
    assert value_interface.currentValue() == pytest.approx(76.24)
    value_interface.setCurrentValue(250)
    assert widget.value() == 250


def test_value_set_after_typing_ends_the_edit(
    *, qtbot: QtBot, widget: ZoomWidget
) -> None:
    widget.setValue(76.24)
    widget.lineEdit().selectAll()
    qtbot.keyClicks(widget, "188")
    widget.setValue(188.4)
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == 188.4


@pytest.mark.parametrize(("start", "typed"), [(100, "100.4"), (188.4, "188.3")])
def test_typed_value_beyond_the_display_precision_applies(
    *, qtbot: QtBot, widget: ZoomWidget, start: float, typed: str
) -> None:
    widget.setValue(start)
    widget.lineEdit().selectAll()
    qtbot.keyClicks(widget, typed)
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    assert widget.value() == float(typed)
