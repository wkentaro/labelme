from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import Qt
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_image_navigation_while_selecting_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(file_or_dir=str(data_path / "annotated"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    # Incident: https://github.com/wkentaro/labelme/pull/1716 {{
    point = QPoint(250, 200)
    qtbot.mouseMove(win._canvas_widgets.canvas, pos=point)
    qtbot.mouseClick(win._canvas_widgets.canvas, Qt.LeftButton, pos=point)
    qtbot.wait(100)

    qtbot.mouseClick(win._docks.file_list, Qt.LeftButton)
    qtbot.wait(100)

    qtbot.keyClick(win._docks.file_list, Qt.Key_Down)
    qtbot.wait(100)
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key_Down)
    qtbot.wait(100)
    # }}

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
