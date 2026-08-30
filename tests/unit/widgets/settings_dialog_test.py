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
from labelme._widgets._integer_slider import IntegerSlider
from labelme._widgets.settings_dialog import SettingsDialog
from labelme._widgets.settings_dialog import _ColorSwatchButton
from labelme._widgets.settings_dialog import _PlainTextEdit

Applied = list[tuple[tuple[str, ...], object]]
Previewed = list[tuple[tuple[str, ...], list[int] | None]]


@pytest.fixture
def applied() -> Applied:
    return []


def _preferred_width(dialog: SettingsDialog) -> int:
    # The width the dialog opens at on an unconstrained screen: its page held
    # out of sideways scrolling plus its own chrome, never below the default.
    page = dialog._page
    scroll_bar_width = dialog.style().pixelMetric(
        QtWidgets.QStyle.PixelMetric.PM_ScrollBarExtent
    )
    page_width = max(page.sizeHint().width(), page._required_width)
    dialog_chrome_width = dialog.sizeHint().width() - page.sizeHint().width()
    return max(760, page_width + dialog_chrome_width + scroll_bar_width)


def _make_dialog(
    qtbot: QtBot,
    applied: Applied,
    overrides: dict,
    succeed: bool,
    previewed: Previewed | None,
) -> SettingsDialog:
    config = load_config(config_file=None, config_overrides=overrides)

    def apply_setting(key_path: tuple[str, ...], value: object) -> bool:
        applied.append((key_path, value))
        return succeed

    def preview_shape_color(key_path: tuple[str, ...], value: list[int] | None) -> None:
        if previewed is not None:
            previewed.append((key_path, value))

    dialog = SettingsDialog(
        config=config,
        apply_setting=apply_setting,
        preview_shape_color=preview_shape_color,
        open_as_text=lambda: None,
    )
    qtbot.addWidget(dialog)
    return dialog


@pytest.fixture
def dialog(qtbot: QtBot, applied: Applied) -> SettingsDialog:
    return _make_dialog(
        qtbot=qtbot, applied=applied, overrides={}, succeed=True, previewed=None
    )


def test_no_apply_on_construction(dialog: SettingsDialog, applied: Applied) -> None:
    assert applied == []


def test_existing_shape_suppression_is_disabled_by_default(
    dialog: SettingsDialog,
) -> None:
    checkbox = dialog._editors[("ai", "suppress_existing_shape_matches")]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    assert checkbox.isChecked() is False


def test_polygon_detail_slider_applies_integer_value(
    dialog: SettingsDialog, applied: Applied
) -> None:
    slider = dialog._editors[("mask_polygonization", "detail")]
    assert isinstance(slider, IntegerSlider)
    assert slider.value == 80

    slider.set_value(60)

    assert (("mask_polygonization", "detail"), 60) in applied


def test_unbounded_integer_edit_accepts_python_ints(
    qtbot: QtBot, applied: Applied
) -> None:
    initial = 2**31
    dialog = _make_dialog(
        qtbot=qtbot,
        applied=applied,
        overrides={"shape_color": {"auto": {"shift": initial}}},
        succeed=True,
        previewed=None,
    )
    edit = dialog._editors[("shape_color", "auto", "shift")]
    assert isinstance(edit, QtWidgets.QLineEdit)
    assert edit.text() == str(initial)

    edit.setText("not an integer")
    edit.editingFinished.emit()
    assert edit.text() == str(initial)
    assert applied == []

    edit.setText(str(initial + 1))
    edit.editingFinished.emit()
    assert (("shape_color", "auto", "shift"), initial + 1) in applied


def test_editors_have_accessible_names(dialog: SettingsDialog) -> None:
    for setting in schema.SETTINGS:
        editor = dialog._editors[setting.key_path]
        assert editor.accessibleName() == dialog.tr(setting.label)
        interface = QtGui.QAccessible.queryAccessibleInterface(editor)
        assert interface is not None
        assert any(
            relation & QtGui.QAccessible.RelationFlag.Label
            and related.text(QtGui.QAccessible.Text.Name) == dialog.tr(setting.label)
            for related, relation in interface.relations()
        )


def test_shape_color_mode_enables_only_its_control(
    dialog: SettingsDialog, applied: Applied
) -> None:
    mode = dialog._editors[("shape_color", "mode")]
    shift = dialog._editors[("shape_color", "auto", "shift")]
    uniform = dialog._editors[("shape_color", "uniform", "color")]
    fallback = dialog._editors[("shape_color", "by_label", "fallback")]
    shift_row = shift.parentWidget()
    uniform_row = uniform.parentWidget()
    fallback_row = fallback.parentWidget()
    assert shift_row is not None
    assert uniform_row is not None
    assert fallback_row is not None
    assert isinstance(mode, QtWidgets.QComboBox)
    assert shift.isEnabled()
    assert not uniform.isEnabled()
    assert not fallback.isEnabled()
    assert all(label.isEnabled() for label in shift_row.findChildren(QtWidgets.QLabel))
    assert all(
        not label.isEnabled()
        for row in (uniform_row, fallback_row)
        for label in row.findChildren(QtWidgets.QLabel)
    )

    mode.setCurrentIndex(mode.findData("uniform"))

    assert (("shape_color", "mode"), "uniform") in applied
    assert not shift.isEnabled()
    assert uniform.isEnabled()
    assert not fallback.isEnabled()
    assert all(
        not label.isEnabled()
        for row in (shift_row, fallback_row)
        for label in row.findChildren(QtWidgets.QLabel)
    )
    assert all(
        label.isEnabled() for label in uniform_row.findChildren(QtWidgets.QLabel)
    )


def test_shape_color_picker_applies_rgb(
    qtbot: QtBot,
    applied: Applied,
    use_widget_color_dialog: None,
) -> None:
    previewed: Previewed = []
    dialog = _make_dialog(
        qtbot=qtbot,
        applied=applied,
        overrides={"shape_color": {"mode": "uniform"}},
        previewed=previewed,
        succeed=True,
    )
    swatch = dialog._editors[("shape_color", "uniform", "color")]
    assert isinstance(swatch, _ColorSwatchButton)

    def choose_color() -> None:
        picker = next(
            widget
            for widget in QtWidgets.QApplication.topLevelWidgets()
            if isinstance(widget, QtWidgets.QColorDialog)
        )
        picker.setCurrentColor(QtGui.QColor(12, 34, 56))
        picker.accept()

    QtCore.QTimer.singleShot(50, choose_color)
    swatch.click()

    assert swatch.get_rgb() == (12, 34, 56)
    assert swatch.toolTip() == "RGB: 12, 34, 56"
    assert swatch.accessibleDescription() == "RGB: 12, 34, 56"
    assert applied == [(("shape_color", "uniform", "color"), [12, 34, 56])]
    assert previewed == [
        (("shape_color", "uniform", "color"), [12, 34, 56]),
        (("shape_color", "uniform", "color"), None),
    ]


def test_setting_note_is_accessible_description(dialog: SettingsDialog) -> None:
    setting = next(
        setting
        for setting in schema.SETTINGS
        if setting.key_path == ("shape_color", "by_label", "fallback")
    )
    assert setting.note is not None
    swatch = dialog._editors[setting.key_path]
    assert isinstance(swatch, _ColorSwatchButton)
    assert swatch.accessibleDescription() == (
        f"RGB: 0, 255, 0. {dialog.tr(setting.note)}"
    )


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
    dialog = _make_dialog(
        qtbot=qtbot,
        applied=applied,
        overrides={"language": "xx_ZZ"},
        succeed=True,
        previewed=None,
    )
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
        succeed=True,
        previewed=None,
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
        previewed=None,
    )
    checkbox = dialog._editors[("display_label_popup",)]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    assert checkbox.isChecked()

    checkbox.setChecked(False)

    assert checkbox.isChecked()  # reverted to the last-saved value


def test_failed_apply_reverts_labels_editor(qtbot: QtBot, applied: Applied) -> None:
    dialog = _make_dialog(
        qtbot=qtbot,
        applied=applied,
        overrides={"labels": ["cat"]},
        succeed=False,
        previewed=None,
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
        dialog = _make_dialog(
            qtbot=qtbot, applied=applied, overrides={}, succeed=True, previewed=None
        )
        navigation = dialog._page._navigation
        long_title = "Продолжение работы между изображениями"

        assert navigation.item(3).text() == long_title
        assert navigation.item(3).toolTip() == long_title
        assert navigation.textElideMode() == QtCore.Qt.TextElideMode.ElideRight
        assert navigation.width() == 240

        with qtbot.waitExposed(dialog):
            dialog.show()
        # A screen narrower than the dialog wants leaves it no room to keep the
        # content out of a horizontal scroll bar.
        if dialog.width() < _preferred_width(dialog):
            pytest.skip("this screen is narrower than the settings content")
        assert dialog._page._scroll_area.horizontalScrollBar().maximum() == 0
    finally:
        qapp.removeTranslator(translator)


def test_default_size_scrolls_vertically_only(
    qtbot: QtBot, dialog: SettingsDialog
) -> None:
    with qtbot.waitExposed(dialog):
        dialog.show()

    if _preferred_width(dialog) > 760:
        pytest.skip("this font needs the dialog wider than its default size")

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
    with qtbot.waitExposed(dialog):
        dialog.show()
    if dialog.width() < _preferred_width(dialog):
        pytest.skip("this screen is narrower than the settings content")
    minimum_width = dialog.width()

    dialog.resize(minimum_width - 200, dialog.height())

    assert dialog.width() == minimum_width
    assert dialog._page._scroll_area.horizontalScrollBar().maximum() == 0


@pytest.mark.parametrize("target", range(len(typing.get_args(schema.Group))))
def test_navigation_jumps_to_group(
    qtbot: QtBot, dialog: SettingsDialog, target: int
) -> None:
    with qtbot.waitExposed(dialog):
        dialog.show()

    scroll_bar = dialog._page._scroll_area.verticalScrollBar()
    # Start scrolled: from the top, a broken jump that moves the scroll bar but not
    # the content can still leave the content where the assertions expect it.
    scroll_bar.setValue(scroll_bar.maximum() // 2)

    navigation = dialog._page._navigation
    item = navigation.item(target)
    assert item is not None
    qtbot.mouseClick(
        navigation.viewport(),
        QtCore.Qt.MouseButton.LeftButton,
        pos=navigation.visualItemRect(item).center(),
    )

    group_top = (
        dialog._page._groups[target].mapTo(dialog._page._content, QtCore.QPoint()).y()
    )
    expected = min(group_top, scroll_bar.maximum())
    assert scroll_bar.value() == expected
    viewport = dialog._page._scroll_area.viewport()
    assert -dialog._page._content.mapTo(viewport, QtCore.QPoint()).y() == expected
    assert navigation.currentRow() == target


def test_scrolling_updates_navigation(qtbot: QtBot, dialog: SettingsDialog) -> None:
    with qtbot.waitExposed(dialog):
        dialog.show()

    scroll_bar = dialog._page._scroll_area.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum() - 1)
    assert dialog._page._navigation.currentRow() == len(dialog._page._groups) - 2

    scroll_bar.setValue(scroll_bar.maximum())
    assert dialog._page._navigation.currentRow() == len(dialog._page._groups) - 1


def test_scrolling_updates_navigation_after_a_jump(
    qtbot: QtBot, dialog: SettingsDialog
) -> None:
    with qtbot.waitExposed(dialog):
        dialog.show()

    navigation = dialog._page._navigation
    item = navigation.item(1)
    assert item is not None
    qtbot.mouseClick(
        navigation.viewport(),
        QtCore.Qt.MouseButton.LeftButton,
        pos=navigation.visualItemRect(item).center(),
    )

    scroll_bar = dialog._page._scroll_area.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum())
    assert navigation.currentRow() == len(dialog._page._groups) - 1


def test_navigation_returns_to_first_group_when_resize_removes_scrollbar(
    qtbot: QtBot, dialog: SettingsDialog
) -> None:
    with qtbot.waitExposed(dialog):
        dialog.show()

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
    with qtbot.waitExposed(dialog):
        dialog.show()
    scroll_bar = dialog._page._scroll_area.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum() // 2)
    expected = scroll_bar.value()

    dialog.close()
    dialog.show()

    assert scroll_bar.value() == expected


def test_short_dialog_scrolls_page(qtbot: QtBot, dialog: SettingsDialog) -> None:
    dialog.resize(dialog.width(), 160)
    with qtbot.waitExposed(dialog):
        dialog.show()

    assert dialog._page._scroll_area.verticalScrollBar().maximum() > 0


def test_large_font_uses_default_size_with_scrolling(
    qtbot: QtBot, applied: Applied
) -> None:
    original_font = QtWidgets.QApplication.font()
    large_font = QtGui.QFont(original_font)
    large_font.setPointSize(24)
    QtWidgets.QApplication.setFont(large_font)
    try:
        dialog = _make_dialog(
            qtbot=qtbot, applied=applied, overrides={}, succeed=True, previewed=None
        )
        with qtbot.waitExposed(dialog):
            dialog.show()

        available_size = dialog.screen().availableGeometry().size()
        assert _preferred_width(dialog) >= 760
        assert dialog.width() == min(_preferred_width(dialog), available_size.width())
        assert dialog.height() == min(590, available_size.height())
        assert dialog._page._scroll_area.verticalScrollBar().maximum() > 0
    finally:
        QtWidgets.QApplication.setFont(original_font)
