from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from labelme.widgets.zoom_widget import ZoomWidget


@pytest.fixture
def widget(qtbot: QtBot) -> ZoomWidget:
    zoom_widget = ZoomWidget()
    qtbot.addWidget(zoom_widget)
    return zoom_widget


def test_zoom_widget_defaults_to_100(widget: ZoomWidget) -> None:
    assert widget.value() == 100.0


def test_zoom_widget_accepts_one_decimal(widget: ZoomWidget) -> None:
    widget.setValue(150.5)
    assert widget.value() == pytest.approx(150.5)


def test_zoom_widget_rounds_to_one_decimal(widget: ZoomWidget) -> None:
    widget.setValue(150.56)
    assert widget.value() == pytest.approx(150.6)


def test_zoom_widget_clamps_to_range(widget: ZoomWidget) -> None:
    widget.setValue(10000)
    assert widget.value() == ZoomWidget.PERCENT_MAX
    widget.setValue(0)
    assert widget.value() == 1.0
