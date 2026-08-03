from __future__ import annotations

import typing
from pathlib import Path

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._config import _schema as schema
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


def test_editors_have_accessible_names(dialog: SettingsDialog) -> None:
    for setting in schema.SETTINGS:
        editor = dialog._editors[setting.key_path]
        assert editor.accessibleName() == dialog.tr(setting.label)


def test_beta_settings_render_a_badge(dialog: SettingsDialog) -> None:
    expected = {dialog.tr(setting.label) for setting in schema.SETTINGS if setting.beta}
    assert expected, "no beta settings to verify"

    badge_text = dialog.tr("BETA")
    beta_labels: set[str] = set()
    for badge in dialog.findChildren(QtWidgets.QLabel):
        if badge.text() != badge_text:
            continue
        cell = badge.parentWidget()
        assert cell is not None
        beta_labels.update(
            sibling.text()
            for sibling in cell.findChildren(QtWidgets.QLabel)
            if sibling is not badge
        )
    assert beta_labels == expected


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


def test_groups_and_navigation_follow_schema_order(dialog: SettingsDialog) -> None:
    expected = list(typing.get_args(schema.Group))
    assert [group.title() for group in dialog._page._groups] == expected
    assert [
        dialog._page._navigation.item(index).text()
        for index in range(dialog._page._navigation.count())
    ] == expected
    assert all(
        not dialog._page._navigation.item(index).icon().isNull()
        for index in range(dialog._page._navigation.count())
    )
    assert all(group.isFlat() for group in dialog._page._groups)


def test_navigation_uses_readable_typography_and_spacing(
    dialog: SettingsDialog,
) -> None:
    navigation = dialog._page._navigation
    assert navigation.font().pointSizeF() == dialog.font().pointSizeF() + 1
    assert navigation.iconSize() == QtCore.QSize(18, 18)
    expected_row_height = navigation.fontMetrics().height() + 12
    assert all(
        navigation.sizeHintForRow(index) == expected_row_height
        for index in range(navigation.count())
    )


def test_navigation_elides_long_localized_names_without_squeezing_content(
    qapp: QtWidgets.QApplication, qtbot: QtBot, applied: Applied
) -> None:
    translator = QtCore.QTranslator()
    translation_path = Path(__file__).parents[3] / "labelme" / "translate" / "ru_RU.qm"
    assert translator.load(str(translation_path))
    qapp.installTranslator(translator)
    try:
        dialog = _make_dialog(qtbot=qtbot, applied=applied, overrides={})
        navigation = dialog._page._navigation
        long_title = "Продолжение работы между изображениями"

        assert navigation.item(3).text() == long_title
        assert navigation.item(3).toolTip() == long_title
        assert navigation.textElideMode() == QtCore.Qt.TextElideMode.ElideRight
        assert navigation.width() == 240

        dialog.show()
        qtbot.waitExposed(dialog)
        if dialog.width() >= dialog.sizeHint().width():
            assert dialog._page._scroll_area.horizontalScrollBar().maximum() == 0
    finally:
        qapp.removeTranslator(translator)


def test_default_size_scrolls_vertically_only(
    qtbot: QtBot, dialog: SettingsDialog
) -> None:
    dialog.show()
    qtbot.waitExposed(dialog)

    scroll_area = dialog._page._scroll_area
    assert (dialog.width(), dialog.height()) == (760, 590)
    assert scroll_area.horizontalScrollBar().maximum() == 0
    assert scroll_area.verticalScrollBar().maximum() > 0


def test_dialog_is_resizable(dialog: SettingsDialog) -> None:
    target_width = dialog.width() + 40
    target_height = dialog.height() + 40
    dialog.resize(target_width, target_height)

    assert (dialog.width(), dialog.height()) == (target_width, target_height)


def test_dialog_prevents_narrow_content_overflow(
    qtbot: QtBot, dialog: SettingsDialog
) -> None:
    dialog.show()
    qtbot.waitExposed(dialog)
    minimum_width = dialog.width()

    dialog.resize(minimum_width - 200, dialog.height())

    assert dialog.width() == minimum_width
    assert dialog._page._scroll_area.horizontalScrollBar().maximum() == 0


@pytest.mark.parametrize("target", range(len(typing.get_args(schema.Group))))
def test_navigation_jumps_to_group(
    qtbot: QtBot, dialog: SettingsDialog, target: int
) -> None:
    dialog.show()
    qtbot.waitExposed(dialog)

    navigation = dialog._page._navigation
    item = navigation.item(target)
    assert item is not None
    qtbot.mouseClick(
        navigation.viewport(),
        QtCore.Qt.MouseButton.LeftButton,
        pos=navigation.visualItemRect(item).center(),
    )

    scroll_bar = dialog._page._scroll_area.verticalScrollBar()
    group_top = (
        dialog._page._groups[target].mapTo(dialog._page._content, QtCore.QPoint()).y()
    )
    assert scroll_bar.value() == min(group_top, scroll_bar.maximum())
    assert navigation.currentRow() == target


def test_scrolling_updates_navigation(qtbot: QtBot, dialog: SettingsDialog) -> None:
    dialog.show()
    qtbot.waitExposed(dialog)

    scroll_bar = dialog._page._scroll_area.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum() - 1)
    assert dialog._page._navigation.currentRow() == len(dialog._page._groups) - 2

    scroll_bar.setValue(scroll_bar.maximum())
    assert dialog._page._navigation.currentRow() == len(dialog._page._groups) - 1


def test_navigation_returns_to_first_group_when_resize_removes_scrollbar(
    qtbot: QtBot, dialog: SettingsDialog
) -> None:
    dialog.show()
    qtbot.waitExposed(dialog)

    scroll_bar = dialog._page._scroll_area.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum())
    assert dialog._page._navigation.currentRow() == len(dialog._page._groups) - 1

    content_height = dialog._page._content.sizeHint().height()
    dialog.resize(dialog.width(), content_height + 200)
    qtbot.waitUntil(lambda: scroll_bar.maximum() == 0)

    assert dialog._page._navigation.currentRow() == 0


def test_reopening_preserves_scroll_position(
    qtbot: QtBot, dialog: SettingsDialog
) -> None:
    dialog.show()
    qtbot.waitExposed(dialog)
    scroll_bar = dialog._page._scroll_area.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum() // 2)
    expected = scroll_bar.value()

    dialog.close()
    dialog.show()

    assert scroll_bar.value() == expected


def test_short_dialog_scrolls_page(qtbot: QtBot, dialog: SettingsDialog) -> None:
    dialog.resize(dialog.width(), 160)
    dialog.show()
    qtbot.waitExposed(dialog)

    assert dialog._page._scroll_area.verticalScrollBar().maximum() > 0


def test_large_font_uses_default_size_with_scrolling(
    qtbot: QtBot, applied: Applied
) -> None:
    original_font = QtWidgets.QApplication.font()
    large_font = QtGui.QFont(original_font)
    large_font.setPointSize(24)
    QtWidgets.QApplication.setFont(large_font)
    try:
        dialog = _make_dialog(qtbot=qtbot, applied=applied, overrides={})
        dialog.show()
        qtbot.waitExposed(dialog)

        available_size = dialog.screen().availableGeometry().size()
        scroll_bar_width = dialog.style().pixelMetric(
            QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent
        )
        assert dialog.width() == min(
            max(760, dialog.sizeHint().width() + scroll_bar_width),
            available_size.width(),
        )
        assert dialog.height() == min(590, available_size.height())
        assert dialog._page._scroll_area.verticalScrollBar().maximum() > 0
    finally:
        QtWidgets.QApplication.setFont(original_font)
