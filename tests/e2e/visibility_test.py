from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


@pytest.fixture()
def _win(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> MainWindow:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win


@pytest.mark.gui
def test_toggle_all_shapes(
    qtbot: QtBot,
    _win: MainWindow,
    pause: bool,
) -> None:
    canvas = _win._canvas_widgets.canvas
    label_list = _win._docks.label_list

    assert len(canvas.shapes) == 5
    for shape in canvas.shapes:
        assert canvas.is_shape_visible(shape)

    _win.toggleShapes(False)
    qtbot.wait(50)

    for item in label_list:
        assert item.checkState() == Qt.Unchecked
    for shape in canvas.shapes:
        assert not canvas.is_shape_visible(shape)

    _win.toggleShapes(True)
    qtbot.wait(50)

    for item in label_list:
        assert item.checkState() == Qt.Checked
    for shape in canvas.shapes:
        assert canvas.is_shape_visible(shape)

    close_or_pause(qtbot=qtbot, widget=_win, pause=pause)


@pytest.mark.gui
def test_toggle_individual_shape(
    qtbot: QtBot,
    _win: MainWindow,
    pause: bool,
) -> None:
    canvas = _win._canvas_widgets.canvas
    label_list = _win._docks.label_list

    assert len(canvas.shapes) == 5

    first_item = label_list[0]
    first_shape = first_item.shape()
    assert first_shape is not None
    assert canvas.is_shape_visible(first_shape)

    first_item.setCheckState(Qt.Unchecked)
    qtbot.wait(50)
    assert not canvas.is_shape_visible(first_shape)

    first_item.setCheckState(Qt.Checked)
    qtbot.wait(50)
    assert canvas.is_shape_visible(first_shape)

    close_or_pause(qtbot=qtbot, widget=_win, pause=pause)
