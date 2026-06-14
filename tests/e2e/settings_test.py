from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._yaml import safe_load
from labelme.app import MainWindow
from labelme.widgets import SettingsDialog
from labelme.widgets.settings_dialog import _PlainTextEdit

from ..conftest import close_or_pause
from .conftest import MainWinFactory


def _set_flag_checked(win: MainWindow, name: str) -> None:
    flag_list = win._docks.flag_list
    flag_list.blockSignals(True)  # avoid mark_dirty; we test only the flag refresh
    try:
        for i in range(flag_list.count()):
            item = flag_list.item(i)
            assert item is not None
            if item.text() == name:
                item.setCheckState(Qt.CheckState.Checked)
                return
        raise AssertionError(f"flag {name!r} not found in the dock")
    finally:
        flag_list.blockSignals(False)


@pytest.fixture
def editable_config_file(tmp_path: Path) -> Path:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("auto_save: true\n")
    return config_file


@pytest.mark.gui
def test_settings_dialog_opens_when_editable(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)

    assert win._settings_dialog is None
    win._open_settings()
    assert isinstance(win._settings_dialog, SettingsDialog)
    assert win._settings_dialog.isVisible()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_setting_change_persists_and_applies(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)

    label_dialog_before = win._label_dialog
    win._open_settings()
    dialog = win._settings_dialog
    assert dialog is not None

    checkbox = dialog._editors[("display_label_popup",)]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    checkbox.setChecked(False)  # toggling applies immediately

    labels_editor = dialog._editors[("labels",)]
    assert isinstance(labels_editor, QtWidgets.QPlainTextEdit)
    labels_editor.setPlainText("cat\ndog\n\ncat\n")
    dialog.accept()  # flushes the pending label edit on close

    assert win._config["display_label_popup"] is False
    assert win._config["labels"] == ["cat", "dog"]
    assert win._label_dialog is label_dialog_before  # updated in place, not rebuilt
    unique_label_list = win._docks.unique_label_list
    assert unique_label_list.find_label_item("cat") is not None
    assert unique_label_list.find_label_item("dog") is not None

    persisted = safe_load(editable_config_file.read_text())
    assert persisted["display_label_popup"] is False
    assert persisted["labels"] == ["cat", "dog"]

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_show_labels_toggle_applies_to_canvas(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)
    canvas = win._canvas_widgets.canvas
    assert canvas._show_labels is False

    win._open_settings()
    dialog = win._settings_dialog
    assert dialog is not None
    checkbox = dialog._editors[("shape", "show_labels")]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    checkbox.setChecked(True)  # toggling applies immediately, without restart
    dialog.accept()

    assert win._config["shape"]["show_labels"] is True
    assert canvas._show_labels is True
    assert safe_load(editable_config_file.read_text())["shape"]["show_labels"] is True

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_label_edit_preserves_label_history(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)
    win._label_dialog.add_label_history("bird")  # learned from a loaded/created shape

    old_label_dialog = win._label_dialog

    win._open_settings()
    dialog = win._settings_dialog
    assert dialog is not None
    labels_editor = dialog._editors[("labels",)]
    assert isinstance(labels_editor, QtWidgets.QPlainTextEdit)
    labels_editor.setPlainText("cat\ndog")
    dialog.accept()

    assert win._label_dialog is old_label_dialog  # updated in place, not rebuilt
    label_list = win._label_dialog.label_list
    labels = {label_list.item(i).text() for i in range(label_list.count())}
    assert labels == {"bird", "cat", "dog"}  # history kept, new labels added

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_flags_setting_refreshes_flag_dock_live(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)

    win._open_settings()
    dialog = win._settings_dialog
    assert dialog is not None
    flags_editor = dialog._editors[("flags",)]
    assert isinstance(flags_editor, _PlainTextEdit)

    flags_editor.setPlainText("occluded\ntruncated")
    flags_editor.commit()

    # The flag dock reflects the edit immediately, without navigating images.
    assert win._config["flags"] == ["occluded", "truncated"]
    assert win._read_flag_dock_states() == {"occluded": False, "truncated": False}
    assert not win._is_changed  # a settings-driven refresh must not dirty the image

    _set_flag_checked(win, "occluded")
    flags_editor.setPlainText("occluded\ntruncated\nblurry")
    flags_editor.commit()

    states = win._read_flag_dock_states()
    # The new "blurry" flag appears unchecked while "occluded" stays checked.
    assert states == {"occluded": True, "truncated": False, "blurry": False}

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_clearing_labels_is_rejected_when_validate_label_is_exact(
    main_win: MainWinFactory,
    qtbot: QtBot,
    editable_config_file: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editable_config_file.write_text("labels: [cat]\nvalidate_label: exact\n")
    win = main_win(config_file=editable_config_file)

    warned: list[str] = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: warned.append(args[2]),
    )

    win._open_settings()
    dialog = win._settings_dialog
    assert dialog is not None

    labels_editor = dialog._editors[("labels",)]
    assert isinstance(labels_editor, QtWidgets.QPlainTextEdit)
    labels_editor.setPlainText("")
    dialog.accept()

    validate_combo = dialog._editors[("validate_label",)]
    assert isinstance(validate_combo, QtWidgets.QComboBox)
    assert warned == [
        (
            "Predefined labels cannot be empty while Label validation is set to "
            "exact. Disable exact validation first."
        )
    ]
    assert labels_editor.toPlainText() == "cat"
    assert validate_combo.currentData() == "exact"
    assert win._config["labels"] == ["cat"]
    assert win._config["validate_label"] == "exact"

    persisted = safe_load(editable_config_file.read_text())
    assert persisted["labels"] == ["cat"]
    assert persisted["validate_label"] == "exact"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_setting_reverts_when_write_fails(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("a read-only directory is not enforced for root")

    config_dir = tmp_path / "ro"
    config_dir.mkdir()
    config_file = config_dir / "labelmerc.yaml"
    config_file.write_text("display_label_popup: true\n")
    win = main_win(config_file=config_file)

    warned: list[object] = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: warned.append(args[2]),
    )

    win._open_settings()
    dialog = win._settings_dialog
    assert dialog is not None
    checkbox = dialog._editors[("display_label_popup",)]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    assert checkbox.isChecked()

    # The atomic save writes a temp file in the config directory, so a read-only
    # directory makes set_override raise.
    config_dir.chmod(0o500)
    try:
        checkbox.setChecked(False)
    finally:
        config_dir.chmod(0o700)

    assert warned  # the user was told the write failed
    assert checkbox.isChecked()  # editor reverted to the last-saved value
    assert win._config["display_label_popup"] is True  # in-memory config unchanged
    assert safe_load(config_file.read_text())["display_label_popup"] is True

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_settings_dialog_is_deleted_when_opening_text_editor(
    main_win: MainWinFactory,
    qtbot: QtBot,
    editable_config_file: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(config_file=editable_config_file)
    win._open_settings()
    dialog = win._settings_dialog
    assert dialog is not None

    deleted: list[bool] = []
    dialog.destroyed.connect(lambda: deleted.append(True))
    monkeypatch.setattr("labelme.app.subprocess.Popen", lambda *args, **kwargs: None)

    win._open_config_file()

    assert win._settings_dialog is None
    qtbot.waitUntil(lambda: bool(deleted))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_settings_disabled_with_cli_overrides(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(
        config_file=editable_config_file, config_overrides={"labels": ["bird"]}
    )

    assert win._config_overrides
    win._open_settings()
    assert win._settings_dialog is None

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
