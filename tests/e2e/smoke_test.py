from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory


@pytest.mark.gui
def test_MainWindow_open(main_win: MainWinFactory, qtbot: QtBot, pause: bool) -> None:
    win = main_win()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_file_search_config_filters_on_startup(
    main_win: MainWinFactory, qtbot: QtBot, data_path: Path, pause: bool
) -> None:
    raw_dir = data_path / "raw"
    all_images = list(raw_dir.glob("*.jpg"))
    assert len(all_images) == 3

    win = main_win(
        config_overrides={"file_search": "2011_000003"},
        file_or_dir=str(raw_dir),
    )

    assert win._docks.file_search.text() == "2011_000003"
    assert win._docks.file_list.count() == 1

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
