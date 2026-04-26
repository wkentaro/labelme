from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from PyQt5.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow
from labelme.widgets.canvas import Canvas

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata
from .conftest import submit_label_dialog


def _draw_polygon(
    qtbot: QtBot,
    win: MainWindow,
    canvas: Canvas,
    label: str,
) -> None:
    POLYGON_XY: Final = [
        (0.2, 0.2),
        (0.5, 0.2),
        (0.5, 0.5),
    ]
    win._switch_canvas_mode(edit=False, create_mode="polygon")
    qtbot.wait(50)

    for xy in POLYGON_XY:
        click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=xy)

    submit_label_dialog(qtbot=qtbot, label_dialog=win._label_dialog, label=label)
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=POLYGON_XY[0])

    def _assert_shape_created() -> None:
        assert any(s.label == label for s in canvas.shapes)

    qtbot.waitUntil(_assert_shape_created, timeout=3000)


@pytest.mark.gui
def test_draw_shape_appears_in_label_list(
    qtbot: QtBot,
    raw_win: MainWindow,
    pause: bool,
) -> None:
    win = raw_win
    canvas = win._canvas_widgets.canvas
    label_list = win._docks.label_list

    count_before = len(label_list)
    label = "test_shape"
    _draw_polygon(qtbot=qtbot, win=win, canvas=canvas, label=label)

    assert len(label_list) == count_before + 1
    shape_labels = [s.label for item in label_list if (s := item.shape()) is not None]
    assert label in shape_labels

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_click_label_list_entry_selects_canvas_shape(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    win = annotated_win
    canvas = win._canvas_widgets.canvas
    label_list = win._docks.label_list

    assert len(canvas.shapes) > 0
    assert len(label_list) == len(canvas.shapes)

    canvas.deselect_shape()
    qtbot.waitUntil(lambda: not canvas.selected_shapes)

    first_item = label_list[0]
    expected_shape = first_item.shape()
    assert expected_shape is not None

    label_list.select_item(first_item)
    qtbot.waitUntil(lambda: expected_shape in canvas.selected_shapes)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_click_canvas_shape_selects_label_list_entry(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    win = annotated_win
    canvas = win._canvas_widgets.canvas
    label_list = win._docks.label_list

    assert len(canvas.shapes) > 0

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)

    selected_canvas_shape = canvas.selected_shapes[0]
    selected_list_items = label_list.selected_items()

    assert len(selected_list_items) == 1
    assert selected_list_items[0].shape() is selected_canvas_shape

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_rename_via_label_dialog_updates_shape_and_list(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    win = annotated_win
    canvas = win._canvas_widgets.canvas
    label_list = win._docks.label_list

    assert len(canvas.shapes) > 0

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)

    first_item = label_list[0]
    first_shape = first_item.shape()
    assert first_shape is not None
    assert first_shape.label is not None
    new_label = f"{first_shape.label}_renamed"

    submit_label_dialog(qtbot=qtbot, label_dialog=win._label_dialog, label=new_label)
    label_list.item_double_clicked.emit(first_item)

    def _assert_renamed() -> None:
        item = label_list[0]
        shape = item.shape()
        assert shape is not None
        assert shape.label == new_label
        assert new_label in item.text()

    qtbot.waitUntil(_assert_renamed, timeout=3000)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_shape_removes_label_list_entry(
    qtbot: QtBot,
    annotated_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    win = annotated_win
    canvas = win._canvas_widgets.canvas
    label_list = win._docks.label_list

    count_before = len(label_list)
    assert count_before > 0

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.Yes,
    )
    win.delete_selected_shapes()
    qtbot.waitUntil(lambda: len(label_list) == count_before - 1)
    assert len(canvas.shapes) == count_before - 1

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_open_different_file_repopulates_label_list(
    qtbot: QtBot,
    main_win: MainWinFactory,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(file_or_dir=str(data_path / "annotated"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    label_list = win._docks.label_list

    shapes_first = len(canvas.shapes)
    assert shapes_first > 0
    assert len(label_list) == shapes_first

    image_path_before = win._image_path
    win._open_next_image()

    def _assert_next_image_loaded() -> None:
        assert win._image_path is not None
        assert win._image_path != image_path_before

    qtbot.waitUntil(_assert_next_image_loaded, timeout=5000)

    def _assert_label_list_repopulated() -> None:
        assert len(label_list) == len(canvas.shapes)

    qtbot.waitUntil(_assert_label_list_repopulated, timeout=3000)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
