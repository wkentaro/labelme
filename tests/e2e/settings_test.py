from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from labelme._yaml import safe_load
from labelme.widgets import SettingsDialog

from ..conftest import close_or_pause
from .conftest import MainWinFactory


@pytest.mark.gui
def test_settings_dialog_opens_when_editable(
    main_win: MainWinFactory, qtbot: QtBot, tmp_path: Path, pause: bool
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("auto_save: true\n")
    win = main_win(config_file=config_file)

    assert win._settings_dialog is None
    win._open_settings()
    assert isinstance(win._settings_dialog, SettingsDialog)
    assert win._settings_dialog.isVisible()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_setting_change_persists_and_applies(
    main_win: MainWinFactory, qtbot: QtBot, tmp_path: Path, pause: bool
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("auto_save: true\n")
    win = main_win(config_file=config_file)

    win._on_setting_changed(key_path=("canvas", "fill_drawing"), value=False)
    win._on_setting_changed(key_path=("auto_save",), value=False)

    # applied live to the running app
    assert win._actions.fill_drawing.isChecked() is False
    assert win._actions.save_auto.isChecked() is False
    assert win._config["canvas"]["fill_drawing"] is False

    # persisted to the config file as sparse overrides
    persisted = safe_load(config_file.read_text())
    assert persisted["canvas"]["fill_drawing"] is False
    assert persisted["auto_save"] is False

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_settings_disabled_with_cli_overrides(
    main_win: MainWinFactory, qtbot: QtBot, tmp_path: Path, pause: bool
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("auto_save: true\n")
    win = main_win(config_file=config_file, config_overrides={"labels": ["bird"]})

    assert win._config_overrides
    win._open_settings()
    assert win._settings_dialog is None

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
