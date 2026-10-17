from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._label_file import read_label_file
from labelme._widgets._canvas import Canvas

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


def open_window(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    config_overrides: dict[str, bool] | None = None,
    output_dir: str | None = None,
) -> tuple[MainWindow, Canvas]:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides=config_overrides,
        output_dir=output_dir,
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win, win._canvas_widgets.canvas


@pytest.mark.gui
def test_shape_conversion_rectangle_to_polygon_and_undo(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win, canvas = open_window(main_win=main_win, qtbot=qtbot, data_path=data_path)

    rect_shape = canvas.shapes[1]
    assert rect_shape.shape_type == "rectangle"
    assert len(rect_shape.points) == 2

    canvas.select_shapes(shapes=[rect_shape])
    qtbot.wait(50)

    assert win._actions.convert_menu.isEnabled()
    assert win._actions.context_convert_menu.isEnabled()
    assert win._actions.convert_to_polygon.isEnabled()
    assert win._actions.convert_to_polygon.isVisible()
    assert not win._actions.convert_to_rectangle.isEnabled()
    assert not win._actions.convert_to_rectangle.isVisible()
    assert not win._actions.convert_to_linestrip.isEnabled()
    assert not win._actions.convert_to_linestrip.isVisible()

    win._actions.convert_to_polygon.trigger()
    qtbot.wait(50)

    converted = canvas.shapes[1]
    assert converted.shape_type == "polygon"
    assert converted.closed is True
    assert converted.label == "blue_block"
    assert converted.points.tolist() == [
        [245.0, 45.0],
        [355.0, 45.0],
        [355.0, 135.0],
        [245.0, 135.0],
    ]
    assert canvas.selected_shapes == [converted]

    win.undo_shape_edit()
    qtbot.wait(50)

    restored = canvas.shapes[1]
    assert restored.shape_type == "rectangle"
    assert restored.closed is True
    assert restored.points.tolist() == [[245.0, 45.0], [355.0, 135.0]]

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_shape_conversion_polygon_to_rectangle_bounding_box_and_undo(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win, canvas = open_window(main_win=main_win, qtbot=qtbot, data_path=data_path)

    poly_shape = canvas.shapes[0]
    assert poly_shape.shape_type == "polygon"
    assert len(poly_shape.points) == 5

    canvas.select_shapes(shapes=[poly_shape])
    qtbot.wait(50)

    assert win._actions.convert_menu.isEnabled()
    assert not win._actions.convert_to_polygon.isEnabled()
    assert win._actions.convert_to_rectangle.isEnabled()
    assert win._actions.convert_to_rectangle.isVisible()
    assert win._actions.convert_to_linestrip.isEnabled()
    assert win._actions.convert_to_linestrip.isVisible()

    win._actions.convert_to_rectangle.trigger()
    qtbot.wait(50)

    converted = canvas.shapes[0]
    assert converted.shape_type == "rectangle"
    assert converted.closed is True
    assert converted.label == "amber_kite"
    assert converted.points.tolist() == [[45.0, 45.0], [195.0, 185.0]]
    assert canvas.selected_shapes == [converted]

    win.undo_shape_edit()
    qtbot.wait(50)

    restored = canvas.shapes[0]
    assert restored.shape_type == "polygon"
    assert len(restored.points) == 5

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_shape_conversion_polygon_and_linestrip_toggle(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win, canvas = open_window(main_win=main_win, qtbot=qtbot, data_path=data_path)

    poly_shape = canvas.shapes[0]
    canvas.select_shapes(shapes=[poly_shape])
    qtbot.wait(50)

    win._actions.convert_to_linestrip.trigger()
    qtbot.wait(50)

    line = canvas.shapes[0]
    assert line.shape_type == "linestrip"
    assert len(line.points) == 5
    assert canvas.selected_shapes == [line]

    assert win._actions.convert_menu.isEnabled()
    assert win._actions.convert_to_polygon.isEnabled()
    assert not win._actions.convert_to_rectangle.isEnabled()
    assert not win._actions.convert_to_linestrip.isEnabled()

    win._actions.convert_to_polygon.trigger()
    qtbot.wait(50)

    poly2 = canvas.shapes[0]
    assert poly2.shape_type == "polygon"
    assert poly2.closed is True
    assert len(poly2.points) == 5

    win.undo_shape_edit()
    qtbot.wait(50)
    assert canvas.shapes[0].shape_type == "linestrip"

    win.undo_shape_edit()
    qtbot.wait(50)
    assert canvas.shapes[0].shape_type == "polygon"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_shape_conversion_linestrip_under_three_points_disabled(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    fixture_json = tmp_path / "linestrips.json"
    raw_img = data_path / "raw/2011_000003.jpg"
    fixture_json.write_text(
        json.dumps(
            {
                "version": "6.0.0",
                "flags": {},
                "shapes": [
                    {
                        "label": "two_pt_line",
                        "points": [[10.0, 10.0], [20.0, 20.0]],
                        "group_id": None,
                        "description": "",
                        "shape_type": "linestrip",
                        "flags": {},
                        "mask": None,
                    },
                    {
                        "label": "three_pt_line",
                        "points": [[30.0, 30.0], [40.0, 40.0], [50.0, 30.0]],
                        "group_id": None,
                        "description": "",
                        "shape_type": "linestrip",
                        "flags": {},
                        "mask": None,
                    },
                ],
                "imagePath": str(raw_img),
                "imageData": None,
                "imageHeight": 338,
                "imageWidth": 500,
            }
        )
    )

    win = main_win(file_or_dir=str(fixture_json))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas

    # 2-point linestrip cannot convert to polygon
    canvas.select_shapes(shapes=[canvas.shapes[0]])
    qtbot.wait(50)
    assert not win._actions.convert_menu.isEnabled()
    assert not win._actions.convert_to_polygon.isEnabled()

    # 3-point linestrip can convert to polygon
    canvas.select_shapes(shapes=[canvas.shapes[1]])
    qtbot.wait(50)
    assert win._actions.convert_menu.isEnabled()
    assert win._actions.convert_to_polygon.isEnabled()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_shape_conversion_multi_selection_intersection_and_undo(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    raw_img = data_path / "raw/2011_000003.jpg"
    fixture_json = tmp_path / "mixed.json"
    fixture_json.write_text(
        json.dumps(
            {
                "version": "6.0.0",
                "flags": {},
                "shapes": [
                    {
                        "label": "poly1",
                        "points": [[10.0, 10.0], [20.0, 30.0], [30.0, 10.0]],
                        "group_id": 1,
                        "description": "",
                        "shape_type": "polygon",
                        "flags": {},
                        "mask": None,
                    },
                    {
                        "label": "rect1",
                        "points": [[50.0, 50.0], [80.0, 80.0]],
                        "group_id": 2,
                        "description": "",
                        "shape_type": "rectangle",
                        "flags": {},
                        "mask": None,
                    },
                    {
                        "label": "line1",
                        "points": [[100.0, 100.0], [110.0, 120.0], [120.0, 100.0]],
                        "group_id": 3,
                        "description": "",
                        "shape_type": "linestrip",
                        "flags": {},
                        "mask": None,
                    },
                ],
                "imagePath": str(raw_img),
                "imageData": None,
                "imageHeight": 338,
                "imageWidth": 500,
            }
        )
    )

    win = main_win(file_or_dir=str(fixture_json))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas

    # Polygon + Rectangle -> intersection is empty, convert menu disabled
    canvas.select_shapes(shapes=[canvas.shapes[0], canvas.shapes[1]])
    qtbot.wait(50)
    assert not win._actions.convert_menu.isEnabled()

    # Rectangle + 3-point Linestrip -> both can convert to polygon
    canvas.select_shapes(shapes=[canvas.shapes[1], canvas.shapes[2]])
    qtbot.wait(50)
    assert win._actions.convert_menu.isEnabled()
    assert win._actions.convert_to_polygon.isEnabled()
    assert not win._actions.convert_to_rectangle.isEnabled()
    assert not win._actions.convert_to_linestrip.isEnabled()

    win._actions.convert_to_polygon.trigger()
    qtbot.wait(50)

    assert canvas.shapes[1].shape_type == "polygon"
    assert canvas.shapes[2].shape_type == "polygon"
    assert len(canvas.shapes[1].points) == 4
    assert len(canvas.shapes[2].points) == 3

    # A single Ctrl+Z reverts BOTH shapes in one step
    win.undo_shape_edit()
    qtbot.wait(50)

    assert canvas.shapes[1].shape_type == "rectangle"
    assert canvas.shapes[2].shape_type == "linestrip"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_shape_conversion_saves_clean_annotation_file(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win, canvas = open_window(
        main_win=main_win,
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )

    canvas.select_shapes(shapes=[canvas.shapes[1]])
    qtbot.wait(50)

    win._actions.convert_to_polygon.trigger()
    qtbot.wait(50)

    win._save_label_file(save_as=False)
    out_file = str(tmp_path / "2011_000003.json")
    assert_labelfile_sanity(out_file)

    label_file = read_label_file(filename=out_file)
    converted_shape = label_file.shapes[1]
    assert converted_shape["shape_type"] == "polygon"
    assert len(converted_shape["points"]) == 4

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
