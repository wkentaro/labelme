from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import draw_and_commit_polygon
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata
from .conftest import submit_label_dialog

_VERTICES = ((0.7, 0.7), (0.9, 0.7), (0.9, 0.9))


def _edit_selected_label(*, qtbot: QtBot, win: MainWindow, label: str) -> None:
    label_list = win._docks.label_list
    label_dialog = win._label_dialog
    submit_label_dialog(qtbot=qtbot, label_dialog=label_dialog, label=label)
    label_list.item_double_clicked.emit(label_list[0])
    qtbot.waitUntil(lambda: not label_dialog.isVisible(), timeout=3000)


def _save(*, win: MainWindow, label_path: Path) -> dict:
    assert win.save_labels(label_path=str(label_path))
    win.mark_clean()
    with label_path.open() as f:
        return json.load(f)


@pytest.mark.gui
def test_undo_creation_keeps_earlier_label_edit(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    # A label pattern with flags, so the edit changes flags as well as the label.
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides={"label_flags": {"person": ["occluded"]}},
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    label_path = tmp_path / "2011_000003.json"
    num_shapes = len(canvas.shapes)
    assert canvas.shapes[0].label == "amber_kite"
    untouched_points = [s.points.copy() for s in canvas.shapes[1:]]

    # Edit the label (and flags) of the first shape, then save.
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    _edit_selected_label(qtbot=qtbot, win=win, label="person")
    assert canvas.shapes[0].label == "person"
    edited_flags = dict(canvas.shapes[0].flags)
    assert "occluded" in edited_flags
    saved = _save(win=win, label_path=label_path)
    assert saved["shapes"][0]["label"] == "person"

    # Create another shape and save.
    draw_and_commit_polygon(qtbot=qtbot, win=win, label="cat", vertices=_VERTICES)
    assert len(canvas.shapes) == num_shapes + 1
    _save(win=win, label_path=label_path)

    # Undo must remove only the new shape; the saved edit stays.
    win.undo_shape_edit()
    qtbot.wait(50)
    assert len(canvas.shapes) == num_shapes
    assert canvas.shapes[0].label == "person"
    assert canvas.shapes[0].flags == edited_flags
    for shape, points in zip(canvas.shapes[1:], untouched_points, strict=True):
        assert np.array_equal(shape.points, points)

    saved = _save(win=win, label_path=label_path)
    assert [s["label"] for s in saved["shapes"]][0] == "person"
    assert saved["shapes"][0]["flags"] == edited_flags
    assert len(saved["shapes"]) == num_shapes

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_undo_right_after_label_edit_reverts_only_the_edit(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    num_shapes = len(canvas.shapes)

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    _edit_selected_label(qtbot=qtbot, win=win, label="person")
    assert canvas.shapes[0].label == "person"

    win.undo_shape_edit()
    qtbot.wait(50)
    assert len(canvas.shapes) == num_shapes
    assert canvas.shapes[0].label == "amber_kite"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
