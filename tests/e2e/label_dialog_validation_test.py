from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Final

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import draw_triangle
from .conftest import schedule_on_dialog
from .conftest import show_window_and_wait_for_imagedata

_RAW_FILE: Final[str] = "raw/2011_000003.jpg"
_VERTICES: Final = ((0.3, 0.3), (0.6, 0.3), (0.6, 0.6))
_CLOSE_POLYGON_CLICK: Final = _VERTICES[0]
_draw_triangle = partial(draw_triangle, vertices=_VERTICES)


@pytest.mark.gui
def test_blank_input_keeps_dialog_open(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(file_or_dir=str(data_path / _RAW_FILE))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    label_dialog = win._label_dialog
    num_shapes_before = len(canvas.shapes)

    _draw_triangle(qtbot=qtbot, win=win)

    dialog_stayed_open: list[bool] = []

    def _try_blank_then_cancel() -> None:
        label_dialog.edit.clear()
        qtbot.keyClick(label_dialog, Qt.Key_Return)
        qtbot.wait(50)
        if label_dialog.isVisible():
            dialog_stayed_open.append(True)
        qtbot.keyClick(label_dialog, Qt.Key_Escape)

    schedule_on_dialog(label_dialog=label_dialog, action=_try_blank_then_cancel)
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=_CLOSE_POLYGON_CLICK)

    qtbot.waitUntil(lambda: bool(dialog_stayed_open), timeout=3000)
    assert len(canvas.shapes) == num_shapes_before

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_validate_label_exact_rejects_unknown_label(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / _RAW_FILE),
        config_overrides={"validate_label": "exact", "labels": ["cat", "dog"]},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    label_dialog = win._label_dialog
    num_shapes_before = len(canvas.shapes)

    error_shown: list[bool] = []

    def _record_critical(*args: object, **kwargs: object) -> int:
        error_shown.append(True)
        return QMessageBox.Ok

    monkeypatch.setattr(QMessageBox, "critical", _record_critical)

    def _enter_unknown_label() -> None:
        label_dialog.edit.clear()
        qtbot.keyClicks(label_dialog.edit, "tiger")
        qtbot.wait(50)
        qtbot.keyClick(label_dialog.edit, Qt.Key_Enter)

    _draw_triangle(qtbot=qtbot, win=win)
    schedule_on_dialog(label_dialog=label_dialog, action=_enter_unknown_label)
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=_CLOSE_POLYGON_CLICK)

    qtbot.waitUntil(lambda: bool(error_shown), timeout=3000)
    assert len(canvas.shapes) == num_shapes_before

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_trailing_whitespace_label_is_stripped(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / _RAW_FILE),
        config_overrides={"labels": ["cat", "dog"]},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    label_dialog = win._label_dialog
    num_shapes_before = len(canvas.shapes)

    _draw_triangle(qtbot=qtbot, win=win)

    def _enter_trailing_space_label() -> None:
        label_dialog.edit.clear()
        qtbot.keyClicks(label_dialog.edit, "cat  ")
        qtbot.wait(50)
        qtbot.keyClick(label_dialog.edit, Qt.Key_Enter)

    schedule_on_dialog(label_dialog=label_dialog, action=_enter_trailing_space_label)
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=_CLOSE_POLYGON_CLICK)

    qtbot.waitUntil(lambda: len(canvas.shapes) == num_shapes_before + 1, timeout=3000)
    assert canvas.shapes[-1].label == "cat"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
