from __future__ import annotations

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets._canvas import Canvas

from ..conftest import close_or_pause
from .conftest import click_canvas_fraction
from .conftest import schedule_on_dialog
from .conftest import submit_label_dialog


@pytest.mark.gui
def test_circle_3p_action_and_mode_switch(
    *, qtbot: QtBot, raw_win: MainWindow, pause: bool
) -> None:
    action = dict(raw_win._actions.draw)["circle_3p"]
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
    dict(raw_win._actions.draw)["circle_3p"].trigger()
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


@pytest.mark.gui
def test_cancel_then_redraw_three_point_circle_keeps_geometry(
    *, qtbot: QtBot, raw_win: MainWindow
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    dict(raw_win._actions.draw)["circle_3p"].trigger()
    clicks = ((0.3, 0.4), (0.5, 0.2), (0.7, 0.4))
    cancelled_points: list[np.ndarray] = []

    def cancel_label() -> None:
        cancelled_points.append(canvas.shapes[-1].points.copy())
        raw_win._label_dialog.reject()

    schedule_on_dialog(label_dialog=raw_win._label_dialog, action=cancel_label)
    for xy in clicks:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)
    assert len(cancelled_points) == 1
    assert not canvas.shapes

    label = "retried_circle"
    submit_label_dialog(qtbot=qtbot, label_dialog=raw_win._label_dialog, label=label)
    for xy in clicks:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)
    qtbot.waitUntil(lambda: any(shape.label == label for shape in canvas.shapes))

    assert len(canvas.shapes) == 1
    assert canvas.shapes[0].shape_type == "circle"
    raw_win.mark_clean()
    np.testing.assert_array_equal(canvas.shapes[0].points, cancelled_points[0])
