from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets._canvas import Canvas

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import show_window_and_wait_for_imagedata
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


@pytest.mark.gui
def test_three_point_ring_boundaries_save_and_reload(
    *, main_win: MainWinFactory, qtbot: QtBot, tmp_path: Path
) -> None:
    example = Path(__file__).parents[2] / "examples" / "three_point_circle"
    win = main_win(
        file_or_dir=example / "ring.png",
        output_dir=tmp_path,
        config_overrides={"auto_save": False},
    )
    canvas = win._canvas_widgets.canvas
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    for label, radius in (("outer_boundary", 128), ("inner_boundary", 92)):
        win._actions.create_circle_3p_mode.trigger()
        submit_label_dialog(qtbot=qtbot, label_dialog=win._label_dialog, label=label)
        for xy in (
            ((160 + radius) / 320, 0.5),
            (0.5, (160 - radius) / 320),
            ((160 - radius) / 320, 0.5),
        ):
            click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)
        qtbot.waitUntil(lambda: any(shape.label == label for shape in canvas.shapes))
        shape = canvas.shapes[-1]
        assert shape.shape_type == "circle"
        np.testing.assert_allclose(shape.points[0], (160, 160), atol=2)
        assert np.linalg.norm(shape.points[1] - shape.points[0]) == pytest.approx(
            radius, abs=2
        )
    label_path = tmp_path / "ring.json"
    win.save_labels(label_path=str(label_path))
    assert win._load_file(image_or_label_path=str(label_path))
    assert [shape.label for shape in canvas.shapes] == [
        "outer_boundary",
        "inner_boundary",
    ]
    assert all(shape.shape_type == "circle" for shape in canvas.shapes)
    assert all(len(shape.points) == 2 for shape in canvas.shapes)
    win.mark_clean()
