from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from labelme.widgets import LabelListWidget
from labelme.widgets import LabelListWidgetItem

from ...conftest import close_or_pause


@pytest.mark.gui
def test_LabelListWidget(qtbot: QtBot, pause: bool) -> None:
    widget = LabelListWidget()

    item = LabelListWidgetItem(text="person <font color='red'>●</fon>")
    widget.add_item(item)
    item = LabelListWidgetItem(text="dog <font color='blue'>●</fon>")
    widget.add_item(item)

    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)

    close_or_pause(qtbot=qtbot, widget=widget, pause=pause)
