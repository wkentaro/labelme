from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
@pytest.mark.parametrize(
    ("row", "direction", "expected_row"),
    [(0, "next", 1), (1, "next", 2), (1, "previous", 0), (2, "previous", 1)],
)
def test_navigation_after_closing_image(
    *,
    main_win: MainWinFactory,
    data_path: Path,
    row: int,
    direction: str,
    expected_row: int,
) -> None:
    win = main_win(file_or_dir=data_path / "raw")
    paths = win.image_list[:]
    win._docks.file_list.setCurrentRow(row)
    win.close_file()
    assert win._image_path is None
    assert win._docks.file_list.currentRow() == row

    action = (
        win._actions.open_prev_img
        if direction == "previous"
        else win._actions.open_next_img
    )
    assert action.isEnabled()
    action.trigger()

    assert win._image_path == paths[expected_row]
    assert win._docks.file_list.currentRow() == expected_row


@pytest.mark.gui
@pytest.mark.parametrize("direction", ["previous", "next"])
def test_navigation_from_filtered_out_image(
    *, main_win: MainWinFactory, data_path: Path, direction: str
) -> None:
    win = main_win(file_or_dir=data_path / "raw")
    paths = win.image_list[:]
    win._docks.file_list.setCurrentRow(1)
    win._docks.file_search.setText(r"000003|000025")
    assert win._file_list_image_path == paths[1]
    assert win._docks.file_list.currentRow() == -1

    action = (
        win._actions.open_prev_img
        if direction == "previous"
        else win._actions.open_next_img
    )
    action.trigger()

    assert win._file_list_image_path == paths[0 if direction == "previous" else 2]
    assert win._actions.open_prev_img.isEnabled() == (direction == "next")
    assert win._actions.open_next_img.isEnabled() == (direction == "previous")


@pytest.mark.gui
def test_navigation_actions_follow_filter_and_boundaries(
    *, main_win: MainWinFactory, data_path: Path
) -> None:
    win = main_win(file_or_dir=data_path / "raw")
    assert not win._actions.open_prev_img.isEnabled()
    assert win._actions.open_next_img.isEnabled()
    win._docks.file_search.setText(r"000003")
    assert not win._actions.open_prev_img.isEnabled()
    assert not win._actions.open_next_img.isEnabled()
    win._docks.file_search.setText("no-match")
    assert not win._actions.open_prev_img.isEnabled()
    assert not win._actions.open_next_img.isEnabled()
    win._docks.file_search.clear()
    assert not win._actions.open_prev_img.isEnabled()
    assert win._actions.open_next_img.isEnabled()
    win._docks.file_list.setCurrentRow(2)
    assert win._actions.open_prev_img.isEnabled()
    assert not win._actions.open_next_img.isEnabled()


@pytest.mark.gui
def test_image_navigation_while_selecting_shape(
    *,
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
    qtbot.mouseClick(win._canvas_widgets.canvas, Qt.MouseButton.LeftButton, pos=point)
    qtbot.wait(100)

    qtbot.mouseClick(win._docks.file_list, Qt.MouseButton.LeftButton)
    qtbot.wait(100)

    qtbot.keyClick(win._docks.file_list, Qt.Key.Key_Down)
    qtbot.wait(100)
    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Down)
    qtbot.wait(100)
    # }}

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
