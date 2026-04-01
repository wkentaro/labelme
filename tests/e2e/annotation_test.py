from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import QSize
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from pytestqt.qtbot import QtBot

import labelme.app
import labelme.testing

from ..conftest import close_or_pause
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_MainWindow_annotate_jpg(
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    input_file: str = str(data_path / "raw/2011_000003.jpg")
    out_file: str = str(tmp_path / "2011_000003.json")

    win: labelme.app.MainWindow = labelme.app.MainWindow(
        filename=input_file,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )
    qtbot.addWidget(win)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    label: str = "whole"
    canvas_size: QSize = win._canvas_widgets.canvas.size()
    points: list[tuple[float, float]] = [
        (canvas_size.width() * 0.25, canvas_size.height() * 0.25),
        (canvas_size.width() * 0.75, canvas_size.height() * 0.25),
        (canvas_size.width() * 0.75, canvas_size.height() * 0.75),
        (canvas_size.width() * 0.25, canvas_size.height() * 0.75),
    ]
    win._switch_canvas_mode(edit=False, createMode="polygon")
    qtbot.wait(50)

    def click(xy: tuple[float, float]) -> None:
        qtbot.mouseMove(win._canvas_widgets.canvas, pos=QPoint(int(xy[0]), int(xy[1])))
        qtbot.wait(50)
        qtbot.mouseClick(
            win._canvas_widgets.canvas,
            Qt.LeftButton,
            pos=QPoint(int(xy[0]), int(xy[1])),
        )
        qtbot.wait(50)

    for xy in points:
        click(xy=xy)

    def interact() -> None:
        qtbot.keyClicks(win._label_dialog.edit, label)
        qtbot.wait(50)
        qtbot.keyClick(win._label_dialog.edit, Qt.Key_Enter)
        qtbot.wait(50)

    QTimer.singleShot(100, interact)

    click(xy=points[0])

    assert len(win._canvas_widgets.canvas.shapes) == 1
    assert len(win._canvas_widgets.canvas.shapes[0].points) == 4
    assert win._canvas_widgets.canvas.shapes[0].label == "whole"
    assert win._canvas_widgets.canvas.shapes[0].shape_type == "polygon"
    assert win._canvas_widgets.canvas.shapes[0].group_id is None
    assert win._canvas_widgets.canvas.shapes[0].mask is None
    assert win._canvas_widgets.canvas.shapes[0].flags == {}

    win.saveFile()

    labelme.testing.assert_labelfile_sanity(out_file)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
