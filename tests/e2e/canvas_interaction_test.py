from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from PyQt5 import QtGui
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import QPointF
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow
from labelme.widgets.canvas import Canvas
from labelme.widgets.label_dialog import LabelDialog

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import image_to_widget_pos
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata

_TEST_FILE_NAME: Final[str] = "annotated/2011_000003.json"
_SHAPE_INDEX: Final[int] = 0


@pytest.fixture()
def _annotated_win(
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


def _hover_and_drag(
    qtbot: QtBot,
    canvas: Canvas,
    start_image_pos: QPointF,
    end_image_pos: QPointF,
) -> None:
    start = image_to_widget_pos(canvas=canvas, image_pos=start_image_pos)
    end = image_to_widget_pos(canvas=canvas, image_pos=end_image_pos)
    qtbot.mouseMove(canvas, pos=start)
    qtbot.wait(50)
    qtbot.mousePress(canvas, Qt.LeftButton, pos=start)
    qtbot.wait(50)
    # qtbot.mouseMove does not carry button state, so send a raw event
    move_event = QtGui.QMouseEvent(
        QtGui.QMouseEvent.MouseMove,
        QPointF(end),
        Qt.NoButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    QApplication.sendEvent(canvas, move_event)
    qtbot.wait(50)
    qtbot.mouseRelease(canvas, Qt.LeftButton, pos=end)
    qtbot.wait(50)


def _click_canvas_fraction(
    qtbot: QtBot,
    canvas: Canvas,
    xy: tuple[float, float],
    modifier: Qt.KeyboardModifier = Qt.NoModifier,
) -> None:
    canvas_size = canvas.size()
    pos = QPoint(
        int(canvas_size.width() * xy[0]),
        int(canvas_size.height() * xy[1]),
    )
    qtbot.mouseMove(canvas, pos=pos)
    qtbot.wait(50)
    qtbot.mouseClick(canvas, Qt.LeftButton, modifier=modifier, pos=pos)
    qtbot.wait(50)


def _enter_label(
    qtbot: QtBot,
    label_dialog: LabelDialog,
    label: str,
) -> None:
    def _poll() -> None:
        if not label_dialog.isVisible():
            QTimer.singleShot(50, _poll)
            return
        qtbot.keyClicks(label_dialog.edit, label)
        qtbot.wait(50)
        qtbot.keyClick(label_dialog.edit, Qt.Key_Enter)

    QTimer.singleShot(0, _poll)


def _save_and_check(
    win: MainWindow,
    tmp_path: Path,
) -> None:
    label_path = str(tmp_path / Path(_TEST_FILE_NAME).name)
    win.saveLabels(label_path=label_path)
    assert_labelfile_sanity(label_path)


@pytest.mark.gui
def test_move_shape_by_drag(
    qtbot: QtBot,
    _annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = _annotated_win._canvas_widgets.canvas
    shape = canvas.shapes[_SHAPE_INDEX]
    original_points = [QPointF(p) for p in shape.points]

    center = shape.boundingRect().center()
    offset = QPointF(15, 10)
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=_SHAPE_INDEX)
    _hover_and_drag(
        qtbot=qtbot,
        canvas=canvas,
        start_image_pos=center,
        end_image_pos=center + offset,
    )

    for orig, moved in zip(original_points, shape.points):
        assert moved.x() != orig.x() or moved.y() != orig.y()

    _save_and_check(win=_annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=_annotated_win, pause=pause)


@pytest.mark.gui
def test_move_vertex_by_drag(
    qtbot: QtBot,
    _annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = _annotated_win._canvas_widgets.canvas
    shape = canvas.shapes[_SHAPE_INDEX]
    vertex_pos = QPointF(shape.points[0])
    target_pos = vertex_pos + QPointF(10, 10)

    _hover_and_drag(
        qtbot=qtbot,
        canvas=canvas,
        start_image_pos=vertex_pos,
        end_image_pos=target_pos,
    )

    assert (
        shape.points[0].x() != vertex_pos.x() or shape.points[0].y() != vertex_pos.y()
    )

    _save_and_check(win=_annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=_annotated_win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize(
    ("key", "expected_dx", "expected_dy"),
    [
        pytest.param(Qt.Key_Up, 0, -5.0, id="up"),
        pytest.param(Qt.Key_Down, 0, 5.0, id="down"),
        pytest.param(Qt.Key_Left, -5.0, 0, id="left"),
        pytest.param(Qt.Key_Right, 5.0, 0, id="right"),
    ],
)
def test_move_shape_by_arrow_key(
    qtbot: QtBot,
    _annotated_win: MainWindow,
    pause: bool,
    key: int,
    expected_dx: float,
    expected_dy: float,
) -> None:
    canvas = _annotated_win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=_SHAPE_INDEX)
    shape = canvas.selectedShapes[0]
    original_center = QPointF(shape.boundingRect().center())

    qtbot.keyPress(canvas, key)
    qtbot.wait(50)
    qtbot.keyRelease(canvas, key)
    qtbot.wait(50)

    new_center = shape.boundingRect().center()
    assert abs((new_center.x() - original_center.x()) - expected_dx) < 1.0
    assert abs((new_center.y() - original_center.y()) - expected_dy) < 1.0

    close_or_pause(qtbot=qtbot, widget=_annotated_win, pause=pause)


@pytest.mark.gui
def test_add_point_on_edge(
    qtbot: QtBot,
    _annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = _annotated_win._canvas_widgets.canvas
    _annotated_win._switch_canvas_mode(edit=False, createMode="polygon")
    qtbot.wait(50)

    # Large polygon so edge midpoints are far from vertices at any canvas scale
    label = "big_rect"
    corners = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    for xy in corners:
        _click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    _enter_label(qtbot=qtbot, label_dialog=_annotated_win._label_dialog, label=label)
    _click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=corners[0])

    def _shape_labeled() -> None:
        assert any(s.label == label for s in canvas.shapes)

    qtbot.waitUntil(_shape_labeled)

    shape = next(s for s in canvas.shapes if s.label == label)
    num_points_before = len(shape.points)

    _annotated_win._switch_canvas_mode(edit=True)
    qtbot.wait(50)

    p0, p1 = shape.points[0], shape.points[1]
    edge_mid = QPointF((p0.x() + p1.x()) / 2, (p0.y() + p1.y()) / 2)
    mid_widget = image_to_widget_pos(canvas=canvas, image_pos=edge_mid)
    qtbot.mouseMove(canvas, pos=mid_widget)
    qtbot.wait(100)
    qtbot.mouseClick(canvas, Qt.LeftButton, modifier=Qt.AltModifier, pos=mid_widget)
    qtbot.wait(50)

    assert len(shape.points) == num_points_before + 1

    _save_and_check(win=_annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=_annotated_win, pause=pause)


@pytest.mark.gui
def test_remove_point_from_shape(
    qtbot: QtBot,
    _annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = _annotated_win._canvas_widgets.canvas
    shape = canvas.shapes[_SHAPE_INDEX]
    original_num_points = len(shape.points)

    vertex = shape.points[0]
    vtx_widget = image_to_widget_pos(canvas=canvas, image_pos=vertex)
    qtbot.mouseMove(canvas, pos=vtx_widget)
    qtbot.wait(100)
    qtbot.mouseClick(
        canvas,
        Qt.LeftButton,
        modifier=Qt.AltModifier | Qt.ShiftModifier,
        pos=vtx_widget,
    )
    qtbot.wait(50)

    assert len(shape.points) == original_num_points - 1

    _save_and_check(win=_annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=_annotated_win, pause=pause)


@pytest.mark.gui
def test_cancel_drawing_with_escape(
    qtbot: QtBot,
    _annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = _annotated_win._canvas_widgets.canvas
    _annotated_win._switch_canvas_mode(edit=False, createMode="polygon")
    qtbot.wait(50)

    for xy in [(0.3, 0.3), (0.6, 0.3)]:
        _click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert canvas.current is not None

    qtbot.keyPress(canvas, Qt.Key_Escape)
    qtbot.wait(50)

    assert canvas.current is None
    close_or_pause(qtbot=qtbot, widget=_annotated_win, pause=pause)


@pytest.mark.gui
def test_undo_last_point_while_drawing(
    qtbot: QtBot,
    _annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = _annotated_win._canvas_widgets.canvas
    num_shapes_before = len(canvas.shapes)
    _annotated_win._switch_canvas_mode(edit=False, createMode="polygon")
    qtbot.wait(50)

    for xy in [(0.3, 0.3), (0.6, 0.3), (0.6, 0.6)]:
        _click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert canvas.current is not None
    assert len(canvas.current.points) == 3

    canvas.undoLastPoint()
    qtbot.wait(50)

    assert canvas.current is not None
    assert len(canvas.current.points) == 2

    for xy in [(0.6, 0.6), (0.3, 0.6)]:
        _click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert len(canvas.current.points) == 4

    label = "undo_polygon"
    _enter_label(qtbot=qtbot, label_dialog=_annotated_win._label_dialog, label=label)

    _click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=(0.3, 0.3))

    def _shape_labeled() -> None:
        assert any(s.label == label for s in canvas.shapes)

    qtbot.waitUntil(_shape_labeled)

    assert len(canvas.shapes) == num_shapes_before + 1
    assert canvas.shapes[-1].label == label

    _save_and_check(win=_annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=_annotated_win, pause=pause)


@pytest.mark.gui
def test_finalize_polygon_with_enter(
    qtbot: QtBot,
    _annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = _annotated_win._canvas_widgets.canvas
    num_shapes_before = len(canvas.shapes)
    _annotated_win._switch_canvas_mode(edit=False, createMode="polygon")
    qtbot.wait(50)

    for xy in [(0.3, 0.3), (0.6, 0.3), (0.6, 0.6)]:
        _click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert canvas.current is not None

    label = "enter_shape"
    _enter_label(qtbot=qtbot, label_dialog=_annotated_win._label_dialog, label=label)

    qtbot.keyPress(canvas, Qt.Key_Return)
    qtbot.wait(200)

    assert len(canvas.shapes) == num_shapes_before + 1
    assert canvas.shapes[-1].label == label

    _save_and_check(win=_annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=_annotated_win, pause=pause)


@pytest.mark.gui
def test_undo_shape_creation(
    qtbot: QtBot,
    _annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = _annotated_win._canvas_widgets.canvas
    num_shapes_before = len(canvas.shapes)
    _annotated_win._switch_canvas_mode(edit=False, createMode="polygon")
    qtbot.wait(50)

    for xy in [(0.3, 0.3), (0.6, 0.3), (0.6, 0.6)]:
        _click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert canvas.current is not None

    label = "undo_target"
    _enter_label(qtbot=qtbot, label_dialog=_annotated_win._label_dialog, label=label)

    qtbot.keyPress(canvas, Qt.Key_Return)
    qtbot.wait(200)

    assert len(canvas.shapes) == num_shapes_before + 1
    assert canvas.shapes[-1].label == label

    _annotated_win.undoShapeEdit()
    qtbot.wait(100)

    assert len(canvas.shapes) == num_shapes_before

    _save_and_check(win=_annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=_annotated_win, pause=pause)
