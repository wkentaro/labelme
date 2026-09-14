from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import draw_and_commit_polygon
from .conftest import draw_triangle
from .conftest import schedule_on_dialog
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_undo_creation_keeps_earlier_group_id_and_description(
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
    label_dialog = win._label_dialog
    num_shapes = len(canvas.shapes)

    def fill_dialog() -> None:
        qtbot.keyClicks(label_dialog.edit, "cat")
        qtbot.keyClicks(label_dialog.edit_group_id, "7")
        qtbot.keyClicks(label_dialog.edit_description, "first")
        qtbot.keyClick(label_dialog.edit_group_id, Qt.Key.Key_Enter)

    draw_triangle(qtbot=qtbot, win=win, vertices=((0.6, 0.6), (0.8, 0.6), (0.8, 0.8)))
    schedule_on_dialog(label_dialog=label_dialog, action=fill_dialog)
    qtbot.keyPress(canvas, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: len(canvas.shapes) == num_shapes + 1, timeout=5000)
    assert canvas.shapes[-1].group_id == 7
    assert canvas.shapes[-1].description == "first"

    draw_and_commit_polygon(
        qtbot=qtbot, win=win, label="cat", vertices=((0.7, 0.7), (0.9, 0.7), (0.9, 0.9))
    )
    assert len(canvas.shapes) == num_shapes + 2

    # Undo must remove only the second shape; the first keeps its metadata.
    win.undo_shape_edit()
    qtbot.wait(50)
    assert len(canvas.shapes) == num_shapes + 1
    assert canvas.shapes[-1].group_id == 7
    assert canvas.shapes[-1].description == "first"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
