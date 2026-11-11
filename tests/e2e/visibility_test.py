from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


def test_toggle_all_shapes(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    label_list = annotated_win._docks.label_list

    assert len(canvas.shapes) == 5
    for shape in canvas.shapes:
        assert shape.visible

    annotated_win.toggle_shape_visibility(value=False)
    qtbot.wait(50)

    for item in label_list:
        assert item.checkState() == Qt.CheckState.Unchecked
    for shape in canvas.shapes:
        assert not shape.visible

    annotated_win.toggle_shape_visibility(value=True)
    qtbot.wait(50)

    for item in label_list:
        assert item.checkState() == Qt.CheckState.Checked
    for shape in canvas.shapes:
        assert shape.visible

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


def test_toggle_all_shapes_flips_a_selected_group_once(
    *, annotated_win: MainWindow
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    label_list = annotated_win._docks.label_list
    for i in (0, 1):
        label_list.select_item(item=label_list[i])
    n_backups = len(canvas.shape_backups)
    repainted_rows: list[int] = []
    label_list._model.dataChanged.connect(
        lambda top_left, *_: repainted_rows.append(top_left.row())
    )

    annotated_win.toggle_shape_visibility(value=None)

    assert not any(shape.visible for shape in canvas.shapes)
    assert all(item.checkState() == Qt.CheckState.Unchecked for item in label_list)
    # One Undo step for the whole action, not one per Shape.
    assert len(canvas.shape_backups) == n_backups + 1
    # The view repaints a checkbox only when the model reports the change.
    assert sorted(repainted_rows) == list(range(len(label_list)))


def test_toggle_individual_shape(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    label_list = annotated_win._docks.label_list

    assert len(canvas.shapes) == 5

    first_item = label_list[0]
    first_shape = first_item.shape()
    assert first_shape is not None
    assert first_shape.visible

    first_item.setCheckState(Qt.CheckState.Unchecked)
    qtbot.wait(50)
    assert not first_shape.visible

    first_item.setCheckState(Qt.CheckState.Checked)
    qtbot.wait(50)
    assert first_shape.visible

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


def test_visibility_preserved_when_undoing_unrelated_edit(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    label_list = annotated_win._docks.label_list

    assert len(canvas.shapes) == 5

    hidden_index = 1
    label_list[hidden_index].setCheckState(Qt.CheckState.Unchecked)
    qtbot.wait(50)
    assert not canvas.shapes[hidden_index].visible

    canvas.shapes[0].points[0] += [5.0, 5.0]
    canvas.backup_shapes()

    annotated_win.undo_shape_edit()
    qtbot.wait(50)

    assert len(canvas.shapes) == 5
    for i, shape in enumerate(canvas.shapes):
        expected_visible = i != hidden_index
        assert shape.visible is expected_visible
        expected_state = (
            Qt.CheckState.Checked if expected_visible else Qt.CheckState.Unchecked
        )
        assert label_list[i].checkState() == expected_state

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


def test_undo_recovers_accidental_hide(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    label_list = annotated_win._docks.label_list

    assert len(canvas.shapes) == 5
    hidden_index = 1

    label_list[hidden_index].setCheckState(Qt.CheckState.Unchecked)
    qtbot.wait(50)
    assert not canvas.shapes[hidden_index].visible
    assert annotated_win._actions.undo.isEnabled()

    annotated_win._actions.undo.trigger()
    qtbot.wait(50)

    assert len(canvas.shapes) == 5
    for i, shape in enumerate(canvas.shapes):
        assert shape.visible
        assert label_list[i].checkState() == Qt.CheckState.Checked

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


def test_undoing_a_hide_leaves_the_file_unmodified(
    *,
    qtbot: QtBot,
    main_win: MainWinFactory,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides={"auto_save": False},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    # A failure leaves unsaved changes; skip the prompt when the window closes.
    monkeypatch.setattr(win, "_can_continue", lambda: True)

    win._docks.label_list[1].setCheckState(Qt.CheckState.Unchecked)
    win._actions.undo.trigger()

    assert win._canvas_widgets.canvas.shapes[1].visible
    # Visibility is not saved, so undoing a hide changes nothing on disk.
    assert not win._is_changed
    assert not win._actions.save.isEnabled()


def test_multi_select_toggle_propagates(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    label_list = annotated_win._docks.label_list

    assert len(canvas.shapes) == 5
    selected_indices = (0, 1, 3)

    label_list.clearSelection()
    for i in selected_indices:
        label_list.select_item(item=label_list[i])
    qtbot.wait(50)
    assert {item for item in label_list.selected_items()} == {
        label_list[i] for i in selected_indices
    }

    label_list[selected_indices[1]].setCheckState(Qt.CheckState.Unchecked)
    qtbot.wait(50)

    for i in range(len(canvas.shapes)):
        if i in selected_indices:
            assert not canvas.shapes[i].visible
            assert label_list[i].checkState() == Qt.CheckState.Unchecked
        else:
            assert canvas.shapes[i].visible
            assert label_list[i].checkState() == Qt.CheckState.Checked

    annotated_win._actions.undo.trigger()
    qtbot.wait(50)

    for i in range(len(canvas.shapes)):
        assert canvas.shapes[i].visible
        assert label_list[i].checkState() == Qt.CheckState.Checked

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


def test_multi_select_preserves_selection_after_checkbox_click(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    label_list = annotated_win._docks.label_list

    assert len(canvas.shapes) == 5
    selected_indices = (0, 1, 3)

    label_list.clearSelection()
    for i in selected_indices:
        label_list.select_item(item=label_list[i])
    qtbot.wait(50)

    target_index = label_list._model.indexFromItem(label_list[selected_indices[1]])
    rect = label_list.visualRect(target_index)
    checkbox_pos = QPoint(rect.left() + 5, rect.center().y())
    qtbot.mouseClick(label_list.viewport(), Qt.MouseButton.LeftButton, pos=checkbox_pos)
    qtbot.wait(50)

    assert {item for item in label_list.selected_items()} == {
        label_list[i] for i in selected_indices
    }
    for i in selected_indices:
        assert label_list[i].checkState() == Qt.CheckState.Unchecked
        assert not canvas.shapes[i].visible

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


def test_multi_select_collapses_on_row_body_click(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    label_list = annotated_win._docks.label_list

    selected_indices = (0, 1, 3)
    clicked_index = 2

    label_list.clearSelection()
    for i in selected_indices:
        label_list.select_item(item=label_list[i])
    qtbot.wait(50)

    target_index = label_list._model.indexFromItem(label_list[clicked_index])
    rect = label_list.visualRect(target_index)
    row_body_pos = QPoint(rect.center().x(), rect.center().y())
    qtbot.mouseClick(label_list.viewport(), Qt.MouseButton.LeftButton, pos=row_body_pos)
    qtbot.wait(50)

    assert {item for item in label_list.selected_items()} == {label_list[clicked_index]}

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


def test_select_all_skips_hidden_shape(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    label_list = annotated_win._docks.label_list
    hidden_index = 1
    label_list[hidden_index].setCheckState(Qt.CheckState.Unchecked)
    qtbot.wait(50)
    assert not canvas.shapes[hidden_index].visible
    annotated_win._actions.edit_mode.trigger()

    qtbot.keyClick(canvas, Qt.Key.Key_A, modifier=Qt.KeyboardModifier.ControlModifier)
    qtbot.wait(50)

    assert len(canvas.selected_shapes) == len(canvas.shapes) - 1
    assert all(shape.visible for shape in canvas.selected_shapes)


def test_recoloring_a_mixed_selection_keeps_each_visibility(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    label_list = annotated_win._docks.label_list
    label_list[1].setCheckState(Qt.CheckState.Unchecked)
    label_list.clearSelection()
    label_list.select_item(item=label_list[0])
    label_list.select_item(item=label_list[1])
    backups = len(canvas.shape_backups)

    # Settings calls this when the shape colors change.
    annotated_win._shape_color_preview = {
        "mode": "uniform",
        "uniform": {"color": [1, 2, 3]},
    }
    annotated_win._refresh_shape_colors()

    assert [shape.visible for shape in canvas.shapes[:2]] == [True, False]
    assert len(canvas.shape_backups) == backups

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)
