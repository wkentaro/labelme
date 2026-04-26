from __future__ import annotations

import pytest
from PyQt5.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow

from ..conftest import close_or_pause


@pytest.mark.gui
def test_toggle_all_shapes(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    label_list = annotated_win._docks.label_list

    assert len(canvas.shapes) == 5
    for shape in canvas.shapes:
        assert canvas.is_shape_visible(shape)

    annotated_win.toggle_shape_visibility(False)
    qtbot.wait(50)

    for item in label_list:
        assert item.checkState() == Qt.Unchecked
    for shape in canvas.shapes:
        assert not canvas.is_shape_visible(shape)

    annotated_win.toggle_shape_visibility(True)
    qtbot.wait(50)

    for item in label_list:
        assert item.checkState() == Qt.Checked
    for shape in canvas.shapes:
        assert canvas.is_shape_visible(shape)

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_toggle_individual_shape(
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
    assert canvas.is_shape_visible(first_shape)

    first_item.setCheckState(Qt.Unchecked)
    qtbot.wait(50)
    assert not canvas.is_shape_visible(first_shape)

    first_item.setCheckState(Qt.Checked)
    qtbot.wait(50)
    assert canvas.is_shape_visible(first_shape)

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)
