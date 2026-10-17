from __future__ import annotations

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets._canvas import Canvas

from ..conftest import close_or_pause
from .conftest import click_canvas_fraction
from .conftest import submit_label_dialog


@pytest.mark.gui
def test_circle_3p_action_and_mode_switch(
    *, qtbot: QtBot, raw_win: MainWindow, pause: bool
) -> None:
    action = raw_win._actions.create_circle_3p_mode
    assert action is not None
    assert action.isEnabled()

    action.trigger()
    assert raw_win._canvas_widgets.canvas.create_mode == "circle_3p"
    assert raw_win._canvas_widgets.canvas.mode.name == "CREATE"

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_draw_circle_3p_end_to_end(
    *, qtbot: QtBot, raw_win: MainWindow, pause: bool
) -> None:
    canvas: Canvas = raw_win._canvas_widgets.canvas
    raw_win._actions.create_circle_3p_mode.trigger()
    qtbot.wait(50)

    label = "apple"
    submit_label_dialog(qtbot=qtbot, label_dialog=raw_win._label_dialog, label=label)

    clicks = ((0.3, 0.4), (0.5, 0.2), (0.7, 0.4))
    for xy in clicks:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    qtbot.waitUntil(lambda: any(s.label == label for s in canvas.shapes))
    assert len(canvas.shapes) == 1
    shape = canvas.shapes[0]
    assert shape.shape_type == "circle"
    assert shape.label == label
    assert len(shape.points) == 2
    radius = float(np.linalg.norm(shape.points[1] - shape.points[0]))
    assert radius > 0

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)
