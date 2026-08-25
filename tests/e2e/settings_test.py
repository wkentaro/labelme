from __future__ import annotations

from pathlib import Path

import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._config import _writer
from labelme._widgets import SettingsDialog
from labelme._widgets._integer_slider import IntegerSlider
from labelme._widgets.label_list_widget import LABEL_COLOR_ROLE
from labelme._widgets.settings_dialog import _ColorSwatchButton
from labelme._widgets.settings_dialog import _PlainTextEdit
from labelme._yaml import safe_load

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


def _open_settings_dialog(win: MainWindow) -> SettingsDialog:
    win._open_settings()
    dialog = win._settings_dialog
    assert dialog is not None
    return dialog


@pytest.fixture
def editable_config_file(tmp_path: Path) -> Path:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("auto_save: true\n")
    return config_file


@pytest.fixture
def settings_with_label_history(
    main_win: MainWinFactory,
    editable_config_file: Path,
) -> tuple[MainWindow, SettingsDialog]:
    win = main_win(config_file=editable_config_file)
    win._label_dialog.add_label_history(label="bird")
    return win, _open_settings_dialog(win=win)


@pytest.mark.gui
def test_startup_syncs_first_ai_model_without_rewriting_config(
    main_win: MainWinFactory,
    qtbot: QtBot,
    editable_config_file: Path,
    pause: bool,
) -> None:
    original_config = "ai:\n  default: EfficientSam (speed)\nauto_save: true\n"
    editable_config_file.write_text(original_config)

    win = main_win(config_file=editable_config_file)

    assert win._canvas_widgets.canvas.get_ai_model_name() == "efficientsam:10m"
    assert editable_config_file.read_text() == original_config

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_startup_applies_existing_shape_suppression_override(
    main_win: MainWinFactory,
    qtbot: QtBot,
    editable_config_file: Path,
    pause: bool,
) -> None:
    original_config = "ai:\n  suppress_existing_shape_matches: true\n"
    editable_config_file.write_text(original_config)

    win = main_win(config_file=editable_config_file)

    assert win._canvas_widgets.canvas._ai_suppress_existing_shape_matches is True
    assert editable_config_file.read_text() == original_config

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


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
    dialog = _open_settings_dialog(win=win)

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
def test_shape_color_picker_previews_and_persists_only_on_accept(
    main_win: MainWinFactory,
    qtbot: QtBot,
    use_widget_color_dialog: None,
    editable_config_file: Path,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=data_path / "annotated/2011_000003.json",
        config_file=editable_config_file,
    )
    dialog = _open_settings_dialog(win=win)
    mode = dialog._editors[("shape_color", "mode")]
    assert isinstance(mode, QtWidgets.QComboBox)
    mode.setCurrentIndex(mode.findData("uniform"))

    swatch = dialog._editors[("shape_color", "uniform", "color")]
    assert isinstance(swatch, _ColorSwatchButton)
    expected = QtGui.QColor(12, 34, 56)
    unique_labels = win._docks.unique_label_list
    assert unique_labels.count() > 0
    label = unique_labels.item(0).data(Qt.ItemDataRole.UserRole)
    color_resolver = win._canvas_widgets.canvas._color_resolver
    assert isinstance(label, str)
    assert color_resolver is not None
    original = unique_labels.item(0).data(LABEL_COLOR_ROLE)
    persisted_before_pick = safe_load(editable_config_file.read_text())
    preview_checks: list[tuple[bool, bool, bool, bool]] = []

    def preview_color(*, accept: bool) -> None:
        picker = next(
            widget
            for widget in QtWidgets.QApplication.topLevelWidgets()
            if isinstance(widget, QtWidgets.QColorDialog)
        )
        picker.setCurrentColor(expected)
        QtWidgets.QApplication.processEvents()
        preview_checks.append(
            (
                all(
                    unique_labels.item(row).data(LABEL_COLOR_ROLE) == expected
                    for row in range(unique_labels.count())
                ),
                all(
                    item.data(LABEL_COLOR_ROLE) == expected
                    for item in win._docks.label_list
                ),
                color_resolver(label) == (12, 34, 56),
                safe_load(editable_config_file.read_text()) == persisted_before_pick,
            )
        )
        if accept:
            picker.accept()
        else:
            picker.reject()

    QtCore.QTimer.singleShot(50, lambda: preview_color(accept=False))
    swatch.click()

    assert preview_checks == [(True, True, True, True)]
    assert unique_labels.item(0).data(LABEL_COLOR_ROLE) == original
    assert safe_load(editable_config_file.read_text()) == persisted_before_pick

    QtCore.QTimer.singleShot(50, lambda: preview_color(accept=True))
    swatch.click()

    assert preview_checks == [(True, True, True, True)] * 2
    persisted = safe_load(editable_config_file.read_text())
    assert persisted["shape_color"] == {
        "mode": "uniform",
        "uniform": {"color": [12, 34, 56]},
    }

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_show_labels_toggle_applies_to_canvas(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)
    canvas = win._canvas_widgets.canvas
    assert canvas._show_labels is False

    dialog = _open_settings_dialog(win=win)
    checkbox = dialog._editors[("shape", "show_labels")]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    checkbox.setChecked(True)  # toggling applies immediately, without restart
    dialog.accept()

    assert win._config["shape"]["show_labels"] is True
    assert canvas._show_labels is True
    assert safe_load(editable_config_file.read_text())["shape"]["show_labels"] is True

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_existing_shape_suppression_toggle_applies_to_canvas(
    main_win: MainWinFactory,
    qtbot: QtBot,
    editable_config_file: Path,
    pause: bool,
) -> None:
    win = main_win(config_file=editable_config_file)
    canvas = win._canvas_widgets.canvas
    assert canvas._ai_suppress_existing_shape_matches is False

    dialog = _open_settings_dialog(win=win)
    checkbox = dialog._editors[("ai", "suppress_existing_shape_matches")]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    checkbox.setChecked(True)

    assert win._config["ai"]["suppress_existing_shape_matches"] is True
    assert canvas._ai_suppress_existing_shape_matches is True
    assert (
        safe_load(editable_config_file.read_text())["ai"][
            "suppress_existing_shape_matches"
        ]
        is True
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_label_edit_preserves_label_history(
    settings_with_label_history: tuple[MainWindow, SettingsDialog],
    qtbot: QtBot,
    pause: bool,
) -> None:
    win, dialog = settings_with_label_history
    old_label_dialog = win._label_dialog

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

    dialog = _open_settings_dialog(win=win)
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

    dialog = _open_settings_dialog(win=win)

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
def test_setting_controls_revert_when_write_fails(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_file = tmp_path / "labelmerc.yaml"
    config_file.write_text("display_label_popup: true\n")
    win = main_win(config_file=config_file)

    warned: list[object] = []
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: warned.append(args[2]),
    )

    dialog = _open_settings_dialog(win=win)
    checkbox = dialog._editors[("display_label_popup",)]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    assert checkbox.isChecked()
    auto_save_editor = dialog._editors[("auto_save",)]
    assert isinstance(auto_save_editor, QtWidgets.QCheckBox)
    assert auto_save_editor.isChecked()
    ai_editor = dialog._editors[("ai", "default")]
    assert isinstance(ai_editor, QtWidgets.QComboBox)
    ai_dock = win._ai_annotation._model_combo
    assert ai_dock.currentText() == "Sam2 (balanced)"

    # Refuse the save at the boundary a read-only config directory would;
    # injecting the failure keeps it reachable on Windows and as root, where
    # a read-only directory does not block writes.
    def _refuse_write(config_file: Path, content: str) -> None:
        raise PermissionError(f"injected write failure: {config_file}")

    monkeypatch.setattr(_writer, "_atomic_write", _refuse_write)
    checkbox.setChecked(False)
    win._actions.save_auto.trigger()
    ai_dock.setCurrentIndex(ai_dock.findText("EfficientSam (speed)"))

    assert len(warned) == 3
    assert checkbox.isChecked()  # editor reverted to the last-saved value
    assert win._actions.save_auto.isChecked()
    assert auto_save_editor.isChecked()
    assert ai_dock.currentText() == "Sam2 (balanced)"
    assert ai_editor.currentData() == "Sam2 (balanced)"
    assert win._canvas_widgets.canvas.get_ai_model_name() == "sam2:latest"
    assert win._config["display_label_popup"] is True
    assert win._config["auto_save"] is True
    assert win._config["ai"]["default"] == "Sam2 (balanced)"
    assert safe_load(config_file.read_text()) == {"display_label_popup": True}

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
    dialog = _open_settings_dialog(win=win)

    deleted: list[bool] = []
    dialog.destroyed.connect(lambda: deleted.append(True))
    monkeypatch.setattr("labelme._app.subprocess.Popen", lambda *args, **kwargs: None)

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


@pytest.mark.gui
def test_keep_prev_dialog_toggle_checks_menu_action(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)
    assert not win._actions.toggle_keep_prev_mode.isChecked()

    dialog = _open_settings_dialog(win=win)
    checkbox = dialog._editors[("keep_prev",)]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    checkbox.setChecked(True)

    assert win._actions.toggle_keep_prev_mode.isChecked()
    assert win._config["keep_prev"] is True
    assert safe_load(editable_config_file.read_text())["keep_prev"] is True

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize(
    ("action_name", "key_path"),
    [
        ("save_auto", ("auto_save",)),
        ("save_with_image_data", ("with_image_data",)),
        ("toggle_keep_prev_mode", ("keep_prev",)),
        ("keep_prev_zoom", ("keep_prev_scale",)),
        (
            "toggle_keep_prev_brightness_contrast",
            ("keep_prev_brightness_contrast",),
        ),
        ("fill_drawing", ("canvas", "fill_drawing")),
    ],
)
def test_menu_toggle_persists_and_syncs_settings_dialog(
    main_win: MainWinFactory,
    qtbot: QtBot,
    editable_config_file: Path,
    pause: bool,
    action_name: str,
    key_path: tuple[str, ...],
) -> None:
    win = main_win(config_file=editable_config_file)
    dialog = _open_settings_dialog(win=win)
    editor = dialog._editors[key_path]
    assert isinstance(editor, QtWidgets.QCheckBox)

    action = getattr(win._actions, action_name)
    expected = not action.isChecked()
    action.trigger()

    config_value = win._config
    persisted_value = safe_load(editable_config_file.read_text())
    for key in key_path:
        config_value = config_value[key]
        persisted_value = persisted_value[key]
    assert config_value is expected
    assert persisted_value is expected
    assert editor.isChecked() is expected

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_fill_drawing_dialog_toggle_applies_to_canvas(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)
    canvas = win._canvas_widgets.canvas
    assert canvas._fill_drawing

    dialog = _open_settings_dialog(win=win)
    checkbox = dialog._editors[("canvas", "fill_drawing")]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    checkbox.setChecked(False)

    assert not canvas._fill_drawing
    assert not win._actions.fill_drawing.isChecked()
    assert (
        safe_load(editable_config_file.read_text())["canvas"]["fill_drawing"] is False
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_fill_drawing_menu_toggle_applies_with_cli_overrides(
    main_win: MainWinFactory, qtbot: QtBot, pause: bool
) -> None:
    win = main_win(config_overrides={"canvas": {"fill_drawing": True}})
    canvas = win._canvas_widgets.canvas
    assert canvas._fill_drawing

    win._actions.fill_drawing.trigger()

    assert win._config["canvas"]["fill_drawing"] is False
    assert canvas._fill_drawing is False

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_sort_labels_dialog_toggle_rebuilds_label_dialog(
    settings_with_label_history: tuple[MainWindow, SettingsDialog],
    qtbot: QtBot,
    editable_config_file: Path,
    pause: bool,
) -> None:
    win, dialog = settings_with_label_history
    assert win._config["sort_labels"] is True
    old_label_dialog = win._label_dialog
    deleted: list[bool] = []
    old_label_dialog.destroyed.connect(lambda: deleted.append(True))

    checkbox = dialog._editors[("sort_labels",)]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    assert checkbox.isChecked()
    checkbox.setChecked(False)

    assert win._config["sort_labels"] is False
    # sort_labels is only read at LabelDialog construction, so the live-apply
    # rebuilds the dialog instead of updating it in place.
    assert win._label_dialog is not old_label_dialog
    assert win._label_dialog._sort_labels is False
    assert win._label_dialog.label_history == ["bird"]
    assert safe_load(editable_config_file.read_text())["sort_labels"] is False
    qtbot.waitUntil(lambda: bool(deleted))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_show_label_text_field_dialog_toggle_rebuilds_label_dialog(
    settings_with_label_history: tuple[MainWindow, SettingsDialog],
    qtbot: QtBot,
    editable_config_file: Path,
    pause: bool,
) -> None:
    win, dialog = settings_with_label_history
    assert win._label_dialog.edit.parent() is not None

    checkbox = dialog._editors[("show_label_text_field",)]
    assert isinstance(checkbox, QtWidgets.QCheckBox)
    assert checkbox.isChecked()
    checkbox.setChecked(False)

    assert win._config["show_label_text_field"] is False
    assert win._label_dialog.edit.parent() is None
    assert win._label_dialog.label_history == ["bird"]
    assert safe_load(editable_config_file.read_text())["show_label_text_field"] is False

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_label_completion_dialog_change_rebuilds_label_dialog(
    settings_with_label_history: tuple[MainWindow, SettingsDialog],
    qtbot: QtBot,
    editable_config_file: Path,
    pause: bool,
) -> None:
    win, dialog = settings_with_label_history
    assert win._config["label_completion"] == "startswith"

    combo = dialog._editors[("label_completion",)]
    assert isinstance(combo, QtWidgets.QComboBox)
    combo.setCurrentIndex(combo.findData("contains"))

    assert win._config["label_completion"] == "contains"
    completer = win._label_dialog.edit.completer()
    assert completer is not None
    assert completer.filterMode() == Qt.MatchFlag.MatchContains
    assert (
        completer.completionMode()
        == QtWidgets.QCompleter.CompletionMode.PopupCompletion
    )
    assert win._label_dialog.label_history == ["bird"]
    assert safe_load(editable_config_file.read_text())["label_completion"] == "contains"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_ai_default_dialog_change_syncs_dock_combo(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)
    assert win._config["ai"]["default"] == "Sam2 (balanced)"
    dock_combo = win._ai_annotation._model_combo
    assert dock_combo.currentText() == "Sam2 (balanced)"

    dialog = _open_settings_dialog(win=win)
    combo = dialog._editors[("ai", "default")]
    assert isinstance(combo, QtWidgets.QComboBox)
    combo.setCurrentIndex(combo.findData("EfficientSam (speed)"))

    assert win._config["ai"]["default"] == "EfficientSam (speed)"
    assert dock_combo.currentText() == "EfficientSam (speed)"
    assert win._canvas_widgets.canvas.get_ai_model_name() == "efficientsam:10m"
    assert (
        safe_load(editable_config_file.read_text())["ai"]["default"]
        == "EfficientSam (speed)"
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_ai_model_choices_follow_point_prompt_mode(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)
    win._switch_canvas_mode(edit=False, create_mode="ai_points_to_shape")

    dialog = _open_settings_dialog(win=win)
    combo = dialog._editors[("ai", "default")]
    assert isinstance(combo, QtWidgets.QComboBox)
    sam3_index = combo.findData("Sam3")
    assert not combo.model().flags(combo.model().index(sam3_index, 0)) & (
        Qt.ItemFlag.ItemIsEnabled
    )
    assert combo.model().data(
        combo.model().index(sam3_index, 0), Qt.ItemDataRole.ToolTipRole
    ) == (
        "Unavailable in AI-Points mode because this model does not support point "
        "prompts."
    )

    combo.setCurrentIndex(sam3_index)

    assert combo.currentData() == "Sam2 (balanced)"
    assert win._ai_annotation.current_model_id == "sam2:latest"
    assert win._config["ai"]["default"] == "Sam2 (balanced)"

    win._switch_canvas_mode(edit=False, create_mode="ai_box_to_shape")

    assert combo.model().flags(combo.model().index(sam3_index, 0)) & (
        Qt.ItemFlag.ItemIsEnabled
    )
    assert (
        combo.model().data(
            combo.model().index(sam3_index, 0), Qt.ItemDataRole.ToolTipRole
        )
        == ""
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_ai_dock_change_persists_and_syncs_settings_dialog(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)
    dialog = _open_settings_dialog(win=win)
    settings_combo = dialog._editors[("ai", "default")]
    assert isinstance(settings_combo, QtWidgets.QComboBox)

    dock_combo = win._ai_annotation._model_combo
    dock_combo.setCurrentIndex(dock_combo.findText("EfficientSam (speed)"))

    assert win._config["ai"]["default"] == "EfficientSam (speed)"
    assert settings_combo.currentData() == "EfficientSam (speed)"
    assert win._canvas_widgets.canvas.get_ai_model_name() == "efficientsam:10m"
    assert (
        safe_load(editable_config_file.read_text())["ai"]["default"]
        == "EfficientSam (speed)"
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_polygon_detail_popover_and_settings_stay_in_sync(
    main_win: MainWinFactory, qtbot: QtBot, editable_config_file: Path, pause: bool
) -> None:
    win = main_win(config_file=editable_config_file)
    dialog = _open_settings_dialog(win=win)
    settings_slider = dialog._editors[("mask_polygonization", "detail")]
    assert isinstance(settings_slider, IntegerSlider)

    toolbar_slider = win._ai_annotation._polygon_detail_slider
    toolbar_slider.set_value(60)

    assert win._config["mask_polygonization"]["detail"] == 60
    assert settings_slider.value == 60
    assert win._canvas_widgets.canvas._ai_assist_session.polygon_detail == 60
    persisted = safe_load(editable_config_file.read_text())
    assert persisted["mask_polygonization"]["detail"] == 60

    settings_slider.set_value(70)

    assert toolbar_slider.value == 70
    assert win._canvas_widgets.canvas._ai_assist_session.polygon_detail == 70

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
