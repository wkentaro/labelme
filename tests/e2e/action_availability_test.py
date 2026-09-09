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
    assert all(not action.isEnabled() for action in visibility_actions)

    assert win._load_file(
        image_or_label_path=str(data_path / "annotated/2011_000003.jpg")
    )
    assert win._actions.save_as.isEnabled()
    assert all(action.isEnabled() for action in visibility_actions)

    assert win._load_file(image_or_label_path=str(data_path / "raw/2011_000003.jpg"))
    assert win._actions.save_as.isEnabled()
    assert all(not action.isEnabled() for action in visibility_actions)

    win.close_file()
    assert not win._actions.save_as.isEnabled()
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
