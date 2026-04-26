from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from typing import Final

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox
from pytestqt.qtbot import QtBot

from labelme.widgets.label_dialog import LabelDialog

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import draw_triangle
from .conftest import schedule_on_dialog
from .conftest import show_window_and_wait_for_imagedata

_RAW_FILE: Final[str] = "raw/2011_000003.jpg"
_LABEL_FLAGS: Final[dict[str, list[str]]] = {"cat": ["a", "b"]}
_VERTICES: Final = ((0.3, 0.3), (0.6, 0.3), (0.6, 0.6))
_CLOSE_POLYGON_CLICK: Final = _VERTICES[0]
_draw_triangle = partial(draw_triangle, vertices=_VERTICES)


def _check_flag(label_dialog: LabelDialog, name: str) -> None:
    for cb in label_dialog.findChildren(QCheckBox):
        if cb.text() == name:
            cb.setChecked(True)
            return
    raise AssertionError(f"Flag checkbox {name!r} not found")


@pytest.mark.gui
@pytest.mark.parametrize(
    ("flag_to_toggle", "expected_flags"),
    [
        pytest.param(None, {"a": False, "b": False}, id="no-toggle"),
        pytest.param("b", {"a": False, "b": True}, id="toggle-b"),
    ],
)
def test_label_flags_applied_to_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    flag_to_toggle: str | None,
    expected_flags: dict[str, bool],
) -> None:
    win = main_win(
        file_or_dir=str(data_path / _RAW_FILE),
        config_overrides={"label_flags": _LABEL_FLAGS},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    label_dialog = win._label_dialog
    num_shapes_before = len(canvas.shapes)

    _draw_triangle(qtbot=qtbot, win=win)

    def _enter_cat() -> None:
        label_dialog.edit.clear()
        qtbot.keyClicks(label_dialog.edit, "cat")
        qtbot.wait(100)
        if flag_to_toggle is not None:
            _check_flag(label_dialog=label_dialog, name=flag_to_toggle)
        qtbot.keyClick(label_dialog.edit, Qt.Key_Enter)

    schedule_on_dialog(label_dialog=label_dialog, action=_enter_cat)
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=_CLOSE_POLYGON_CLICK)

    qtbot.waitUntil(lambda: len(canvas.shapes) == num_shapes_before + 1, timeout=3000)

    shape = canvas.shapes[-1]
    assert shape.label == "cat"
    assert shape.flags == expected_flags

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_flags_survive_save_reload_roundtrip(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / _RAW_FILE),
        config_overrides={"label_flags": _LABEL_FLAGS, "auto_save": False},
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    label_dialog = win._label_dialog
    num_shapes_before = len(canvas.shapes)

    _draw_triangle(qtbot=qtbot, win=win)

    def _enter_cat_a_true() -> None:
        label_dialog.edit.clear()
        qtbot.keyClicks(label_dialog.edit, "cat")
        qtbot.wait(100)
        _check_flag(label_dialog=label_dialog, name="a")
        qtbot.keyClick(label_dialog.edit, Qt.Key_Enter)

    schedule_on_dialog(label_dialog=label_dialog, action=_enter_cat_a_true)
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=_CLOSE_POLYGON_CLICK)

    qtbot.waitUntil(lambda: len(canvas.shapes) == num_shapes_before + 1, timeout=3000)
    assert canvas.shapes[-1].flags == {"a": True, "b": False}

    label_path = str(tmp_path / "2011_000003.json")
    assert win.save_labels(label_path=label_path)

    with open(label_path) as f:
        disk_data = json.load(f)
    cat_shapes = [s for s in disk_data["shapes"] if s["label"] == "cat"]
    assert len(cat_shapes) == 1
    assert cat_shapes[0]["flags"] == {"a": True, "b": False}

    win._load_file(image_or_label_path=label_path)
    qtbot.waitUntil(lambda: any(s.label == "cat" for s in canvas.shapes), timeout=3000)

    reloaded_shape = next(s for s in canvas.shapes if s.label == "cat")
    assert reloaded_shape.flags == {"a": True, "b": False}

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
