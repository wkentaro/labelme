from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from labelme._config import load_config
from labelme.widgets.settings_dialog import SettingsDialog

Applied = list[tuple[tuple[str, ...], object]]


@pytest.fixture
def applied() -> Applied:
    return []


def _make_dialog(qtbot: QtBot, applied: Applied, overrides: dict) -> SettingsDialog:
    config = load_config(config_file=None, config_overrides=overrides)
    dialog = SettingsDialog(
        config=config,
        apply_setting=lambda key_path, value: applied.append((key_path, value)),
        open_as_text=lambda: None,
    )
    qtbot.addWidget(dialog)
    return dialog


@pytest.fixture
def dialog(qtbot: QtBot, applied: Applied) -> SettingsDialog:
    return _make_dialog(qtbot=qtbot, applied=applied, overrides={})


def test_no_apply_on_construction(dialog: SettingsDialog, applied: Applied) -> None:
    assert applied == []


def test_toggle_bool_applies(dialog: SettingsDialog, applied: Applied) -> None:
    check = dialog._editors[("auto_save",)]
    check.setChecked(False)  # ty: ignore[unresolved-attribute]
    assert (("auto_save",), False) in applied


def test_str_list_dedups_and_drops_blanks(
    dialog: SettingsDialog, applied: Applied
) -> None:
    edit = dialog._editors[("labels",)]
    edit.setPlainText("cat\ndog\n\ncat\n")  # ty: ignore[unresolved-attribute]
    edit.editing_finished.emit()  # ty: ignore[unresolved-attribute]
    assert (("labels",), ["cat", "dog"]) in applied


def test_str_list_none_initial_is_blank(dialog: SettingsDialog) -> None:
    edit = dialog._editors[("labels",)]
    assert edit.toPlainText() == ""  # ty: ignore[unresolved-attribute]


def test_accept_flushes_pending_str_list_edits(
    dialog: SettingsDialog, applied: Applied
) -> None:
    edit = dialog._editors[("labels",)]
    edit.setPlainText("cat\ndog")  # ty: ignore[unresolved-attribute]
    dialog.accept()
    assert (("labels",), ["cat", "dog"]) in applied


def test_validate_label_gate_reverts_when_labels_emptied(
    qtbot: QtBot, applied: Applied
) -> None:
    dialog = _make_dialog(
        qtbot=qtbot,
        applied=applied,
        overrides={"labels": ["cat"], "validate_label": "exact"},
    )
    validate_combo = dialog._editors[("validate_label",)]
    exact_index = validate_combo.findData("exact")  # ty: ignore[unresolved-attribute]
    assert validate_combo.model().item(exact_index).isEnabled()  # ty: ignore[unresolved-attribute]

    labels_editor = dialog._editors[("labels",)]
    labels_editor.setPlainText("")  # ty: ignore[unresolved-attribute]
    labels_editor.editing_finished.emit()  # ty: ignore[unresolved-attribute]

    assert not validate_combo.model().item(exact_index).isEnabled()  # ty: ignore[unresolved-attribute]
    assert (("validate_label",), None) in applied


def test_no_apply_on_construction_when_exact_without_labels(
    qtbot: QtBot, applied: Applied
) -> None:
    config = load_config(
        config_file=None,
        config_overrides={"labels": ["cat"], "validate_label": "exact"},
    )
    config["labels"] = None  # a hand-edited state that load_config would reject
    dialog = SettingsDialog(
        config=config,
        apply_setting=lambda key_path, value: applied.append((key_path, value)),
        open_as_text=lambda: None,
    )
    qtbot.addWidget(dialog)
    assert applied == []
    validate_combo = dialog._editors[("validate_label",)]
    exact_index = validate_combo.findData("exact")  # ty: ignore[unresolved-attribute]
    assert not validate_combo.model().item(exact_index).isEnabled()  # ty: ignore[unresolved-attribute]
