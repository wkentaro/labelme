from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory


@pytest.fixture()
def recovery_button_states() -> dict[QMessageBox.ButtonRole, bool]:
    return {}


@pytest.fixture()
def recovery_messages() -> list[str]:
    return []


@pytest.fixture(autouse=True)
def recovery_buttons(
    *,
    qapp: QApplication,
    recovery_button_states: dict[QMessageBox.ButtonRole, bool],
    recovery_messages: list[str],
) -> Iterator[list[QMessageBox.ButtonRole]]:
    choices = [QMessageBox.ButtonRole.AcceptRole]
    timer = QTimer()

    def click_recovery_button() -> None:
        for widget in qapp.topLevelWidgets():
            if not isinstance(widget, QMessageBox) or not widget.isVisible():
                continue
            recovery_messages.append(widget.text() + widget.informativeText())
            if widget.standardButtons() == QMessageBox.StandardButton.Ok:
                widget.button(QMessageBox.StandardButton.Ok).click()
                continue
            assert widget.defaultButton().text() == "Continue with defaults"
            assert widget.escapeButton() is widget.defaultButton()
            recovery_button_states.update(
                (widget.buttonRole(button), button.isEnabled())
                for button in widget.buttons()
            )
            role = choices.pop(0) if choices else QMessageBox.ButtonRole.AcceptRole
            button = next(b for b in widget.buttons() if widget.buttonRole(b) == role)
            assert button.isEnabled()
            button.click()

    timer.timeout.connect(click_recovery_button)
    timer.start(10)
    yield choices
    timer.stop()


@pytest.mark.gui
@pytest.mark.parametrize(
    "with_config_file",
    [
        pytest.param(True, id="with_config_file"),
        pytest.param(False, id="without_config_file"),
    ],
)
def test_MainWindow_config(
    *,
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

    # Command-line values remain read-only while model management stays available.
    assert win._is_settings_editable is False
    win._open_settings()
    assert win._settings_dialog is not None
    assert not win._settings_dialog._editors[("auto_save",)].isEnabled()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize(
    "original",
    [b"labels: [cat]\nauto_save: false\nunknown: true\n", b"labels: [unclosed\n"],
    ids=["unknown-key", "malformed-yaml"],
)
def test_config_recovery_resets_and_reopens(
    *,
    main_win: MainWinFactory,
    tmp_path: Path,
    recovery_buttons: list[QMessageBox.ButtonRole],
    recovery_messages: list[str],
    original: bytes,
) -> None:
    config_file = tmp_path / "labelmerc"
    config_file.write_bytes(original)
    recovery_buttons.insert(0, QMessageBox.ButtonRole.ResetRole)
    win = main_win(config_file=config_file)
    assert win._is_settings_editable
    assert win._config_file == config_file
    assert win._config["auto_save"] is True
    assert win._config["labels"] is None
    assert config_file.read_bytes() == b""
    backups = list(tmp_path.glob("labelmerc.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original
    assert (
        "Resetting saves a backup of your configuration file first."
        in recovery_messages[0]
    )
    assert recovery_messages[1] == f"Configuration backup saved to {backups[0]}"
    reopened = main_win(config_file=config_file)
    assert reopened._config == win._config
    assert recovery_buttons == [QMessageBox.ButtonRole.AcceptRole]


@pytest.mark.gui
@pytest.mark.parametrize("original", ["unknown: true\n", "labels: [unclosed\n"])
def test_config_recovery_continue_keeps_file_and_valid_cli_overrides(
    *,
    main_win: MainWinFactory,
    tmp_path: Path,
    original: str,
) -> None:
    config_file = tmp_path / "labelmerc"
    config_file.write_text(original)
    win = main_win(config_file=config_file, config_overrides={"labels": ["bird"]})
    assert win._config_file is None
    assert win._config["labels"] == ["bird"]
    assert win._config["auto_save"] is True
    assert config_file.read_text() == original
    assert not list(tmp_path.glob("*.bak"))


@pytest.mark.gui
def test_config_recovery_allows_continuing_after_write_failure(
    *,
    main_win: MainWinFactory,
    tmp_path: Path,
    recovery_buttons: list[QMessageBox.ButtonRole],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "labelmerc"
    original = b"unknown: true\n"
    config_file.write_bytes(original)

    def fail_write(**_kwargs: object) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr("labelme._config._writer._atomic_write", fail_write)
    recovery_buttons.insert(0, QMessageBox.ButtonRole.ResetRole)
    win = main_win(config_file=config_file)
    assert win._config_file is None
    assert win._config["auto_save"] is True
    assert config_file.read_bytes() == original
    assert next(tmp_path.glob("labelmerc.*.bak")).read_bytes() == original
    assert recovery_buttons == []


@pytest.mark.gui
@pytest.mark.parametrize(
    ("original", "overrides"),
    [
        ("labels: [cat]\nvalidate_label: exact\n", {"labels": []}),
        ("unknown: true\n", {"validate_label": "exact"}),
    ],
    ids=["cli-conflicts-with-file", "cli-needs-file-settings"],
)
def test_cli_conflict_disables_file_resets(
    *,
    tmp_path: Path,
    qtbot: QtBot,
    recovery_button_states: dict[QMessageBox.ButtonRole, bool],
    original: str,
    overrides: dict,
) -> None:
    config_file = tmp_path / "labelmerc"
    config_file.write_text(original)
    win = MainWindow(config_file=config_file, config_overrides=overrides)
    qtbot.addWidget(win)
    assert not recovery_button_states[QMessageBox.ButtonRole.ResetRole]
    assert config_file.read_text() == original
    assert not list(tmp_path.glob("*.bak"))
