from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._label_file import read_label_file
from labelme._shape import Shape
from labelme._widgets._canvas import Canvas

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


def _open(
    *, main_win: MainWinFactory, qtbot: QtBot, data_path: Path, tmp_path: Path
) -> tuple[MainWindow, Canvas]:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides={"auto_save": True},
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win, win._canvas_widgets.canvas


def test_convert_mixed_selection_to_rectangles_and_undo(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win, canvas = _open(
        main_win=main_win, qtbot=qtbot, data_path=data_path, tmp_path=tmp_path
    )
    kite, box, hexagon = canvas.shapes[:3]
    # The rectangle already has the target kind, so it stays as it is.
    canvas.select_shapes(shapes=[kite, box, hexagon])
    qtbot.wait(50)
    assert win._actions.convert["rectangle"].isEnabled()

    win._actions.convert["rectangle"].trigger()
    qtbot.waitUntil(lambda: not win._save_writer.is_busy)

    converted = canvas.shapes[:3]
    assert [s.shape_type for s in converted] == ["rectangle"] * 3
    assert converted[1] is box
    assert [converted[0].label, converted[2].label] == ["amber_kite", "green_hexagon"]
    assert converted[0].points.tolist() == [
        kite.points.min(axis=0).tolist(),
        kite.points.max(axis=0).tolist(),
    ]
    assert canvas.selected_shapes == converted
    saved = read_label_file(filename=str(tmp_path / "2011_000003.json"))
    assert [s["shape_type"] for s in saved.shapes] == [
        "rectangle",
        "rectangle",
        "rectangle",
        "polygon",
        "polygon",
    ]

    win.undo_shape_edit()
    qtbot.wait(50)
    assert [s.shape_type for s in canvas.shapes[:3]] == [
        "polygon",
        "rectangle",
        "polygon",
    ]
    assert canvas.shapes[0].points.tolist() == kite.points.tolist()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


def test_convert_menu_lists_every_kind_and_enables_valid_ones(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win, canvas = _open(
        main_win=main_win, qtbot=qtbot, data_path=data_path, tmp_path=tmp_path
    )
    convert = win._actions.convert
    # A mode switch rebuilds the menus, which must not drop the submenu.
    win._actions.create_mode.trigger()
    win._actions.edit_mode.trigger()
    for menu in (win._menus.edit, canvas.shape_context_menu):
        (submenu,) = [
            m for a in menu.actions() if isinstance(m := a.menu(), QtWidgets.QMenu)
        ]
        assert submenu.actions() == list(convert.values())
        assert submenu.toolTipsVisible()

    canvas.select_shapes(shapes=[canvas.shapes[1]])
    qtbot.wait(50)
    assert [t for t, a in convert.items() if a.isEnabled()] == ["polygon"]
    assert [t for t, a in convert.items() if a.isChecked()] == ["rectangle"]
    assert convert["linestrip"].toolTip() == (
        "Only polygons and lines can be converted to linestrips"
    )
    assert convert["circle"].toolTip() == "Converting to circles isn’t supported"

    canvas.shapes[1].locked = True
    canvas.select_shapes(shapes=[canvas.shapes[1]])
    qtbot.wait(50)
    assert not convert["polygon"].isEnabled()
    assert convert["polygon"].toolTip() == "Unlock the selected shapes to convert them"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


def test_out_of_bounds_setting_refreshes_convert_actions(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win, canvas = _open(
        main_win=main_win, qtbot=qtbot, data_path=data_path, tmp_path=tmp_path
    )
    outside = Shape(
        label="ball",
        shape_type="circle",
        points=np.array([[-50.0, -50.0], [-40.0, -50.0]]),
    )
    win._commit_shapes(shapes=[*canvas.shapes, outside])
    canvas.select_shapes(shapes=[canvas.shapes[-1]])
    qtbot.wait(50)
    rectangle = win._actions.convert["rectangle"]
    assert not rectangle.isEnabled()

    # Unclipped, its box has area; clipped to the image, it has none.
    for enabled in (True, False):
        win._apply_setting_change(("canvas", "allow_out_of_bounds_points"), enabled)
        assert rectangle.isEnabled() is enabled

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
