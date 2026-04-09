from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from PyQt5.QtCore import QPointF
from PyQt5.QtCore import Qt
from pytestqt.qtbot import QtBot

import labelme.app

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata

_TEST_FILE_NAME: Final[str] = "annotated/2011_000003.json"


@pytest.fixture()
def _auto_save_win(
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> labelme.app.MainWindow:
    win = labelme.app.MainWindow(
        file_or_dir=str(data_path / _TEST_FILE_NAME),
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )
    qtbot.addWidget(win)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win


@pytest.mark.gui
def test_auto_save_on_shape_move(
    qtbot: QtBot,
    _auto_save_win: labelme.app.MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    label_file = tmp_path / Path(_TEST_FILE_NAME).name
    assert not label_file.exists()

    canvas = _auto_save_win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    original_center = QPointF(canvas.selectedShapes[0].boundingRect().center())

    qtbot.keyPress(canvas, Qt.Key_Right)
    qtbot.wait(50)
    qtbot.keyRelease(canvas, Qt.Key_Right)
    qtbot.wait(50)

    new_center = canvas.selectedShapes[0].boundingRect().center()
    assert abs((new_center.x() - original_center.x()) - 5.0) < 1.0

    assert label_file.exists()
    assert_labelfile_sanity(str(label_file))

    close_or_pause(qtbot=qtbot, widget=_auto_save_win, pause=pause)
