from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

import labelme.app


@pytest.mark.gui
def test_MainWindow_open(qtbot: QtBot) -> None:
    win: labelme.app.MainWindow = labelme.app.MainWindow()
    qtbot.addWidget(win)
    win.show()
    win.close()
