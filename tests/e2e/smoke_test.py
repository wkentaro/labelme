from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

import labelme.app

from ..conftest import close_or_pause


@pytest.mark.gui
def test_MainWindow_open(qtbot: QtBot, pause: bool) -> None:
    win: labelme.app.MainWindow = labelme.app.MainWindow()
    qtbot.addWidget(win)
    win.show()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_file_search_config_filters_on_startup(
    qtbot: QtBot, data_path: Path, pause: bool
) -> None:
    raw_dir = data_path / "raw"
    all_images = list(raw_dir.glob("*.jpg"))
    assert len(all_images) == 3

    win = labelme.app.MainWindow(
        config_overrides={"file_search": "2011_000003"},
        file_or_dir=str(raw_dir),
    )
    qtbot.addWidget(win)
    win.show()

    assert win._docks.file_search.text() == "2011_000003"
    assert win._docks.file_list.count() == 1

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
