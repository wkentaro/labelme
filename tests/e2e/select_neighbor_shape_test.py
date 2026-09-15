from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import select_shape

# 2011_000003.json lays its shapes out roughly as
#
#     amber_kite      blue_block
#     green_hexagon   red_triangle   purple_diamond
#
# with purple_diamond sitting a few pixels higher than red_triangle.
_RED_TRIANGLE: Final = 3


def _selected_labels(*, win: MainWindow) -> list[str]:
    return [str(shape.label) for shape in win._canvas_widgets.canvas.selected_shapes]


@pytest.mark.gui
@pytest.mark.parametrize(
    ("key", "expected_label"),
    [
        pytest.param(Qt.Key.Key_Up, "blue_block", id="up"),
        pytest.param(Qt.Key.Key_Left, "green_hexagon", id="left"),
        pytest.param(Qt.Key.Key_Right, "purple_diamond", id="right"),
    ],
)
def test_ctrl_arrow_selects_neighbor_shape(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
    key: Qt.Key,
    expected_label: str,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=_RED_TRIANGLE)
    assert _selected_labels(win=annotated_win) == ["red_triangle"]

    qtbot.keyClick(canvas, key, modifier=Qt.KeyboardModifier.ControlModifier)
    qtbot.wait(50)

    assert _selected_labels(win=annotated_win) == [expected_label]
    (item,) = annotated_win._docks.label_list.selected_items()
    assert item.shape() is canvas.selected_shapes[0]

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_ctrl_arrow_keeps_selection_when_nothing_lies_that_way(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    # green_hexagon is below red_triangle by only a few pixels but far to the
    # left, so it is a left neighbor, not a lower one.
    canvas = annotated_win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=_RED_TRIANGLE)

    annotated_win._actions.select_neighbor_shape["down"].trigger()

    assert _selected_labels(win=annotated_win) == ["red_triangle"]

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_ctrl_arrow_starts_from_top_left_shape(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    assert not canvas.selected_shapes

    qtbot.keyClick(
        canvas, Qt.Key.Key_Down, modifier=Qt.KeyboardModifier.ControlModifier
    )
    qtbot.wait(50)

    assert _selected_labels(win=annotated_win) == ["amber_kite"]

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_ctrl_arrow_skips_hidden_shapes(
    *,
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    GREEN_HEXAGON: Final = 2
    canvas = annotated_win._canvas_widgets.canvas
    red_triangle = canvas.shapes[_RED_TRIANGLE]
    item = next(
        item for item in annotated_win._docks.label_list if item.shape() is red_triangle
    )
    item.setCheckState(Qt.CheckState.Unchecked)
    qtbot.wait(50)
    assert not red_triangle.visible

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=GREEN_HEXAGON)
    annotated_win._actions.select_neighbor_shape["right"].trigger()

    assert _selected_labels(win=annotated_win) == ["purple_diamond"]

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_select_neighbor_actions_follow_shapes(
    *, main_win: MainWinFactory, data_path: Path
) -> None:
    win = main_win(config_overrides={"auto_save": False})
    actions = win._actions.select_neighbor_shape.values()
    assert all(not action.isEnabled() for action in actions)

    assert win._load_file(
        image_or_label_path=str(data_path / "annotated/2011_000003.jpg")
    )
    assert all(action.isEnabled() for action in actions)

    assert win._load_file(image_or_label_path=str(data_path / "raw/2011_000003.jpg"))
    assert all(not action.isEnabled() for action in actions)
