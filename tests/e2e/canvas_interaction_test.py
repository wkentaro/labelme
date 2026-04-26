from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from PyQt5.QtCore import QPointF
from PyQt5.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow
from labelme.shape import Shape
from labelme.widgets.canvas import Canvas
from labelme.widgets.label_dialog import LabelDialog

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import click_canvas_fraction
from .conftest import drag_canvas
from .conftest import image_to_widget_pos
from .conftest import schedule_on_dialog
from .conftest import select_shape
from .conftest import submit_label_dialog

_TEST_FILE_NAME: Final[str] = "annotated/2011_000003.json"
_SHAPE_INDEX: Final[int] = 0


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
    drag_canvas(qtbot=qtbot, canvas=canvas, button=Qt.LeftButton, start=start, end=end)


def _cancel_label(
    qtbot: QtBot,
    label_dialog: LabelDialog,
) -> None:
    schedule_on_dialog(
        label_dialog=label_dialog,
        action=lambda: qtbot.keyClick(label_dialog, Qt.Key_Escape),
    )


def _wait_for_shape(qtbot: QtBot, canvas: Canvas, label: str) -> Shape:
    result: list[Shape] = []

    def created() -> None:
        for s in canvas.shapes:
            if s.label == label:
                result.append(s)
                return
        raise AssertionError

    qtbot.waitUntil(created)
    return result[0]


def _click_to_remove_point(
    qtbot: QtBot,
    canvas: Canvas,
    vertex: QPointF,
) -> None:
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


def _save_and_check(
    win: MainWindow,
    tmp_path: Path,
) -> None:
    label_path = str(tmp_path / Path(_TEST_FILE_NAME).name)
    win.save_labels(label_path=label_path)
    assert_labelfile_sanity(label_path)


@pytest.mark.gui
def test_move_shape_by_drag(
    qtbot: QtBot,
    annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    shape = canvas.shapes[_SHAPE_INDEX]
    original_points = [QPointF(p) for p in shape.points]

    center = shape.bounding_rect().center()
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

    _save_and_check(win=annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_move_vertex_by_drag(
    qtbot: QtBot,
    annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
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

    _save_and_check(win=annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


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
    annotated_win: MainWindow,
    pause: bool,
    key: int,
    expected_dx: float,
    expected_dy: float,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=_SHAPE_INDEX)
    shape = canvas.selected_shapes[0]
    original_center = QPointF(shape.bounding_rect().center())

    qtbot.keyPress(canvas, key)
    qtbot.wait(50)
    qtbot.keyRelease(canvas, key)
    qtbot.wait(50)

    new_center = shape.bounding_rect().center()
    assert abs((new_center.x() - original_center.x()) - expected_dx) < 1.0
    assert abs((new_center.y() - original_center.y()) - expected_dy) < 1.0

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_select_all_shapes_from_canvas(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    assert len(canvas.shapes) > 1
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=_SHAPE_INDEX)
    assert len(canvas.selected_shapes) == 1

    qtbot.keyClick(canvas, Qt.Key_A, modifier=Qt.ControlModifier)
    qtbot.wait(50)

    assert set(map(id, canvas.selected_shapes)) == set(map(id, canvas.shapes))
    assert len(annotated_win._docks.label_list.selected_items()) == len(canvas.shapes)

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_add_point_on_edge(
    qtbot: QtBot,
    annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    annotated_win._switch_canvas_mode(edit=False, create_mode="polygon")
    qtbot.wait(50)

    # Large polygon so edge midpoints are far from vertices at any canvas scale
    label = "big_rect"
    corners = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    for xy in corners:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    submit_label_dialog(
        qtbot=qtbot, label_dialog=annotated_win._label_dialog, label=label
    )
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=corners[0])

    def _shape_labeled() -> None:
        assert any(s.label == label for s in canvas.shapes)

    qtbot.waitUntil(_shape_labeled)

    shape = next(s for s in canvas.shapes if s.label == label)
    num_points_before = len(shape.points)

    annotated_win._switch_canvas_mode(edit=True)
    qtbot.wait(50)

    p0, p1 = shape.points[0], shape.points[1]
    edge_mid = QPointF((p0.x() + p1.x()) / 2, (p0.y() + p1.y()) / 2)
    mid_widget = image_to_widget_pos(canvas=canvas, image_pos=edge_mid)
    qtbot.mouseMove(canvas, pos=mid_widget)
    qtbot.wait(100)
    qtbot.mouseClick(canvas, Qt.LeftButton, modifier=Qt.AltModifier, pos=mid_widget)
    qtbot.wait(50)

    assert len(shape.points) == num_points_before + 1

    _save_and_check(win=annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_remove_point_from_shape(
    qtbot: QtBot,
    annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    shape = canvas.shapes[_SHAPE_INDEX]
    original_num_points = len(shape.points)

    _click_to_remove_point(qtbot=qtbot, canvas=canvas, vertex=shape.points[0])

    assert len(shape.points) == original_num_points - 1

    _save_and_check(win=annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_cancel_drawing_with_escape(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    annotated_win._switch_canvas_mode(edit=False, create_mode="polygon")
    qtbot.wait(50)

    for xy in [(0.3, 0.3), (0.6, 0.3)]:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert canvas.current is not None

    qtbot.keyPress(canvas, Qt.Key_Escape)
    qtbot.wait(50)

    assert canvas.current is None
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_undo_last_point_while_drawing(
    qtbot: QtBot,
    annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    num_shapes_before = len(canvas.shapes)
    annotated_win._switch_canvas_mode(edit=False, create_mode="polygon")
    qtbot.wait(50)

    for xy in [(0.3, 0.3), (0.6, 0.3), (0.6, 0.6)]:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert canvas.current is not None
    assert len(canvas.current.points) == 3

    canvas.undo_last_point()
    qtbot.wait(50)

    assert canvas.current is not None
    assert len(canvas.current.points) == 2

    for xy in [(0.6, 0.6), (0.3, 0.6)]:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert len(canvas.current.points) == 4

    label = "undo_polygon"
    submit_label_dialog(
        qtbot=qtbot, label_dialog=annotated_win._label_dialog, label=label
    )

    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=(0.3, 0.3))

    def _shape_labeled() -> None:
        assert any(s.label == label for s in canvas.shapes)

    qtbot.waitUntil(_shape_labeled)

    assert len(canvas.shapes) == num_shapes_before + 1
    assert canvas.shapes[-1].label == label

    _save_and_check(win=annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_finalize_polygon_with_enter(
    qtbot: QtBot,
    annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    num_shapes_before = len(canvas.shapes)
    annotated_win._switch_canvas_mode(edit=False, create_mode="polygon")
    qtbot.wait(50)

    for xy in [(0.3, 0.3), (0.6, 0.3), (0.6, 0.6)]:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert canvas.current is not None

    label = "enter_shape"
    submit_label_dialog(
        qtbot=qtbot, label_dialog=annotated_win._label_dialog, label=label
    )

    qtbot.keyPress(canvas, Qt.Key_Return)
    qtbot.wait(200)

    assert len(canvas.shapes) == num_shapes_before + 1
    assert canvas.shapes[-1].label == label

    _save_and_check(win=annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_undo_shape_creation(
    qtbot: QtBot,
    annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    num_shapes_before = len(canvas.shapes)
    annotated_win._switch_canvas_mode(edit=False, create_mode="polygon")
    qtbot.wait(50)

    for xy in [(0.3, 0.3), (0.6, 0.3), (0.6, 0.6)]:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert canvas.current is not None

    label = "undo_target"
    submit_label_dialog(
        qtbot=qtbot, label_dialog=annotated_win._label_dialog, label=label
    )

    qtbot.keyPress(canvas, Qt.Key_Return)
    qtbot.wait(200)

    assert len(canvas.shapes) == num_shapes_before + 1
    assert canvas.shapes[-1].label == label

    annotated_win.undo_shape_edit()
    qtbot.wait(100)

    assert len(canvas.shapes) == num_shapes_before

    _save_and_check(win=annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize(
    ("create_mode", "setup_click", "finalize_click", "select_offset"),
    [
        pytest.param("rectangle", (0.2, 0.2), (0.8, 0.8), (0.0, 0.0), id="rectangle"),
        pytest.param("circle", (0.5, 0.5), (0.75, 0.5), (0.0, -20.0), id="circle"),
    ],
)
def test_select_nonpolygon_shape(
    qtbot: QtBot,
    raw_win: MainWindow,
    tmp_path: Path,
    pause: bool,
    create_mode: str,
    setup_click: tuple[float, float],
    finalize_click: tuple[float, float],
    select_offset: tuple[float, float],
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    raw_win._switch_canvas_mode(edit=False, create_mode=create_mode)
    qtbot.wait(50)

    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=setup_click)

    label = f"test_{create_mode}"
    submit_label_dialog(qtbot=qtbot, label_dialog=raw_win._label_dialog, label=label)
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=finalize_click)

    shape = _wait_for_shape(qtbot=qtbot, canvas=canvas, label=label)
    assert shape.shape_type == create_mode

    raw_win._switch_canvas_mode(edit=True)
    qtbot.wait(50)

    click_pos = shape.bounding_rect().center() + QPointF(*select_offset)
    click_widget = image_to_widget_pos(canvas=canvas, image_pos=click_pos)
    qtbot.mouseMove(canvas, pos=click_widget)
    qtbot.wait(50)
    qtbot.mouseClick(canvas, Qt.LeftButton, pos=click_widget)
    qtbot.wait(50)

    assert shape in canvas.selected_shapes

    _save_and_check(win=raw_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_cancel_label_reopens_shape(
    qtbot: QtBot,
    raw_win: MainWindow,
    pause: bool,
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    num_shapes_before = len(canvas.shapes)
    raw_win._switch_canvas_mode(edit=False, create_mode="polygon")
    qtbot.wait(50)

    for xy in [(0.3, 0.3), (0.6, 0.3), (0.6, 0.6)]:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert canvas.current is not None

    _cancel_label(qtbot=qtbot, label_dialog=raw_win._label_dialog)
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=(0.3, 0.3))

    def shape_reopened() -> None:
        assert len(canvas.shapes) == num_shapes_before
        assert canvas.current is not None

    qtbot.waitUntil(shape_reopened)

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize(
    (
        "create_mode",
        "setup_clicks",
        "finalize_click",
        "finalize_modifier",
        "expected_points",
    ),
    [
        pytest.param(
            "polygon",
            [(0.2, 0.2), (0.8, 0.2), (0.5, 0.8)],
            (0.2, 0.2),
            Qt.NoModifier,
            3,
            id="triangle",
        ),
        pytest.param(
            "linestrip",
            [(0.3, 0.3)],
            (0.7, 0.7),
            Qt.ControlModifier,
            2,
            id="two-point-linestrip",
        ),
    ],
)
def test_remove_point_blocked_at_minimum(
    qtbot: QtBot,
    raw_win: MainWindow,
    tmp_path: Path,
    pause: bool,
    create_mode: str,
    setup_clicks: list[tuple[float, float]],
    finalize_click: tuple[float, float],
    finalize_modifier: Qt.KeyboardModifier,
    expected_points: int,
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    raw_win._switch_canvas_mode(edit=False, create_mode=create_mode)
    qtbot.wait(50)

    for xy in setup_clicks:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    label = f"min_{create_mode}"
    submit_label_dialog(qtbot=qtbot, label_dialog=raw_win._label_dialog, label=label)
    click_canvas_fraction(
        qtbot=qtbot, canvas=canvas, xy=finalize_click, modifier=finalize_modifier
    )

    shape = _wait_for_shape(qtbot=qtbot, canvas=canvas, label=label)
    assert len(shape.points) == expected_points

    raw_win._switch_canvas_mode(edit=True)
    qtbot.wait(50)

    _click_to_remove_point(qtbot=qtbot, canvas=canvas, vertex=shape.points[0])

    assert len(shape.points) == expected_points

    _save_and_check(win=raw_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)
