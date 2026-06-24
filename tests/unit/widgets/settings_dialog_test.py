from __future__ import annotations

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._config import load_config
from labelme._widgets.settings_dialog import SettingsDialog
from labelme._widgets.settings_dialog import _PlainTextEdit

Applied = list[tuple[tuple[str, ...], object]]


@pytest.fixture
def applied() -> Applied:
    return []


def _make_dialog(
    qtbot: QtBot, applied: Applied, overrides: dict, succeed: bool = True
) -> SettingsDialog:
    config = load_config(config_file=None, config_overrides=overrides)

    def apply_setting(key_path: tuple[str, ...], value: object) -> bool:
        applied.append((key_path, value))
        return succeed

    dialog = SettingsDialog(
        config=config,
        apply_setting=apply_setting,
        open_as_text=lambda: None,
    )
    qtbot.addWidget(dialog)
    return dialog


@pytest.fixture
def dialog(qtbot: QtBot, applied: Applied) -> SettingsDialog:
    return _make_dialog(qtbot=qtbot, applied=applied, overrides={})


def test_no_apply_on_construction(dialog: SettingsDialog, applied: Applied) -> None:
    assert applied == []


def test_accept_does_not_reapply_unchanged_str_list(
    dialog: SettingsDialog, applied: Applied
) -> None:
    dialog.accept()
    assert applied == []


def test_str_list_none_initial_is_blank(dialog: SettingsDialog) -> None:
    edit = dialog._editors[("labels",)]
    assert isinstance(edit, QtWidgets.QPlainTextEdit)
    assert edit.toPlainText() == ""


def test_language_default_selects_system(dialog: SettingsDialog) -> None:
    combo = dialog._editors[("language",)]
    assert isinstance(combo, QtWidgets.QComboBox)
    assert combo.currentData() is None


def test_language_lists_bundled_locales(dialog: SettingsDialog) -> None:
    combo = dialog._editors[("language",)]
    assert isinstance(combo, QtWidgets.QComboBox)
    assert combo.findData("ja_JP") >= 0


def test_language_applies_locale_code(dialog: SettingsDialog, applied: Applied) -> None:
    combo = dialog._editors[("language",)]
    assert isinstance(combo, QtWidgets.QComboBox)
    combo.setCurrentIndex(combo.findData("en_US"))
    assert (("language",), "en_US") in applied


def test_language_applies_discovered_locale(
    dialog: SettingsDialog, applied: Applied
) -> None:
    combo = dialog._editors[("language",)]
    assert isinstance(combo, QtWidgets.QComboBox)
    index = combo.findData("ja_JP")
    assert index >= 0
    combo.setCurrentIndex(index)
    assert (("language",), "ja_JP") in applied


def test_language_unknown_code_falls_back_to_system(
    qtbot: QtBot, applied: Applied
) -> None:
    dialog = _make_dialog(qtbot=qtbot, applied=applied, overrides={"language": "xx_ZZ"})
    combo = dialog._editors[("language",)]
    assert isinstance(combo, QtWidgets.QComboBox)
    assert combo.currentData() is None
    assert applied == []


def test_clearing_labels_is_rejected_when_validate_label_is_exact(
    qtbot: QtBot, applied: Applied, monkeypatch: pytest.MonkeyPatch
) -> None:
    dialog = _make_dialog(
        qtbot=qtbot,
        applied=applied,
        overrides={"labels": ["cat"], "validate_label": "exact"},
    )
    warned: list[str] = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: warned.append(args[2]),
    )

    validate_combo = dialog._editors[("validate_label",)]
    assert isinstance(validate_combo, QtWidgets.QComboBox)
    model = validate_combo.model()
    assert isinstance(model, QtGui.QStandardItemModel)
    exact_index = validate_combo.findData("exact")
    assert model.item(exact_index).isEnabled()
    assert validate_combo.currentData() == "exact"

    labels_editor = dialog._editors[("labels",)]
    assert isinstance(labels_editor, _PlainTextEdit)
    labels_editor.setPlainText("")
    labels_editor.editing_finished.emit()

    assert warned == [
        (
            "Predefined labels cannot be empty while Label validation is set to "
            "exact. Disable exact validation first."
        )
    ]
    assert applied == []
    assert model.item(exact_index).isEnabled()
    assert validate_combo.currentData() == "exact"
    assert labels_editor.toPlainText() == "cat"


def test_failed_apply_reverts_checkbox(qtbot: QtBot, applied: Applied) -> None:
    dialog = _make_dialog(
        qtbot=qtbot,
        applied=applied,
        overrides={"display_label_popup": True},
        succeed=False,
    )
    checkbox = dialog._editors[("display_label_popup",)]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    assert checkbox.isChecked()

    checkbox.setChecked(False)

    assert checkbox.isChecked()  # reverted to the last-saved value


def test_failed_apply_reverts_labels_editor(qtbot: QtBot, applied: Applied) -> None:
    dialog = _make_dialog(
        qtbot=qtbot, applied=applied, overrides={"labels": ["cat"]}, succeed=False
    )
    edit = dialog._editors[("labels",)]
    assert isinstance(edit, _PlainTextEdit)
    assert edit.toPlainText() == "cat"

    edit.setPlainText("cat\ndog")
    edit.commit()

    assert edit.toPlainText() == "cat"  # reverted, not left in a phantom state
    applied.clear()
    edit.commit()  # nothing pending: the revert reset the committed text
    assert applied == []
