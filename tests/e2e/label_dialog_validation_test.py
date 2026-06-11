from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Final

import pytest
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import click_canvas_fraction
from .conftest import draw_and_commit_polygon
from .conftest import draw_triangle
from .conftest import schedule_on_dialog
from .conftest import show_window_and_wait_for_imagedata

_RAW_FILE: Final[str] = "raw/2011_000003.jpg"
_VERTICES: Final = ((0.3, 0.3), (0.6, 0.3), (0.6, 0.6))
_CLOSE_POLYGON_CLICK: Final = _VERTICES[0]
_draw_triangle = partial(draw_triangle, vertices=_VERTICES)


def _label_list_texts(label_list: QtWidgets.QListWidget) -> list[str]:
    texts: list[str] = []
    for i in range(label_list.count()):
        item = label_list.item(i)
        assert item is not None
        texts.append(item.text())
    return texts


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
        qtbot.keyClick(label_dialog, Qt.Key.Key_Return)
        qtbot.wait(50)
        if label_dialog.isVisible():
            dialog_stayed_open.append(True)
        qtbot.keyClick(label_dialog, Qt.Key.Key_Escape)

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
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "critical", _record_critical)

    def _enter_unknown_label() -> None:
        label_dialog.edit.clear()
        qtbot.keyClicks(label_dialog.edit, "tiger")
        qtbot.wait(50)
        qtbot.keyClick(label_dialog.edit, Qt.Key.Key_Enter)

    _draw_triangle(qtbot=qtbot, win=win)
    schedule_on_dialog(label_dialog=label_dialog, action=_enter_unknown_label)
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=_CLOSE_POLYGON_CLICK)

    qtbot.waitUntil(lambda: bool(error_shown), timeout=3000)
    assert len(canvas.shapes) == num_shapes_before

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_arrow_keys_in_label_edit_navigate_label_list(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / _RAW_FILE),
        config_overrides={"labels": ["cat", "dog", "person"]},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    label_dialog = win._label_dialog

    after_down: list[str] = []

    def _press_down_capture_then_cancel() -> None:
        # Sorted labels: cat, dog, person. Pin selection to row 0 so Down
        # forwarded from the line edit advances to row 1.
        label_dialog.label_list.setCurrentRow(0)
        qtbot.keyClick(label_dialog.edit, Qt.Key.Key_Down)
        qtbot.wait(50)
        item = label_dialog.label_list.currentItem()
        if item is not None:
            after_down.append(item.text())
        qtbot.keyClick(label_dialog, Qt.Key.Key_Escape)

    _draw_triangle(qtbot=qtbot, win=win)
    schedule_on_dialog(
        label_dialog=label_dialog, action=_press_down_capture_then_cancel
    )
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=_CLOSE_POLYGON_CLICK)

    qtbot.waitUntil(lambda: bool(after_down), timeout=3000)
    assert after_down[0] == "dog"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_add_label_history_dedups_repeated_labels_and_keeps_sorted(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / _RAW_FILE),
        config_overrides={"labels": ["cat"]},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    label_list = win._label_dialog.label_list
    assert _label_list_texts(label_list=label_list) == ["cat"]

    triangle_zebra: Final = ((0.10, 0.10), (0.25, 0.10), (0.25, 0.25))
    triangle_cat: Final = ((0.40, 0.10), (0.55, 0.10), (0.55, 0.25))
    triangle_ant: Final = ((0.70, 0.10), (0.85, 0.10), (0.85, 0.25))

    draw_and_commit_polygon(
        qtbot=qtbot, win=win, label="zebra", vertices=triangle_zebra
    )
    assert _label_list_texts(label_list=label_list) == ["cat", "zebra"]

    # "cat" already in the list; the dedup branch must keep the count flat.
    draw_and_commit_polygon(qtbot=qtbot, win=win, label="cat", vertices=triangle_cat)
    assert _label_list_texts(label_list=label_list) == ["cat", "zebra"]

    # New label that sorts before existing entries proves sortItems runs
    # after the append, not just on construction.
    draw_and_commit_polygon(qtbot=qtbot, win=win, label="ant", vertices=triangle_ant)
    assert _label_list_texts(label_list=label_list) == ["ant", "cat", "zebra"]

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_label_completer_autocompletes_typed_prefix(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / _RAW_FILE),
        config_overrides={"labels": ["cat", "dog", "person"]},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    label_dialog = win._label_dialog

    completion: list[str] = []

    def _type_p_capture_completion_then_cancel() -> None:
        # LabelQLineEdit.keyPressEvent forwards Up/Down to the list widget
        # and routes everything else to QLineEdit, so typing 'p' must drive
        # the QCompleter to suggest the only "p"-prefixed label.
        label_dialog.edit.clear()
        qtbot.keyClick(label_dialog.edit, Qt.Key.Key_P)
        qtbot.wait(50)
        completion.append(label_dialog.edit.completer().currentCompletion())
        qtbot.keyClick(label_dialog, Qt.Key.Key_Escape)

    _draw_triangle(qtbot=qtbot, win=win)
    schedule_on_dialog(
        label_dialog=label_dialog,
        action=_type_p_capture_completion_then_cancel,
    )
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=_CLOSE_POLYGON_CLICK)

    qtbot.waitUntil(lambda: bool(completion), timeout=3000)
    assert completion[0] == "person"

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
        qtbot.keyClick(label_dialog.edit, Qt.Key.Key_Enter)

    schedule_on_dialog(label_dialog=label_dialog, action=_enter_trailing_space_label)
    click_canvas_fraction(qtbot=qtbot, canvas=canvas, xy=_CLOSE_POLYGON_CLICK)

    qtbot.waitUntil(lambda: len(canvas.shapes) == num_shapes_before + 1, timeout=3000)
    assert canvas.shapes[-1].label == "cat"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
