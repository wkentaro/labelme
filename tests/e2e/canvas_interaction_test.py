from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Final

import numpy as np
import PIL.Image
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme import utils
from labelme._shape import Shape
from labelme.app import MainWindow
from labelme.widgets._shape_render import bounds as _shape_bounds
from labelme.widgets.canvas import Canvas
from labelme.widgets.canvas import _CanvasMode
from labelme.widgets.label_dialog import LabelDialog

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import drag_canvas
from .conftest import hover_widget_pos
from .conftest import image_to_widget_pos
from .conftest import schedule_on_dialog
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata
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
        Qt.AltModifier | Qt.ShiftModifier,
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
    original_points = [QPointF(float(p[0]), float(p[1])) for p in shape.points]

    center = _shape_bounds(shape=shape).center()
    offset = QPointF(15, 10)
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=_SHAPE_INDEX)
    _hover_and_drag(
        qtbot=qtbot,
        canvas=canvas,
        start_image_pos=center,
        end_image_pos=center + offset,
    )

    for orig, moved in zip(original_points, shape.points):
        assert float(moved[0]) != orig.x() or float(moved[1]) != orig.y()

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
    vertex_pos = QPointF(float(shape.points[0][0]), float(shape.points[0][1]))
    target_pos = vertex_pos + QPointF(10, 10)

    _hover_and_drag(
        qtbot=qtbot,
        canvas=canvas,
        start_image_pos=vertex_pos,
        end_image_pos=target_pos,
    )

    assert (
        float(shape.points[0][0]) != vertex_pos.x()
        or float(shape.points[0][1]) != vertex_pos.y()
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
    original_center = QPointF(_shape_bounds(shape=shape).center())

    qtbot.keyPress(canvas, key)
    qtbot.wait(50)
    qtbot.keyRelease(canvas, key)
    qtbot.wait(50)

    new_center = _shape_bounds(shape=shape).center()
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
    edge_mid = QPointF(
        (float(p0[0]) + float(p1[0])) / 2, (float(p0[1]) + float(p1[1])) / 2
    )
    mid_widget = image_to_widget_pos(canvas=canvas, image_pos=edge_mid)
    qtbot.mouseMove(canvas, pos=mid_widget)
    qtbot.wait(100)
    qtbot.mouseClick(canvas, Qt.LeftButton, Qt.AltModifier, pos=mid_widget)
    qtbot.wait(50)

    assert len(shape.points) == num_points_before + 1

    _save_and_check(win=annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_add_point_via_context_menu_action(
    qtbot: QtBot,
    annotated_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    shape = canvas.shapes[_SHAPE_INDEX]
    num_points_before = len(shape.points)

    assert not annotated_win._actions.add_point_to_edge.isEnabled()

    p0, p1 = shape.points[0], shape.points[1]
    midpoint = QPointF(
        (float(p0[0]) + float(p1[0])) / 2, (float(p0[1]) + float(p1[1])) / 2
    )
    qtbot.mouseMove(canvas, pos=image_to_widget_pos(canvas=canvas, image_pos=midpoint))
    qtbot.wait(100)

    assert annotated_win._actions.add_point_to_edge.isEnabled()
    annotated_win._actions.add_point_to_edge.trigger()
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

    _click_to_remove_point(
        qtbot=qtbot,
        canvas=canvas,
        vertex=QPointF(float(shape.points[0][0]), float(shape.points[0][1])),
    )

    assert len(shape.points) == original_num_points - 1

    _save_and_check(win=annotated_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_draw_actions_disable_only_active_mode(
    annotated_win: MainWindow,
    qtbot: QtBot,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas

    annotated_win._switch_canvas_mode(edit=False, create_mode="polygon")
    qtbot.wait(50)
    assert canvas.mode == _CanvasMode.CREATE

    for draw_mode, draw_action in annotated_win._actions.draw:
        if draw_mode == "polygon":
            assert not draw_action.isEnabled()
        else:
            assert draw_action.isEnabled()

    annotated_win._switch_canvas_mode(edit=True)
    qtbot.wait(50)
    assert canvas.mode == _CanvasMode.EDIT

    for _, draw_action in annotated_win._actions.draw:
        assert draw_action.isEnabled()

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

    assert canvas._current is not None

    qtbot.keyPress(canvas, Qt.Key_Escape)
    qtbot.wait(50)

    assert canvas._current is None
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

    assert canvas._current is not None
    assert len(canvas._current.points) == 3

    canvas.undo_last_point()
    qtbot.wait(50)

    assert canvas._current is not None
    assert len(canvas._current.points) == 2

    for xy in [(0.6, 0.6), (0.3, 0.6)]:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    assert len(canvas._current.points) == 4

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

    assert canvas._current is not None

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

    assert canvas._current is not None

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
    (
        "create_mode",
        "setup_click",
        "finalize_click",
        "finalize_modifier",
        "select_offset",
    ),
    [
        pytest.param(
            "rectangle",
            (0.2, 0.2),
            (0.8, 0.8),
            Qt.NoModifier,
            (0.0, 0.0),
            id="rectangle",
        ),
        pytest.param(
            "circle",
            (0.5, 0.5),
            (0.75, 0.5),
            Qt.NoModifier,
            (0.0, -20.0),
            id="circle",
        ),
        pytest.param(
            "line",
            (0.2, 0.5),
            (0.8, 0.5),
            Qt.NoModifier,
            (0.0, 0.0),
            id="line",
        ),
        pytest.param(
            "linestrip",
            (0.2, 0.5),
            (0.8, 0.5),
            Qt.ControlModifier,
            (0.0, 0.0),
            id="two-point-linestrip",
        ),
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
    finalize_modifier: Qt.KeyboardModifier,
    select_offset: tuple[float, float],
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    raw_win._switch_canvas_mode(edit=False, create_mode=create_mode)
    qtbot.wait(50)

    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=setup_click)

    label = f"test_{create_mode}"
    submit_label_dialog(qtbot=qtbot, label_dialog=raw_win._label_dialog, label=label)
    click_canvas_fraction(
        qtbot=qtbot, canvas=canvas, xy=finalize_click, modifier=finalize_modifier
    )

    shape = _wait_for_shape(qtbot=qtbot, canvas=canvas, label=label)
    assert shape.shape_type == create_mode

    raw_win._switch_canvas_mode(edit=True)
    qtbot.wait(50)

    click_pos = _shape_bounds(shape=shape).center() + QPointF(*select_offset)
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

    assert canvas._current is not None

    _cancel_label(qtbot=qtbot, label_dialog=raw_win._label_dialog)
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=(0.3, 0.3))

    def shape_reopened() -> None:
        assert len(canvas.shapes) == num_shapes_before
        assert canvas._current is not None

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

    _click_to_remove_point(
        qtbot=qtbot,
        canvas=canvas,
        vertex=QPointF(float(shape.points[0][0]), float(shape.points[0][1])),
    )

    assert len(shape.points) == expected_points

    _save_and_check(win=raw_win, tmp_path=tmp_path)
    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


def _click_to_select(qtbot: QtBot, canvas: Canvas, image_pos: QPointF) -> None:
    pos = image_to_widget_pos(canvas=canvas, image_pos=image_pos)
    hover_widget_pos(qtbot=qtbot, canvas=canvas, pos=pos)
    qtbot.mouseClick(canvas, Qt.LeftButton, pos=pos)
    qtbot.wait(50)


@pytest.mark.gui
def test_select_point_shape_by_click(
    qtbot: QtBot,
    raw_win: MainWindow,
    pause: bool,
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    raw_win._switch_canvas_mode(edit=False, create_mode="point")
    qtbot.wait(50)

    submit_label_dialog(qtbot=qtbot, label_dialog=raw_win._label_dialog, label="pt")
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=(0.5, 0.5))

    shape = _wait_for_shape(qtbot=qtbot, canvas=canvas, label="pt")
    assert shape.shape_type == "point"

    raw_win._switch_canvas_mode(edit=True)
    qtbot.wait(50)

    _click_to_select(
        qtbot=qtbot,
        canvas=canvas,
        image_pos=QPointF(float(shape.points[0][0]), float(shape.points[0][1])),
    )

    assert shape in canvas.selected_shapes

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_right_click_on_shape_opens_context_menu(
    qtbot: QtBot,
    annotated_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    # No prior right-drag has populated `_selected_shapes_copy`, so the bare
    # right-click should open menus[0] (the no-clipboard variant). Stubbing
    # both exec_ methods catches a regression that would route to menus[1].
    menu_opened: list[int] = []
    monkeypatch.setattr(
        canvas.menus[0],
        "exec",
        lambda *args, **kwargs: menu_opened.append(0) or None,
    )
    monkeypatch.setattr(
        canvas.menus[1],
        "exec",
        lambda *args, **kwargs: menu_opened.append(1) or None,
    )

    bounds_center = _shape_bounds(shape=canvas.shapes[_SHAPE_INDEX]).center()
    pos = image_to_widget_pos(canvas=canvas, image_pos=bounds_center)
    qtbot.mouseMove(canvas, pos=pos)
    qtbot.wait(50)
    qtbot.mouseClick(canvas, Qt.RightButton, pos=pos)
    qtbot.wait(50)

    assert menu_opened == [0]

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_select_mask_shape_by_click(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    # Mask cells are indexed pixel-for-pixel from points[0]; clicking inside
    # the True region must land on a True cell to exercise the mask branch
    # of `_shape.is_hit_by_point`.
    mask_arr = np.zeros((40, 40), dtype=np.uint8)
    mask_arr[10:30, 10:30] = 1
    mask_b64 = utils.img_arr_to_b64(mask_arr)

    raw_image_path = data_path / "raw/2011_000003.jpg"
    img_b64 = base64.b64encode(raw_image_path.read_bytes()).decode("utf-8")
    image_width, image_height = PIL.Image.open(raw_image_path).size

    fixture_json = tmp_path / "mask_fixture.json"
    fixture_json.write_text(
        json.dumps(
            {
                "version": "6.0.0",
                "flags": {},
                "shapes": [
                    {
                        "label": "mask_shape",
                        "points": [[100.0, 100.0], [139.0, 139.0]],
                        "group_id": None,
                        "description": "",
                        "shape_type": "mask",
                        "flags": {},
                        "mask": mask_b64,
                    }
                ],
                "imagePath": raw_image_path.name,
                "imageData": img_b64,
                "imageHeight": image_height,
                "imageWidth": image_width,
            }
        )
    )

    win = main_win(
        file_or_dir=str(fixture_json),
        config_overrides={"with_image_data": True},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas

    qtbot.waitUntil(lambda: any(s.label == "mask_shape" for s in canvas.shapes))
    shape = next(s for s in canvas.shapes if s.label == "mask_shape")

    # True region in image coords: rows/cols 110..129 (mask[10:30,10:30] +
    # origin (100,100)). Click well inside that block.
    _click_to_select(qtbot=qtbot, canvas=canvas, image_pos=QPointF(120.0, 120.0))

    assert shape in canvas.selected_shapes

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
