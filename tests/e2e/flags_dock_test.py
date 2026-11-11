from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


def test_flag_click_without_image_leaves_window_clean(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
) -> None:
    # Auto Save stays off here: with it on, the unfixed code asserts inside a
    # Qt slot and the app's exception hook opens a modal dialog.
    win: MainWindow = main_win(
        config_overrides=dict(flags=["occluded"], auto_save=False)
    )
    win.show()
    qtbot.waitExposed(win)
    flag_list = win._docks.flag_list
    assert flag_list.count() == 1

    flag_list.item(0).setCheckState(Qt.CheckState.Checked)

    assert not win._is_changed
    assert not win._actions.save.isEnabled()
    assert not win.windowTitle().endswith("*")


def test_close_file_clears_the_closed_image_flags(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    win: MainWindow = main_win(
        file_or_dir=str(data_path / "annotated" / "2011_000003.json"),
        config_overrides=dict(auto_save=False),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._load_flags(flags={"blurry": True}, widget=win._docks.flag_list)
    assert win._docks.flag_list.count() == 1

    win.close_file()

    assert win._docks.flag_list.count() == 0
