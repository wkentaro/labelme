from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import draw_and_commit_polygon
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata
from .conftest import submit_label_dialog


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
    edited_flags = {"occluded": False}
    canvas = win._canvas_widgets.canvas
    label_list = win._docks.label_list
    label_dialog = win._label_dialog
    num_shapes = len(canvas.shapes)
    untouched_points = [s.points.copy() for s in canvas.shapes[1:]]

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    submit_label_dialog(qtbot=qtbot, label_dialog=label_dialog, label="person")
    label_list.item_double_clicked.emit(label_list[0])
    qtbot.waitUntil(lambda: not label_dialog.isVisible(), timeout=3000)
    assert canvas.shapes[0].label == "person"
    assert canvas.shapes[0].flags == edited_flags

    draw_and_commit_polygon(
        qtbot=qtbot, win=win, label="cat", vertices=((0.7, 0.7), (0.9, 0.7), (0.9, 0.9))
    )
    assert len(canvas.shapes) == num_shapes + 1

    # Undo must remove only the new shape; the earlier edit stays.
    win.undo_shape_edit()
    qtbot.wait(50)
    assert len(canvas.shapes) == num_shapes
    assert canvas.shapes[0].label == "person"
    assert canvas.shapes[0].flags == edited_flags
    for shape, points in zip(canvas.shapes[1:], untouched_points, strict=True):
        assert np.array_equal(shape.points, points)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
