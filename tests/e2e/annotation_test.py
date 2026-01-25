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

from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_MainWindow_annotate_jpg(
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> None:
    input_file: str = str(data_path / "raw/2011_000003.jpg")
    out_file: str = str(tmp_path / "2011_000003.json")

    win: labelme.app.MainWindow = labelme.app.MainWindow(
        filename=input_file,
        output_file=out_file,
    )
    qtbot.addWidget(win)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    label: str = "whole"
    canvas_size: QSize = win.canvas.size()
    points: list[tuple[float, float]] = [
        (canvas_size.width() * 0.25, canvas_size.height() * 0.25),
        (canvas_size.width() * 0.75, canvas_size.height() * 0.25),
        (canvas_size.width() * 0.75, canvas_size.height() * 0.75),
        (canvas_size.width() * 0.25, canvas_size.height() * 0.75),
    ]
    win._switch_canvas_mode(edit=False, createMode="polygon")
    qtbot.wait(100)

    def click(xy: tuple[float, float]) -> None:
        qtbot.mouseMove(win.canvas, pos=QPoint(int(xy[0]), int(xy[1])))
        qtbot.wait(100)
        qtbot.mousePress(win.canvas, Qt.LeftButton, pos=QPoint(int(xy[0]), int(xy[1])))
        qtbot.wait(100)

    for xy in points:
        click(xy=xy)

    def interact() -> None:
        qtbot.keyClicks(win.labelDialog.edit, label)
        qtbot.wait(100)
        qtbot.keyClick(win.labelDialog.edit, Qt.Key_Enter)
        qtbot.wait(100)

    QTimer.singleShot(300, interact)

    click(xy=points[0])

    assert len(win.canvas.shapes) == 1
    assert len(win.canvas.shapes[0].points) == 4
    assert win.canvas.shapes[0].label == "whole"
    assert win.canvas.shapes[0].shape_type == "polygon"
    assert win.canvas.shapes[0].group_id is None
    assert win.canvas.shapes[0].mask is None
    assert win.canvas.shapes[0].flags == {}

    win.saveFile()

    labelme.testing.assert_labelfile_sanity(out_file)

    win.close()
