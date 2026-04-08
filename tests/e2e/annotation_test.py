from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from pytestqt.qtbot import QtBot

import labelme.app

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
@pytest.mark.parametrize(
    "create_mode, setup_clicks, finalize_click, expected_num_points",
    [
        pytest.param(
            "polygon",
            [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)],
            (0.25, 0.25),
            4,
            id="polygon",
        ),
        pytest.param("rectangle", [(0.25, 0.25)], (0.75, 0.75), 2, id="rectangle"),
        pytest.param("circle", [(0.5, 0.5)], (0.75, 0.5), 2, id="circle"),
        pytest.param("line", [(0.25, 0.25)], (0.75, 0.75), 2, id="line"),
        pytest.param("point", [], (0.5, 0.5), 1, id="point"),
        pytest.param(
            "linestrip",
            [(0.25, 0.25), (0.5, 0.5)],
            (0.75, 0.75),
            3,
            id="linestrip",
        ),
    ],
)
def test_annotate_shape_types(
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
    create_mode: str,
    setup_clicks: list[tuple[float, float]],
    finalize_click: tuple[float, float],
    expected_num_points: int,
) -> None:
    input_file = str(data_path / "raw/2011_000003.jpg")
    out_file = str(tmp_path / "2011_000003.json")

    win = labelme.app.MainWindow(
        file_or_dir=input_file,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )
    qtbot.addWidget(win)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    label = "test_shape"
    canvas = win._canvas_widgets.canvas
    canvas_size = canvas.size()

    def to_pos(xy: tuple[float, float]) -> QPoint:
        return QPoint(
            int(canvas_size.width() * xy[0]),
            int(canvas_size.height() * xy[1]),
        )

    win._switch_canvas_mode(edit=False, createMode=create_mode)
    qtbot.wait(50)

    def click(
        xy: tuple[float, float], modifier: Qt.KeyboardModifier = Qt.NoModifier
    ) -> None:
        pos = to_pos(xy)
        qtbot.mouseMove(canvas, pos=pos)
        qtbot.wait(50)
        qtbot.mouseClick(canvas, Qt.LeftButton, modifier=modifier, pos=pos)
        qtbot.wait(50)

    for xy in setup_clicks:
        click(xy=xy)

    def enter_label() -> None:
        qtbot.keyClicks(win._label_dialog.edit, label)
        qtbot.wait(50)
        qtbot.keyClick(win._label_dialog.edit, Qt.Key_Enter)
        qtbot.wait(50)

    QTimer.singleShot(100, enter_label)

    # linestrip requires Ctrl+Click to finalize; all others finalize automatically
    finalize_modifier = (
        Qt.ControlModifier if create_mode == "linestrip" else Qt.NoModifier
    )
    click(xy=finalize_click, modifier=finalize_modifier)

    assert len(canvas.shapes) == 1
    shape = canvas.shapes[0]
    assert len(shape.points) == expected_num_points
    assert shape.label == label
    assert shape.shape_type == create_mode
    assert shape.group_id is None
    assert shape.mask is None
    assert shape.flags == {}

    win._save_label_file()
    assert_labelfile_sanity(out_file)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
