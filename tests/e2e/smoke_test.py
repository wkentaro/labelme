from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

import labelme.app


@pytest.mark.gui
def test_MainWindow_open(qtbot: QtBot) -> None:
    win: labelme.app.MainWindow = labelme.app.MainWindow()
    qtbot.addWidget(win)
    win.show()
    win.close()


@pytest.mark.gui
def test_file_search_config_filters_on_startup(qtbot: QtBot, data_path: Path) -> None:
    raw_dir = data_path / "raw"
    all_images = list(raw_dir.glob("*.jpg"))
    assert len(all_images) == 3

    win = labelme.app.MainWindow(
        config_overrides={"file_search": "2011_000003"},
        filename=str(raw_dir),
    )
    qtbot.addWidget(win)
    win.show()

    assert win.fileSearch.text() == "2011_000003"
    assert win.fileListWidget.count() == 1

    win.close()
