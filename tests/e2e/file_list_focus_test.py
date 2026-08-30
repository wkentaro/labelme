from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_arrow_keys_walk_file_list_across_loads(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    *,
    pause: bool,
) -> None:
    win = main_win(file_or_dir=str(data_path / "annotated"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    file_list = win._docks.file_list
    assert file_list.count() == 3
    file_list.setFocus()
    qtbot.waitUntil(lambda: file_list.hasFocus())

    # Keys must go to whatever holds focus, not to file_list directly: routing
    # them by hand would pass even while the load steals focus.
    for expected_row in (1, 2):
        focused = QApplication.focusWidget()
        assert focused is not None
        qtbot.keyClick(focused, Qt.Key.Key_Down)
        qtbot.waitUntil(lambda row=expected_row: file_list.currentRow() == row)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_canvas_takes_focus_when_file_list_has_none(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    *,
    pause: bool,
) -> None:
    win = main_win(file_or_dir=str(data_path / "annotated"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    # Start from the search box, so the canvas can only end up focused by the
    # load handing it the keyboard.
    file_search = win._docks.file_search
    file_search.setFocus()
    qtbot.waitUntil(lambda: file_search.hasFocus())

    win._open_next_image()
    qtbot.waitUntil(lambda: win._docks.file_list.currentRow() == 1)
    assert win._canvas_widgets.canvas.hasFocus()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
