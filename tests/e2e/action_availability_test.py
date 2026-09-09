from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QFileDialog

from labelme._shape import Shape

from .conftest import MainWinFactory


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
    assert not selected_action.isEnabled()
    assert win._actions.edit_mode.isEnabled()

    win._actions.save_as.trigger()
    assert destination.exists()
    assert not selected_action.isEnabled()
    assert canvas.create_mode == tool
    assert canvas.mode == drawing_mode

    win.close_file()
    assert not win._actions.edit_mode.isEnabled()
    assert all(not action.isEnabled() for _, action in win._actions.draw)
    assert win._load_file(image_or_label_path=str(destination))
    assert not selected_action.isEnabled()
    assert canvas.create_mode == tool
    assert canvas.mode == drawing_mode
    assert win._actions.edit_mode.isEnabled()

    win._actions.edit_mode.trigger()
    assert canvas.mode != drawing_mode
    assert not win._actions.edit_mode.isEnabled()
    assert all(action.isEnabled() for _, action in win._actions.draw)
    win.mark_clean()


@pytest.mark.gui
@pytest.mark.parametrize("auto_save", [False, True])
def test_delete_file_follows_carried_annotation_save_state(
    *, main_win: MainWinFactory, data_path: Path, auto_save: bool
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
    assert image_path.with_suffix(".json").exists() == auto_save
    assert win._actions.delete_file.isEnabled() == auto_save


@pytest.mark.gui
def test_delete_file_enables_after_first_auto_save(
    *, main_win: MainWinFactory, data_path: Path
) -> None:
    image_path = data_path / "raw/2011_000003.jpg"
    win = main_win(file_or_dir=image_path, config_overrides={"auto_save": True})
    assert not win._actions.delete_file.isEnabled()
    win._insert_shapes(
        [Shape(label="point", shape_type="point", points=np.array([[20.0, 20.0]]))]
    )
    assert image_path.with_suffix(".json").exists()
    assert win._actions.delete_file.isEnabled()
