from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._widgets._settings_dialog import _LabelFlagsEditor
from labelme._yaml import safe_load

from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import draw_triangle
from .conftest import schedule_on_dialog
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
@pytest.mark.parametrize("close_action", ["button", "escape", "window"])
def test_closing_untouched_shape_flag_settings_preserves_rules_exactly(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    close_action: str,
) -> None:
    config_file = tmp_path / "labelmerc"
    original = (
        b"label_flags:\n"
        b'  "^car$":\n'
        b'    - " leading"\n'
        b'    - "trailing "\n'
        b'    - "embedded\\nnewline"\n'
    )
    expected_rules = {"^car$": [" leading", "trailing ", "embedded\nnewline"]}
    config_file.write_bytes(original)
    win = main_win(config_file=config_file)

    win._open_settings()
    settings = win._settings_dialog
    assert settings is not None
    if close_action == "button":
        close_button = next(
            button
            for button in settings.findChildren(QtWidgets.QPushButton)
            if button.text() == "Close"
        )
        qtbot.mouseClick(close_button, QtCore.Qt.MouseButton.LeftButton)
    elif close_action == "escape":
        qtbot.keyClick(settings, QtCore.Qt.Key.Key_Escape)
    else:
        settings.close()

    assert not settings.isVisible()
    assert config_file.read_bytes() == original
    assert win._config["label_flags"] == expected_rules


@pytest.mark.gui
@pytest.mark.parametrize("display_popup", [False, True])
def test_shape_flag_settings_apply_without_changing_existing_annotation(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    data_path: Path,
    display_popup: bool,
) -> None:
    config_file = tmp_path / "labelmerc"
    config_file.write_text(
        f"auto_save: false\ndisplay_label_popup: {str(display_popup).lower()}\n"
        "labels: [car]\n# Keep this comment\n"
    )
    win = main_win(
        config_file=config_file,
        file_or_dir=data_path / "raw/2011_000003.jpg",
        output_dir=tmp_path,
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._open_settings()
    settings = win._settings_dialog
    assert settings is not None
    editor = settings._editors[("label_flags",)]
    assert isinstance(editor, _LabelFlagsEditor)
    editor._add_button.click()
    pattern, flags, _ = editor._rows[0]
    pattern.setText("^car$")
    flags.setPlainText("occluded\ndamaged, minor")
    settings.accept()
    expected_rules = {"^car$": ["occluded", "damaged, minor"]}
    assert safe_load(config_file.read_text())["label_flags"] == expected_rules
    assert "# Keep this comment" in config_file.read_text()
    assert not win._is_changed
    canvas = win._canvas_widgets.canvas
    assert canvas.shapes == []

    item = win._docks.unique_label_list.find_label_item(label="car")
    assert item is not None
    win._docks.unique_label_list.setCurrentItem(item)
    vertices = ((0.3, 0.3), (0.6, 0.3), (0.6, 0.6))
    draw_triangle(qtbot=qtbot, win=win, vertices=vertices)
    if display_popup:
        schedule_on_dialog(
            label_dialog=win._label_dialog, action=win._label_dialog.accept
        )
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=vertices[0])
    assert len(canvas.shapes) == 1
    shape = canvas.shapes[0]
    assert shape.flags == {"occluded": False, "damaged, minor": False}
    assert shape.flags is not None
    shape.flags["occluded"] = True
    annotation_path = tmp_path / "annotation.json"
    assert win.save_labels(label_path=str(annotation_path))
    win.mark_clean()

    win._open_settings()
    pattern, flags, remove = editor._rows[0]
    flags.setPlainText("truncated")
    settings.accept()
    assert not win._is_changed
    assert shape.flags == {"occluded": True, "damaged, minor": False}
    label_dialog = win._label_dialog

    def edit_existing_shape() -> None:
        assert label_dialog._collect_flags() == {
            "truncated": False,
            "occluded": True,
            "damaged, minor": False,
        }
        label_dialog.edit.setText("person")
        label_dialog.accept()

    win._docks.label_list.select_item(item=next(iter(win._docks.label_list)))
    schedule_on_dialog(label_dialog=label_dialog, action=edit_existing_shape)
    win._edit_label()
    assert shape.label == "person"
    assert shape.flags == {"occluded": True, "damaged, minor": False}
    assert win.save_labels(label_path=str(annotation_path))
    assert json.loads(annotation_path.read_text())["shapes"][0]["flags"] == shape.flags
    win._load_file(image_or_label_path=str(annotation_path))
    qtbot.waitUntil(lambda: bool(canvas.shapes))
    assert canvas.shapes[0].flags == shape.flags

    win._open_settings()
    remove.click()
    assert "label_flags" not in safe_load(config_file.read_text())
    assert canvas.shapes[0].flags == {"occluded": True, "damaged, minor": False}
    settings.accept()
    win.close()
    reopened = main_win(config_file=config_file)
    assert reopened._config["label_flags"] is None


@pytest.mark.gui
def test_invalid_shape_flag_rules_leave_last_valid_config_active(
    *,
    main_win: MainWinFactory,
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "labelmerc"
    original = "label_flags:\n  ^car$: [occluded]\n"
    config_file.write_text(original)
    win = main_win(config_file=config_file)
    win._open_settings()
    settings = win._settings_dialog
    assert settings is not None
    editor = settings._editors[("label_flags",)]
    assert isinstance(editor, _LabelFlagsEditor)
    editor._add_button.click()
    pattern, flags, remove = editor._rows[1]
    for invalid_pattern, names, error in (
        ("", "", "Enter a pattern"),
        ("car(", "truncated", "Invalid regular expression"),
        ("^car$", "truncated", "Duplicate label pattern"),
    ):
        pattern.setText(invalid_pattern)
        flags.setPlainText(names)
        settings.accept()
        assert error in editor._error.text()
        assert config_file.read_text() == original
        assert win._config["label_flags"] == {"^car$": ["occluded"]}
        win._open_settings()
    pattern.setText(".*")
    flags.setPlainText("damaged, minor\ntruncated")
    settings.accept()
    expected = {"^car$": ["occluded"], ".*": ["damaged, minor", "truncated"]}
    assert win._config["label_flags"] == expected
    assert safe_load(config_file.read_text())["label_flags"] == expected
    win.close()
    reopened = main_win(config_file=config_file)
    reopened._open_settings()
    new_settings = reopened._settings_dialog
    assert new_settings is not None
    new_editor = new_settings._editors[("label_flags",)]
    assert isinstance(new_editor, _LabelFlagsEditor)
    assert new_editor._rows[1][1].toPlainText() == "damaged, minor\ntruncated"
