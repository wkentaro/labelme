from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets._shape_render import bounds as _shape_bounds

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata

_TEST_FILE_NAME: Final[str] = "annotated/2011_000003.json"


@pytest.fixture()
def _auto_save_win(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> MainWindow:
    win = main_win(
        file_or_dir=str(data_path / _TEST_FILE_NAME),
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win


@pytest.mark.gui
def test_auto_save_on_shape_move(
    qtbot: QtBot,
    _auto_save_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    label_file = tmp_path / Path(_TEST_FILE_NAME).name
    assert not label_file.exists()

    canvas = _auto_save_win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    original_center = QPointF(_shape_bounds(shape=canvas.selected_shapes[0]).center())

    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.wait(50)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)
    qtbot.wait(50)

    new_center = _shape_bounds(shape=canvas.selected_shapes[0]).center()
    assert abs((new_center.x() - original_center.x()) - 5.0) < 1.0

    assert label_file.exists()
    assert_labelfile_sanity(str(label_file))

    close_or_pause(qtbot=qtbot, widget=_auto_save_win, pause=pause)


@pytest.mark.gui
def test_auto_save_on_undo(
    qtbot: QtBot,
    _auto_save_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    label_file = tmp_path / Path(_TEST_FILE_NAME).name

    canvas = _auto_save_win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    original_shape = canvas.selected_shapes[0]
    original_center = QPointF(_shape_bounds(shape=original_shape).center())
    original_points = [(float(x), float(y)) for x, y in original_shape.points]

    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.wait(50)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)
    qtbot.wait(50)
    assert label_file.exists()

    _auto_save_win.undo_shape_edit()
    qtbot.wait(50)

    restored_center = _shape_bounds(shape=canvas.shapes[0]).center()
    assert abs(restored_center.x() - original_center.x()) < 1.0

    with open(label_file) as f:
        saved_xs = [x for x, _ in json.load(f)["shapes"][0]["points"]]
    assert abs(min(saved_xs) - min(x for x, _ in original_points)) < 1.0

    assert_labelfile_sanity(str(label_file))

    close_or_pause(qtbot=qtbot, widget=_auto_save_win, pause=pause)
