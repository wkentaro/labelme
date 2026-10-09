from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._app import _shapes_from_dicts
from labelme._label_file import read_label_file

from ..conftest import close_or_pause


@pytest.mark.gui
def test_toggle_shape_lock_action(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    annotated_win._actions.save_auto.setChecked(False)
    canvas = annotated_win._canvas_widgets.canvas
    assert len(canvas.shapes) == 5

    item = annotated_win._docks.label_list[0]
    annotated_win._docks.label_list.select_item(item=item)
    assert len(canvas.selected_shapes) == 1
    target = canvas.selected_shapes[0]
    assert not target.locked

    lock_action = annotated_win._actions.toggle_shape_lock
    assert lock_action.isEnabled()
    assert "lock shape" in lock_action.text().lower()

    lock_action.trigger()
    qtbot.wait(20)
    assert target.locked
    assert "unlock shape" in lock_action.text().lower()
    assert annotated_win._is_changed

    lock_action.trigger()
    qtbot.wait(20)
    assert not target.locked
    assert "lock shape" in lock_action.text().lower()

    annotated_win.mark_clean()
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_lock_all_and_unlock_all_shapes(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    annotated_win._actions.save_auto.setChecked(False)
    canvas = annotated_win._canvas_widgets.canvas
    assert len(canvas.shapes) == 5
    assert all(not s.locked for s in canvas.shapes)

    annotated_win._actions.lock_all_shapes.trigger()
    qtbot.wait(20)
    assert all(s.locked for s in canvas.shapes)
    assert annotated_win._is_changed

    annotated_win._actions.unlock_all_shapes.trigger()
    qtbot.wait(20)
    assert all(not s.locked for s in canvas.shapes)

    annotated_win.mark_clean()
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_locked_shape_json_roundtrip(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    item = annotated_win._docks.label_list[0]
    annotated_win._docks.label_list.select_item(item=item)
    first_shape = canvas.selected_shapes[0]
    annotated_win._actions.toggle_shape_lock.trigger()
    assert first_shape.locked

    save_path = tmp_path / "saved_annotation.json"
    annotated_win.save_labels(label_path=str(save_path))
    assert save_path.exists()

    with open(save_path) as f:
        data = json.load(f)

    # Verify locked: true persisted in the json file
    shapes_data = data["shapes"]
    assert shapes_data[0].get("locked") is True
    # Other shapes did not have locked set
    assert all(not s.get("locked") for s in shapes_data[1:])

    # Read back through _shapes_from_dicts
    loaded_annotation = read_label_file(filename=str(save_path))
    reloaded_shapes = _shapes_from_dicts(
        shape_dicts=loaded_annotation.shapes, label_flags=None
    )
    assert reloaded_shapes[0].locked
    assert all(not s.locked for s in reloaded_shapes[1:])

    annotated_win._actions.toggle_shape_lock.trigger()
    assert not first_shape.locked
    annotated_win.save_labels(label_path=str(save_path))

    with open(save_path) as f:
        data2 = json.load(f)
    assert not data2["shapes"][0].get("locked")

    annotated_win.mark_clean()
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_undo_restores_locked_state(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    item = annotated_win._docks.label_list[0]
    annotated_win._docks.label_list.select_item(item=item)
    target = canvas.selected_shapes[0]
    assert not target.locked

    annotated_win._actions.toggle_shape_lock.trigger()
    assert target.locked
    assert annotated_win._actions.undo.isEnabled()

    annotated_win.undo_shape_edit()
    qtbot.wait(20)
    # Target shape should now be unlocked
    assert not canvas.shapes[0].locked

    annotated_win.mark_clean()
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)
