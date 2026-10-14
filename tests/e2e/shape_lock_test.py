from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import drag_canvas
from .conftest import hover_widget_pos
from .conftest import image_to_widget_pos
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_locked_shape_resists_edits_and_survives_reopen(
    *,
    annotated_win: MainWindow,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
) -> None:
    win = annotated_win
    canvas = win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    shape = canvas.shapes[0]
    points = shape.points.copy()

    win._actions.lock.trigger()

    assert shape.locked
    assert win._actions.lock.text() == "Unlock Shapes"
    assert not win._actions.delete.isEnabled()
    assert not win._actions.edit.isEnabled()
    label_list = win._docks.label_list
    # The lock trails the row's text, so a locked row keeps its height.
    assert label_list.sizeHintForRow(0) == label_list.sizeHintForRow(1)
    assert (
        label_list.sizeHintForIndex(label_list.model().index(0, 0)).width()
        > label_list.sizeHintForIndex(label_list.model().index(1, 0)).width()
    )

    body = image_to_widget_pos(
        canvas=canvas,
        image_pos=QPointF(float(points[:, 0].mean()), float(points[:, 1].mean())),
    )
    vertex = image_to_widget_pos(canvas=canvas, image_pos=QPointF(*points[0]))
    for start in (body, vertex):
        hover_widget_pos(qtbot=qtbot, canvas=canvas, pos=start)
        drag_canvas(
            qtbot=qtbot,
            canvas=canvas,
            button=Qt.MouseButton.LeftButton,
            start=start,
            end=start + QPoint(30, 30),
        )
    canvas.selection_changed.emit([shape])
    qtbot.keyClick(canvas, Qt.Key.Key_Right)
    win.delete_selected_shapes()
    win._edit_label()

    assert (shape.points == points).all()
    assert len(canvas.shapes) == 5

    label_path = tmp_path / "2011_000003.json"
    assert win.save_labels(label_path=str(label_path))
    win._wait_for_save()
    saved_shapes = json.loads(label_path.read_text())["shapes"]
    assert [s.get("locked") for s in saved_shapes] == [True, None, None, None, None]

    win._actions.duplicate.trigger()
    assert not canvas.shapes[-1].locked
    win.undo_shape_edit()
    win.undo_shape_edit()
    assert not canvas.shapes[0].locked

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_locked_key_is_restored_on_open(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    source = data_path / "annotated/2011_000003.json"
    annotation = json.loads(source.read_text())
    annotation["shapes"][1]["locked"] = True
    annotation["imagePath"] = str(source.with_suffix(".jpg"))
    label_path = tmp_path / source.name
    label_path.write_text(json.dumps(annotation))

    win = main_win(file_or_dir=str(label_path), config_overrides=None, output_dir=None)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    shapes = win._canvas_widgets.canvas.shapes
    assert [s.locked for s in shapes] == [False, True, False, False, False]

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_shapes_carried_to_the_next_image_are_unlocked(
    *,
    main_win: MainWinFactory,
    data_path: Path,
) -> None:
    win = main_win(
        file_or_dir=data_path / "annotated/2011_000003.jpg",
        config_overrides={"auto_save": False, "keep_prev": True},
    )
    canvas = win._canvas_widgets.canvas
    canvas.shapes[0].locked = True

    assert win._load_file(image_or_label_path=str(data_path / "raw/2011_000003.jpg"))

    assert len(canvas.shapes) == 5
    assert not any(shape.locked for shape in canvas.shapes)
    win.mark_clean()


@pytest.mark.gui
def test_lock_leaves_an_unfinished_shape_alone(
    *,
    annotated_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = annotated_win
    canvas = win._canvas_widgets.canvas
    win._switch_canvas_mode(edit=False, create_mode="polygon")
    qtbot.mouseClick(
        canvas,
        Qt.MouseButton.LeftButton,
        pos=image_to_widget_pos(canvas=canvas, image_pos=QPointF(20, 20)),
    )
    assert canvas.is_drawing
    item = win._docks.label_list.find_item_by_shape(shape=canvas.shapes[0])
    win._docks.label_list.select_item(item=item)

    win._actions.lock.trigger()

    assert canvas.is_drawing
    assert not canvas.shapes[0].locked
    win.mark_clean()


@pytest.mark.gui
def test_drag_right_after_unlock_is_recorded(
    *,
    annotated_win: MainWindow,
    qtbot: QtBot,
) -> None:
    win = annotated_win
    canvas = win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    shape = canvas.shapes[0]
    points = shape.points.copy()
    win._actions.lock.trigger()
    win._actions.lock.trigger()
    assert not shape.locked
    start = image_to_widget_pos(
        canvas=canvas,
        image_pos=QPointF(float(points[:, 0].mean()), float(points[:, 1].mean())),
    )

    # No pointer move before the press, so the canvas has no hovered shape.
    with qtbot.waitSignal(canvas.shape_moved, timeout=1000):
        drag_canvas(
            qtbot=qtbot,
            canvas=canvas,
            button=Qt.MouseButton.LeftButton,
            start=start,
            end=start + QPoint(30, 30),
        )

    assert not (shape.points == points).all()
    win.undo_shape_edit()
    assert (canvas.shapes[0].points == points).all()
    win.mark_clean()
