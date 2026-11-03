from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._shape import Shape
from labelme._widgets import LabelDialogEntry

from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_actions_follow_image_and_shapes(
    *, main_win: MainWinFactory, data_path: Path
) -> None:
    win = main_win(config_overrides={"auto_save": False})
    visibility_actions = (
        win._actions.hide_all,
        win._actions.show_all,
        win._actions.toggle_all,
    )
    assert not win._actions.save_as.isEnabled()
    assert not win._actions.close.isEnabled()
    assert not win._canvas_widgets.zoom_widget.isEnabled()
    assert not win._actions.brightness_contrast.isEnabled()
    assert all(not action.isEnabled() for action in visibility_actions)

    assert win._load_file(
        image_or_label_path=str(data_path / "annotated/2011_000003.jpg")
    )
    assert win._actions.save_as.isEnabled()
    assert win._actions.close.isEnabled()
    assert win._canvas_widgets.zoom_widget.isEnabled()
    assert win._actions.brightness_contrast.isEnabled()
    assert all(action.isEnabled() for action in visibility_actions)

    assert win._load_file(image_or_label_path=str(data_path / "raw/2011_000003.jpg"))
    assert win._actions.save_as.isEnabled()
    assert all(not action.isEnabled() for action in visibility_actions)

    win.close_file()
    assert not win._actions.save_as.isEnabled()
    assert not win._actions.close.isEnabled()
    assert not win._canvas_widgets.zoom_widget.isEnabled()
    assert not win._actions.brightness_contrast.isEnabled()
    assert all(not action.isEnabled() for action in visibility_actions)


@pytest.mark.gui
def test_canceling_a_point_label_restores_select_and_undo(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "raw/2011_000003.jpg"),
        config_overrides={"auto_save": False},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    monkeypatch.setattr(win._label_dialog, "popup", lambda *_a, **_k: None)

    win._actions.create_point_mode.trigger()
    click_canvas_fraction(qtbot=qtbot, canvas=win._canvas_widgets.canvas, xy=(0.5, 0.5))

    assert not win._canvas_widgets.canvas.shapes
    assert win._actions.edit_mode.isEnabled()
    assert not win._actions.undo.isEnabled()
    assert not win._is_changed


def _open_annotated(
    *, main_win: MainWinFactory, qtbot: QtBot, data_path: Path
) -> MainWindow:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.jpg"),
        config_overrides={"auto_save": False},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win


def _start_polygon(*, win: MainWindow, qtbot: QtBot) -> None:
    win._actions.create_mode.trigger()
    click_canvas_fraction(qtbot=qtbot, canvas=win._canvas_widgets.canvas, xy=(0.3, 0.3))
    assert win._canvas_widgets.canvas.is_drawing
    assert not win._actions.edit_mode.isEnabled()


@pytest.mark.gui
def test_switching_image_mid_draw_restores_select(
    *, main_win: MainWinFactory, qtbot: QtBot, data_path: Path
) -> None:
    win = _open_annotated(main_win=main_win, qtbot=qtbot, data_path=data_path)
    _start_polygon(win=win, qtbot=qtbot)

    assert win._load_file(
        image_or_label_path=str(data_path / "annotated/2011_000006.jpg")
    )

    assert win._actions.edit_mode.isEnabled()
    assert not win._actions.undo_last_point.isEnabled()


@pytest.mark.gui
def test_canceling_a_draft_keeps_delete_disabled_without_selection(
    *, main_win: MainWinFactory, qtbot: QtBot, data_path: Path
) -> None:
    win = _open_annotated(main_win=main_win, qtbot=qtbot, data_path=data_path)
    _start_polygon(win=win, qtbot=qtbot)

    qtbot.keyClick(win._canvas_widgets.canvas, Qt.Key.Key_Escape)

    assert not win._canvas_widgets.canvas.selected_shapes
    assert not win._actions.delete.isEnabled()


@pytest.mark.gui
def test_editing_a_label_enables_undo(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = _open_annotated(main_win=main_win, qtbot=qtbot, data_path=data_path)
    assert not win._actions.undo.isEnabled()
    canvas = win._canvas_widgets.canvas
    canvas.select_shapes(shapes=[canvas.shapes[0]])
    monkeypatch.setattr(
        win._label_dialog,
        "popup",
        lambda *_a, **_k: LabelDialogEntry(
            label="renamed", flags={}, group_id=None, description=""
        ),
    )

    # The edit leaves unsaved changes; skip the prompt when the window closes.
    monkeypatch.setattr(win, "_can_continue", lambda: True)

    win._edit_label()

    assert canvas.shapes[0].label == "renamed"
    assert win._actions.undo.isEnabled()


@pytest.mark.gui
def test_hiding_a_shape_mid_draw_keeps_undo_disabled(
    *, main_win: MainWinFactory, qtbot: QtBot, data_path: Path
) -> None:
    win = _open_annotated(main_win=main_win, qtbot=qtbot, data_path=data_path)
    _start_polygon(win=win, qtbot=qtbot)

    win._docks.label_list[0].setCheckState(Qt.CheckState.Unchecked)

    assert not win._actions.undo.isEnabled()
    assert not win._actions.edit_mode.isEnabled()


@pytest.mark.gui
def test_save_as_writes_empty_annotation(
    *,
    main_win: MainWinFactory,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(file_or_dir=data_path / "raw/2011_000003.jpg")
    destination = tmp_path / "empty.json"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda **_kwargs: (str(destination), ""),
    )
    assert win._actions.save_as.isEnabled()
    win._actions.save_as.trigger()
    assert json.loads(destination.read_text())["shapes"] == []
    assert win._load_file(image_or_label_path=str(destination))
    assert len(win._docks.label_list) == 0


@pytest.mark.gui
@pytest.mark.parametrize("clear_by", ["undo", "delete"])
def test_visibility_actions_follow_last_shape_and_restore(
    *,
    main_win: MainWinFactory,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clear_by: str,
) -> None:
    win = main_win(
        file_or_dir=data_path / "raw/2011_000003.jpg",
        config_overrides={"auto_save": False},
    )
    visibility_actions = (
        win._actions.hide_all,
        win._actions.show_all,
        win._actions.toggle_all,
    )
    shape = Shape(label="point", shape_type="point", points=np.array([[20.0, 20.0]]))
    win._insert_shapes([shape])
    win.mark_clean()
    assert all(action.isEnabled() for action in visibility_actions)

    if clear_by == "undo":
        win._actions.undo.trigger()
    else:
        monkeypatch.setattr(win, "_confirm_deletion", lambda **_kwargs: True)
        win.delete_selected_shapes()
    win.mark_clean()
    assert len(win._docks.label_list) == 0
    assert all(not action.isEnabled() for action in visibility_actions)
    assert win._actions.save_as.isEnabled()

    if clear_by == "delete":
        win._actions.undo.trigger()
    else:
        win._insert_shapes([shape])
    win.mark_clean()
    assert len(win._docks.label_list) == 1
    assert all(action.isEnabled() for action in visibility_actions)
    win._actions.hide_all.trigger()
    assert not win._canvas_widgets.canvas.shapes[0].visible
    win._actions.show_all.trigger()
    assert win._canvas_widgets.canvas.shapes[0].visible
    win._actions.toggle_all.trigger()
    assert not win._canvas_widgets.canvas.shapes[0].visible
    win.mark_clean()


@pytest.mark.gui
@pytest.mark.parametrize("keep_prev", [False, True])
@pytest.mark.parametrize("tool", ["point", "polygon"])
def test_drawing_tool_survives_file_transitions(
    *,
    main_win: MainWinFactory,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    keep_prev: bool,
    tool: str,
) -> None:
    win = main_win(
        file_or_dir=data_path / "annotated/2011_000003.jpg",
        config_overrides={"auto_save": False, "keep_prev": keep_prev},
    )
    canvas = win._canvas_widgets.canvas
    selected_action = dict(win._actions.draw)[tool]
    selected_action.trigger()
    drawing_mode = canvas.mode
    destination = tmp_path / "saved.json"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda **_kwargs: (str(destination), "")
    )

    assert win._load_file(image_or_label_path=str(data_path / "raw/2011_000003.jpg"))
    win.mark_clean()
    assert len(canvas.shapes) == (5 if keep_prev else 0)
    assert canvas.create_mode == tool
    assert canvas.mode == drawing_mode
    assert selected_action.isChecked()
    assert win._actions.edit_mode.isEnabled()

    win._actions.save_as.trigger()
    assert destination.exists()
    assert selected_action.isChecked()
    assert canvas.create_mode == tool
    assert canvas.mode == drawing_mode

    win.close_file()
    assert not win._actions.edit_mode.isEnabled()
    assert all(not action.isEnabled() for _, action in win._actions.draw)
    assert win._load_file(image_or_label_path=str(destination))
    assert selected_action.isChecked()
    assert canvas.create_mode == tool
    assert canvas.mode == drawing_mode
    assert win._actions.edit_mode.isEnabled()

    win._actions.edit_mode.trigger()
    assert canvas.mode != drawing_mode
    assert win._actions.edit_mode.isChecked()
    assert all(action.isEnabled() for _, action in win._actions.draw)
    assert not any(action.isChecked() for _, action in win._actions.draw)
    win.mark_clean()


@pytest.mark.gui
@pytest.mark.parametrize("auto_save", [False, True])
def test_delete_file_follows_carried_annotation_save_state(
    *, main_win: MainWinFactory, data_path: Path, auto_save: bool, qtbot: QtBot
) -> None:
    win = main_win(
        file_or_dir=data_path / "annotated/2011_000003.jpg",
        config_overrides={"keep_prev": True, "auto_save": auto_save},
    )
    assert win._actions.delete_file.isEnabled()
    labels = [shape.label for shape in win._canvas_widgets.canvas.shapes]
    image_path = data_path / "raw/2011_000003.jpg"
    assert win._load_file(image_or_label_path=str(image_path))
    win.mark_clean()
    assert [shape.label for shape in win._canvas_widgets.canvas.shapes] == labels
    qtbot.waitUntil(lambda: not win._save_writer.is_busy)
    assert image_path.with_suffix(".json").exists() == auto_save
    assert win._actions.delete_file.isEnabled() == auto_save


@pytest.mark.gui
def test_delete_file_enables_after_first_auto_save(
    *, main_win: MainWinFactory, data_path: Path, qtbot: QtBot
) -> None:
    image_path = data_path / "raw/2011_000003.jpg"
    win = main_win(file_or_dir=image_path, config_overrides={"auto_save": True})
    assert not win._actions.delete_file.isEnabled()
    win._insert_shapes(
        [Shape(label="point", shape_type="point", points=np.array([[20.0, 20.0]]))]
    )
    qtbot.waitUntil(lambda: not win._save_writer.is_busy)
    assert image_path.with_suffix(".json").exists()
    assert win._actions.delete_file.isEnabled()
