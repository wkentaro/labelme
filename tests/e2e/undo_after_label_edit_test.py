from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import _SaveTarget

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import draw_and_commit_polygon
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata
from .conftest import submit_label_dialog


def test_undo_creation_keeps_earlier_label_edit(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    # A label pattern with flags, so the edit changes flags as well as the label.
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides={"label_flags": {"person": ["occluded"]}},
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    edited_flags = {"occluded": False}
    canvas = win._canvas_widgets.canvas
    label_list = win._docks.label_list
    label_dialog = win._label_dialog
    num_shapes = len(canvas.shapes)
    untouched_points = [s.points.copy() for s in canvas.shapes[1:]]

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    submit_label_dialog(qtbot=qtbot, label_dialog=label_dialog, label="person")
    label_list.item_double_clicked.emit(label_list[0])
    qtbot.waitUntil(lambda: not label_dialog.isVisible(), timeout=3000)
    assert canvas.shapes[0].label == "person"
    assert canvas.shapes[0].flags == edited_flags

    draw_and_commit_polygon(
        qtbot=qtbot, win=win, label="cat", vertices=((0.7, 0.7), (0.9, 0.7), (0.9, 0.9))
    )
    assert len(canvas.shapes) == num_shapes + 1

    # Undo must remove only the new shape; the earlier edit stays.
    win.undo_shape_edit()
    qtbot.wait(50)
    assert len(canvas.shapes) == num_shapes
    assert canvas.shapes[0].label == "person"
    assert canvas.shapes[0].flags == edited_flags
    for shape, points in zip(canvas.shapes[1:], untouched_points, strict=True):
        assert np.array_equal(shape.points, points)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


def test_undo_back_to_the_saved_state_clears_the_unsaved_mark(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides=dict(auto_save=False),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    for _ in range(2):
        qtbot.keyPress(canvas, Qt.Key.Key_Right)
        qtbot.keyRelease(canvas, Qt.Key.Key_Right)
    assert win.windowTitle().endswith("*")
    assert win._status_bar.save.text() == "Unsaved changes"

    # One step back is still off the file; the second is the file itself.
    win.undo_shape_edit()
    assert win._is_changed
    assert win.windowTitle().endswith("*")
    win.undo_shape_edit()
    assert not win._is_changed
    assert not win._actions.save.isEnabled()
    assert not win.windowTitle().endswith("*")
    assert win._status_bar.save.text() == ""

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


def test_undo_on_carried_shapes_keeps_them_unsaved(
    *, main_win: MainWinFactory, qtbot: QtBot, data_path: Path
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.jpg"),
        config_overrides={"keep_prev": True, "auto_save": False},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    assert win._load_file(image_or_label_path=str(data_path / "raw/2011_000003.jpg"))
    canvas = win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    qtbot.keyClick(canvas, Qt.Key.Key_Right)

    # Back to the carried Shapes, which this Image's file does not hold.
    win.undo_shape_edit()

    is_changed = win._is_changed
    # A dirty window would block teardown on the Unsaved Changes dialog.
    win.mark_clean()
    assert is_changed


def test_undo_to_what_a_late_save_wrote_is_clean(
    *, main_win: MainWinFactory, qtbot: QtBot, data_path: Path, tmp_path: Path
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides=dict(auto_save=False),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    qtbot.keyClick(canvas, Qt.Key.Key_Right)
    request = win._capture_save_request(label_path=win._save_destination())
    written_revision = win._save_revision
    qtbot.keyClick(canvas, Qt.Key.Key_Right)

    # The write of the first nudge lands after the second one.
    win._on_save_finished(request, written_revision, None)
    states = [win._is_changed]
    win.undo_shape_edit()
    states.append(win._is_changed)
    win.undo_shape_edit()
    states.append(win._is_changed)
    # A dirty window would block teardown on the Unsaved Changes dialog.
    win.mark_clean()
    # Back to the late write is clean; past it, to the loaded file, is not.
    assert states == [True, False, True]


def test_undo_after_a_failed_save_as_keeps_the_unsaved_mark(
    *, main_win: MainWinFactory, qtbot: QtBot, data_path: Path, tmp_path: Path
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides=dict(auto_save=False),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    qtbot.keyClick(canvas, Qt.Key.Key_Right)
    # Save As chose another file, and writing it failed.
    win._save_target = _SaveTarget(
        path=str(tmp_path / "other.json"), overwrite_confirmed=True
    )
    request = win._capture_save_request(label_path=win._save_target.path)
    win._on_save_finished(request, win._save_revision, OSError("disk full"))

    # Back to the loaded file's Shapes, which the chosen file does not hold.
    win.undo_shape_edit()

    is_changed = win._is_changed
    # A dirty window would block teardown on the Unsaved Changes dialog.
    win.mark_clean()
    assert is_changed


def test_undo_to_discarded_shapes_keeps_the_unsaved_mark(
    *, main_win: MainWinFactory, qtbot: QtBot, data_path: Path, tmp_path: Path
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides=dict(auto_save=False),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    qtbot.keyClick(canvas, Qt.Key.Key_Right)
    # Discarding to open a folder clears the mark but keeps the Shapes open.
    win.mark_clean()
    qtbot.keyClick(canvas, Qt.Key.Key_Right)

    # Back to the discarded Shapes, which the file does not hold.
    win.undo_shape_edit()

    is_changed = win._is_changed
    win.mark_clean()
    assert is_changed


def test_undo_past_a_manual_save_keeps_the_unsaved_mark(
    *, main_win: MainWinFactory, qtbot: QtBot, data_path: Path
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides=dict(auto_save=False),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    qtbot.keyClick(canvas, Qt.Key.Key_Right)
    assert win.save_labels(label_path=win._save_destination())

    # Back to the loaded Shapes, which the save replaced in the file.
    win.undo_shape_edit()

    is_changed = win._is_changed
    # A dirty window would block teardown on the Unsaved Changes dialog.
    win.mark_clean()
    assert is_changed


def test_undo_after_deleting_the_file_keeps_the_unsaved_mark(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides=dict(auto_save=False),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    loaded = [shape.copy() for shape in canvas.shapes]
    assert win.save_labels(label_path=win._save_destination())
    monkeypatch.setattr(win, "_confirm_deletion", lambda **_kwargs: True)
    win.delete_file()
    # Pasting selects the pasted Shapes, and the nudge moves them all.
    win._insert_shapes(shapes=loaded)
    qtbot.keyClick(canvas, Qt.Key.Key_Right)

    # Back to the Shapes of the deleted file, which no file holds.
    win.undo_shape_edit()

    is_changed = win._is_changed
    win.mark_clean()
    assert is_changed
