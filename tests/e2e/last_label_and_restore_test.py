from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from typing import Final

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets.label_dialog import LabelDialog

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import draw_and_commit_polygon
from .conftest import draw_triangle
from .conftest import schedule_on_dialog
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata

_SHAPE_TIMEOUT_MS: Final = 5_000
_VERTICES: Final = ((0.2, 0.2), (0.6, 0.2), (0.6, 0.6))
_draw_triangle = partial(draw_triangle, vertices=_VERTICES)
_draw_and_commit_polygon = partial(draw_and_commit_polygon, vertices=_VERTICES)


def _schedule_capture_then_cancel(
    *,
    label_dialog: LabelDialog,
    captured: list[str],
) -> None:
    def _action() -> None:
        captured.append(label_dialog.edit.text())
        label_dialog.reject()

    schedule_on_dialog(label_dialog=label_dialog, action=_action)


@pytest.fixture()
def discard_unsaved_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard,
    )


@pytest.mark.gui
def test_last_label_memo(
    qtbot: QtBot,
    raw_win: MainWindow,
    *,
    pause: bool,
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    label_dialog = raw_win._label_dialog

    _draw_and_commit_polygon(qtbot=qtbot, win=raw_win, label="foo")

    captured: list[str] = []
    _schedule_capture_then_cancel(label_dialog=label_dialog, captured=captured)

    _draw_triangle(qtbot=qtbot, win=raw_win)
    qtbot.keyPress(canvas, Qt.Key.Key_Return)

    qtbot.waitUntil(lambda: bool(captured), timeout=_SHAPE_TIMEOUT_MS)

    assert captured[0] == "foo"

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_restore_last_shape_via_undo(
    qtbot: QtBot,
    raw_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    *,
    pause: bool,
) -> None:
    canvas = raw_win._canvas_widgets.canvas

    _draw_and_commit_polygon(qtbot=qtbot, win=raw_win, label="restore_me")
    raw_win._switch_canvas_mode(edit=True, create_mode=None)

    assert len(canvas.shapes) == 1
    original_points = [
        QPointF(float(p[0]), float(p[1])) for p in canvas.shapes[0].points
    ]

    monkeypatch.setattr(raw_win, "_confirm_deletion", lambda *_args, **_kwargs: True)

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    raw_win.delete_selected_shapes()
    qtbot.waitUntil(lambda: len(canvas.shapes) == 0, timeout=_SHAPE_TIMEOUT_MS)

    raw_win.undo_shape_edit()
    qtbot.waitUntil(lambda: len(canvas.shapes) == 1, timeout=_SHAPE_TIMEOUT_MS)

    restored = canvas.shapes[0]
    assert restored.label == "restore_me"
    assert [
        QPointF(float(p[0]), float(p[1])) for p in restored.points
    ] == original_points

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_first_and_subsequent_shapes_can_be_undone_and_saved(
    qtbot: QtBot,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    data_path: Path,
    tmp_path: Path,
    *,
    pause: bool,
) -> None:
    raw_win = main_win(
        file_or_dir=data_path / "raw/2011_000003.jpg",
        config_overrides={"auto_save": False},
        output_dir=tmp_path,
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=raw_win)

    canvas = raw_win._canvas_widgets.canvas
    label_list = raw_win._docks.label_list

    assert not canvas.shapes
    assert not canvas.can_restore_shape
    assert not raw_win._actions.undo.isEnabled()

    _draw_and_commit_polygon(qtbot=qtbot, win=raw_win, label="first")

    assert canvas.can_restore_shape
    assert raw_win._actions.undo.isEnabled()
    assert len(canvas.shapes) == 1
    assert len(label_list) == 1

    _draw_and_commit_polygon(qtbot=qtbot, win=raw_win, label="second")

    raw_win._actions.undo.trigger()
    assert [shape.label for shape in canvas.shapes] == ["first"]
    assert len(label_list) == 1

    raw_win._actions.undo.trigger()
    assert not canvas.shapes
    assert len(label_list) == 0
    assert not canvas.can_restore_shape
    assert not raw_win._actions.undo.isEnabled()

    label_path = tmp_path / "manual-save.json"
    monkeypatch.setattr(raw_win, "prompt_save_file_path", lambda: str(label_path))
    raw_win._save_label_file(save_as=False)

    with label_path.open() as f:
        assert json.load(f)["shapes"] == []

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
@pytest.mark.usefixtures("discard_unsaved_changes")
def test_undo_not_enabled_after_opening_image_with_shapes_carried_forward(
    qtbot: QtBot,
    main_win: MainWinFactory,
    data_path: Path,
    tmp_path: Path,
    *,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=data_path / "raw",
        config_overrides={"keep_prev": True, "auto_save": False},
        output_dir=tmp_path,
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    _draw_and_commit_polygon(qtbot=qtbot, win=win, label="carried")
    assert len(canvas.shapes) == 1

    win._actions.open_next_img.trigger()
    qtbot.waitUntil(lambda: len(canvas.shapes) == 1, timeout=_SHAPE_TIMEOUT_MS)

    # Keep Previous Annotation carried the shape onto the next image, but
    # nothing has been edited on this image yet: Undo must stay disabled so
    # a stray trigger cannot silently discard the carried-forward shape.
    assert [shape.label for shape in canvas.shapes] == ["carried"]
    assert not canvas.can_restore_shape
    assert not win._actions.undo.isEnabled()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize("image_dir", ["raw", "annotated"])
@pytest.mark.usefixtures("discard_unsaved_changes")
def test_navigation_disables_undo_for_clean_image_history(
    qtbot: QtBot,
    main_win: MainWinFactory,
    data_path: Path,
    image_dir: str,
    *,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=data_path / image_dir,
        config_overrides={"auto_save": False},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    _draw_and_commit_polygon(qtbot=qtbot, win=win, label="new")
    assert win._actions.undo.isEnabled()

    image_path = win._image_path

    win._actions.open_next_img.trigger()
    qtbot.waitUntil(lambda: win._image_path != image_path, timeout=_SHAPE_TIMEOUT_MS)

    assert not canvas.can_restore_shape
    assert not win._actions.undo.isEnabled()
    assert not win._is_changed

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_save_keeps_shape_undo_disabled_while_drawing(
    qtbot: QtBot,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    data_path: Path,
    tmp_path: Path,
    *,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=data_path / "raw/2011_000003.jpg",
        config_overrides={"auto_save": False},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    _draw_and_commit_polygon(qtbot=qtbot, win=win, label="committed")
    _draw_triangle(qtbot=qtbot, win=win)

    assert canvas.is_drawing
    assert not win._actions.undo.isEnabled()
    assert win._actions.undo_last_point.isEnabled()

    monkeypatch.setattr(
        win,
        "prompt_save_file_path",
        lambda: str(tmp_path / "save-while-drawing.json"),
    )
    win._save_label_file(save_as=False)

    assert canvas.is_drawing
    assert not win._actions.undo.isEnabled()
    assert win._actions.undo_last_point.isEnabled()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
