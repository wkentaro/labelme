from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory


@pytest.mark.gui
def test_MainWindow_open(
    main_win: MainWinFactory, qtbot: QtBot, *, pause: bool
) -> None:
    win = main_win()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_file_search_config_regex_filters_on_startup(
    main_win: MainWinFactory, qtbot: QtBot, data_path: Path, *, pause: bool
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
