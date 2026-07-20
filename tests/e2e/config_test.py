from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory


@pytest.mark.gui
@pytest.mark.parametrize(
    "with_config_file",
    [
        pytest.param(True, id="with_config_file"),
        pytest.param(False, id="without_config_file"),
    ],
)
def test_MainWindow_config(
    main_win: MainWinFactory,
    with_config_file: bool,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
) -> None:
    config_file: Path | None = None
    auto_save: bool = True
    if with_config_file:
        config_file = tmp_path / "labelmerc.yaml"
        config_file.write_text("auto_save: false\nlabels: [cat, dog]\n")
        auto_save = False

    win = main_win(
        config_file=config_file,
        config_overrides={"labels": ["bird"]},
    )

    assert win._config["auto_save"] is auto_save
    assert win._config["labels"] == ["bird"]
    assert win._config_file == config_file

    # Overrides are present, so settings are not editable and opening the
    # dialog is a no-op regardless of whether a config file backs the session.
    assert win._is_settings_editable is False
    win._open_settings()
    assert win._settings_dialog is None

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_MainWindow_config_load_error_falls_back(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
) -> None:
    # Malformed YAML makes load_config raise a non-ValueError (a yaml
    # ParserError); the backstop must catch any such error and fall back to
    # defaults instead of crashing the app before the window opens.
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("auto_save: [unclosed\n")

    win = main_win(config_file=config_file)

    assert win._config_file is None
    assert win._config["auto_save"] is True

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
