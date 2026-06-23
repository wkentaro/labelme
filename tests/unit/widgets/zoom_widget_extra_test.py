"""Additional characterization tests for ZoomWidget.

The core value/range/decimal tests are already in zoom_widget_test.py.
This file covers the remaining observable contract: class constants, suffix,
alignment, button symbols, tooltip/status-tip, and minimum width.
"""

from __future__ import annotations

import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets.zoom_widget import ZoomWidget


@pytest.fixture()
def widget(qtbot: QtBot) -> ZoomWidget:
    w = ZoomWidget()
    qtbot.addWidget(w)
    return w


# --- class constants ---


def test_zoom_widget_percent_max_constant() -> None:
    assert ZoomWidget.PERCENT_MAX == 1000


def test_zoom_widget_percent_decimals_constant() -> None:
    assert ZoomWidget.PERCENT_DECIMALS == 1


def test_zoom_widget_percent_suffix_constant() -> None:
    assert ZoomWidget.PERCENT_SUFFIX == " %"


# --- suffix ---


def test_zoom_widget_suffix_matches_constant(widget: ZoomWidget) -> None:
    assert widget.suffix() == ZoomWidget.PERCENT_SUFFIX


# --- range ---


def test_zoom_widget_minimum_is_one(widget: ZoomWidget) -> None:
    assert widget.minimum() == pytest.approx(1.0)


def test_zoom_widget_maximum_equals_percent_max(widget: ZoomWidget) -> None:
    assert widget.maximum() == pytest.approx(ZoomWidget.PERCENT_MAX)


# --- decimals ---


def test_zoom_widget_decimals_matches_constant(widget: ZoomWidget) -> None:
    assert widget.decimals() == ZoomWidget.PERCENT_DECIMALS


# --- alignment ---


def test_zoom_widget_alignment_is_center(widget: ZoomWidget) -> None:
    assert widget.alignment() == QtCore.Qt.AlignmentFlag.AlignCenter


# --- button symbols ---


def test_zoom_widget_no_spin_buttons(widget: ZoomWidget) -> None:
    assert widget.buttonSymbols() == QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons


# --- tooltip and status tip ---


def test_zoom_widget_tooltip_is_zoom_level(widget: ZoomWidget) -> None:
    assert widget.toolTip() == "Zoom Level"


def test_zoom_widget_status_tip_is_zoom_level(widget: ZoomWidget) -> None:
    assert widget.statusTip() == "Zoom Level"


# --- minimum width ---


def test_zoom_widget_minimum_width_accommodates_max_value(widget: ZoomWidget) -> None:
    # The minimum width must be wide enough to display the maximum zoom string.
    sample = (
        f"{ZoomWidget.PERCENT_MAX:.{ZoomWidget.PERCENT_DECIMALS}f}"
        f"{ZoomWidget.PERCENT_SUFFIX}"
    )
    minimum_required = widget.fontMetrics().horizontalAdvance(sample)
    assert widget.minimumWidth() >= minimum_required
    assert widget.minimumWidth() > 0


# --- is a QDoubleSpinBox ---


def test_zoom_widget_is_double_spin_box(widget: ZoomWidget) -> None:
    assert isinstance(widget, QtWidgets.QDoubleSpinBox)
