from __future__ import annotations

from pathlib import Path

from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory


def test_MainWindow_open(
    *, main_win: MainWinFactory, qtbot: QtBot, pause: bool
) -> None:
    win = main_win()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


def test_file_search_config_regex_filters_on_startup(
    *, main_win: MainWinFactory, qtbot: QtBot, data_path: Path, pause: bool
) -> None:
    raw_dir = data_path / "raw"
    all_images = list(raw_dir.glob("*.jpg"))
    assert len(all_images) == 3

    win = main_win(
        config_overrides={"file_search": r"2011_00000[36]\.jpg$"},
        file_or_dir=str(raw_dir),
    )

    assert win._docks.file_search.text() == r"2011_00000[36]\.jpg$"
    assert [Path(path).name for path in win.image_list] == [
        "2011_000003.jpg",
        "2011_000006.jpg",
    ]

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


def test_select_tool_heads_the_shape_tool_rail(*, main_win: MainWinFactory) -> None:
    win = main_win()
    rail = win.findChild(QtWidgets.QToolBar, "CreateShapeToolsToolBar")
    top = win.findChild(QtWidgets.QToolBar, "ToolsToolBar")
    assert rail is not None and top is not None

    first, second, third = rail.actions()[:3]
    assert first is win._actions.edit_mode
    assert second.isSeparator()
    assert third is dict(win._actions.draw)["polygon"]
    assert win._actions.edit_mode not in top.actions()
