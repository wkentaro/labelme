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


def test_flags_dock_hides_while_it_has_no_flags(
    *, main_win: MainWinFactory, qtbot: QtBot
) -> None:
    win: MainWindow = main_win()
    win.show()
    qtbot.waitExposed(win)
    dock = win._docks.flag_dock
    assert dock.isHidden()

    win._load_flags(flags={"blurry": False}, widget=win._docks.flag_list)
    assert dock.isVisible()

    win._load_flags(flags={}, widget=win._docks.flag_list)
    assert dock.isHidden()


def test_flags_dock_stays_closed_once_the_user_closes_it(
    *, main_win: MainWinFactory, qtbot: QtBot
) -> None:
    win: MainWindow = main_win(config_overrides=dict(flags=["occluded"]))
    win.show()
    qtbot.waitExposed(win)
    dock = win._docks.flag_dock
    assert dock.isVisible()

    dock.close()
    win._load_flags(flags={}, widget=win._docks.flag_list)
    win._load_flags(flags={"blurry": False}, widget=win._docks.flag_list)
    assert dock.isHidden()

    dock.toggleViewAction().trigger()
    assert dock.isVisible()


def test_flags_dock_returns_next_session_after_hiding_while_empty(
    *, main_win: MainWinFactory, qtbot: QtBot
) -> None:
    win: MainWindow = main_win()
    win.show()
    qtbot.waitExposed(win)
    assert win._docks.flag_dock.isHidden()
    win.close()

    win = main_win(config_overrides=dict(flags=["occluded"]))
    win.show()
    qtbot.waitExposed(win)
    assert win._docks.flag_dock.isVisible()


def test_flags_dock_stays_closed_next_session_once_the_user_closes_it(
    *, main_win: MainWinFactory, qtbot: QtBot
) -> None:
    win: MainWindow = main_win(config_overrides=dict(flags=["occluded"]))
    win.show()
    qtbot.waitExposed(win)
    win._docks.flag_dock.close()
    win.close()

    win = main_win(config_overrides=dict(flags=["occluded"]))
    win.show()
    qtbot.waitExposed(win)
    assert win._docks.flag_dock.isHidden()


def test_flags_dock_preference_survives_minimizing(
    *, main_win: MainWinFactory, qtbot: QtBot
) -> None:
    win: MainWindow = main_win(config_overrides=dict(flags=["occluded"]))
    win.show()
    qtbot.waitExposed(win)
    win.showMinimized()
    qtbot.waitUntil(win.isMinimized)
    # Offscreen Qt doesn't hide docks on minimize the way a desktop does.
    win._docks.flag_dock.toggleViewAction().toggled.emit(False)  # noqa: FBT003 -- Qt signal
    win.close()

    win = main_win(config_overrides=dict(flags=["occluded"]))
    win.show()
    qtbot.waitExposed(win)
    assert win._docks.flag_dock.isVisible()
