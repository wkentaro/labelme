from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from labelme._shape import Shape
from labelme.config import safe_load
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

    win._on_setting_changed(key_path=("shape", "point_size"), value=20)
    win._on_setting_changed(key_path=("auto_save",), value=False)

    # applied live to the running app
    assert Shape.point_size == 20
    assert win._actions.save_auto.isChecked() is False
    assert win._config["shape"]["point_size"] == 20

    # persisted to the config file as sparse overrides
    persisted = safe_load(config_file.read_text())
    assert persisted["shape"]["point_size"] == 20
    assert persisted["auto_save"] is False

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_reopen_last_dir_loads_on_launch(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    data_path: Path,
    pause: bool,
) -> None:
    raw_dir = data_path / "raw"
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("reopen_last_dir: true\n")

    win = main_win(file_or_dir=str(raw_dir), config_file=config_file)
    assert win._prev_opened_dir == str(raw_dir)
    win.close()

    reopened = main_win(config_file=config_file)
    assert reopened._prev_opened_dir == str(raw_dir)
    assert reopened.image_list

    close_or_pause(qtbot=qtbot, widget=reopened, pause=pause)


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
