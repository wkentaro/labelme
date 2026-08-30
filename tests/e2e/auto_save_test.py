from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

import labelme._app
from labelme._app import MainWindow
from labelme._widgets._shape_render import bounds as _shape_bounds

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import draw_and_commit_polygon
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata

_TEST_FILE_NAME: Final[str] = "annotated/2011_000003.json"
_RAW_FILE_NAME: Final[str] = "raw/2011_000003.jpg"
_VERTICES: Final[tuple[tuple[float, float], ...]] = (
    (0.2, 0.2),
    (0.6, 0.2),
    (0.6, 0.6),
)


@pytest.fixture()
def _auto_save_win(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> MainWindow:
    win = main_win(
        file_or_dir=str(data_path / _TEST_FILE_NAME),
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win


@pytest.fixture()
def _raw_auto_save_win(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> MainWindow:
    win = main_win(
        file_or_dir=str(data_path / _RAW_FILE_NAME),
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win


@pytest.mark.gui
def test_auto_save_on_shape_move(
    qtbot: QtBot,
    _auto_save_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    label_file = tmp_path / Path(_TEST_FILE_NAME).name
    assert not label_file.exists()

    canvas = _auto_save_win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    original_center = QPointF(_shape_bounds(shape=canvas.selected_shapes[0]).center())

    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.wait(50)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)
    qtbot.wait(50)

    new_center = _shape_bounds(shape=canvas.selected_shapes[0]).center()
    assert abs((new_center.x() - original_center.x()) - 5.0) < 1.0

    assert label_file.exists()
    assert_labelfile_sanity(str(label_file))

    close_or_pause(qtbot=qtbot, widget=_auto_save_win, pause=pause)


@pytest.mark.gui
def test_enabling_auto_save_on_dirty_annotation_clears_dirty_state(
    monkeypatch: pytest.MonkeyPatch,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> None:
    prompt_shown = False

    def record_prompt(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        nonlocal prompt_shown
        prompt_shown = True
        return QMessageBox.StandardButton.Discard

    monkeypatch.setattr(QMessageBox, "question", record_prompt)
    win = main_win(
        file_or_dir=str(data_path / _TEST_FILE_NAME),
        config_overrides=dict(auto_save=False),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    label_file = tmp_path / Path(_TEST_FILE_NAME).name
    canvas = win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)

    assert win._is_changed
    assert win._actions.save.isEnabled()
    assert win.windowTitle().endswith("*")
    assert not label_file.exists()

    win._actions.save_auto.setChecked(True)
    draw_and_commit_polygon(
        qtbot=qtbot,
        win=win,
        label="auto-saved",
        vertices=_VERTICES,
    )

    assert label_file.exists()
    with open(label_file) as f:
        saved_labels = [shape["label"] for shape in json.load(f)["shapes"]]
    assert "auto-saved" in saved_labels
    assert not win._is_changed
    assert not win._actions.save.isEnabled()
    assert not win.windowTitle().endswith("*")
    # The window is still in polygon create mode: a successful auto-save must
    # clear only the dirty indicators, not re-enable the draw actions.
    assert not dict(win._actions.draw)["polygon"].isEnabled()

    win.close()
    qtbot.waitUntil(lambda: not win.isVisible(), timeout=3000)

    assert not prompt_shown


@pytest.mark.gui
def test_auto_save_on_undo(
    qtbot: QtBot,
    _auto_save_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    label_file = tmp_path / Path(_TEST_FILE_NAME).name

    canvas = _auto_save_win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    original_shape = canvas.selected_shapes[0]
    original_center = QPointF(_shape_bounds(shape=original_shape).center())
    original_points = [(float(x), float(y)) for x, y in original_shape.points]

    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.wait(50)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)
    qtbot.wait(50)
    assert label_file.exists()

    _auto_save_win.undo_shape_edit()
    qtbot.wait(50)

    restored_center = _shape_bounds(shape=canvas.shapes[0]).center()
    assert abs(restored_center.x() - original_center.x()) < 1.0

    with open(label_file) as f:
        saved_xs = [x for x, _ in json.load(f)["shapes"][0]["points"]]
    assert abs(min(saved_xs) - min(x for x, _ in original_points)) < 1.0

    assert_labelfile_sanity(str(label_file))

    close_or_pause(qtbot=qtbot, widget=_auto_save_win, pause=pause)


@pytest.mark.gui
def test_auto_save_on_undo_of_first_shape(
    qtbot: QtBot,
    _raw_auto_save_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    label_file = tmp_path / f"{Path(_RAW_FILE_NAME).stem}.json"
    canvas = _raw_auto_save_win._canvas_widgets.canvas

    draw_and_commit_polygon(
        qtbot=qtbot,
        win=_raw_auto_save_win,
        label="first",
        vertices=_VERTICES,
    )

    assert _raw_auto_save_win._actions.undo.isEnabled()
    with label_file.open() as f:
        assert len(json.load(f)["shapes"]) == 1

    _raw_auto_save_win._actions.undo.trigger()

    assert not canvas.shapes
    assert len(_raw_auto_save_win._docks.label_list) == 0
    assert not canvas.can_restore_shape
    assert not _raw_auto_save_win._actions.undo.isEnabled()
    with label_file.open() as f:
        assert json.load(f)["shapes"] == []

    close_or_pause(qtbot=qtbot, widget=_raw_auto_save_win, pause=pause)


@pytest.mark.gui
def test_failed_auto_save_keeps_annotation_dirty_and_allows_manual_retry(
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    _raw_auto_save_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    label_file = tmp_path / f"{Path(_RAW_FILE_NAME).stem}.json"
    assert not label_file.exists()
    assert not _raw_auto_save_win.windowTitle().endswith("*")

    errors_shown: list[tuple[str, str]] = []

    def _record_critical(
        _parent: object, title: str, message: str
    ) -> QMessageBox.StandardButton:
        errors_shown.append((title, message))
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "critical", _record_critical)

    original_write_label_file = labelme._app.write_label_file

    def _raise_permission_error(*args: object, **kwargs: object) -> None:
        raise PermissionError("read-only output directory")

    monkeypatch.setattr(labelme._app, "write_label_file", _raise_permission_error)

    draw_and_commit_polygon(
        qtbot=qtbot,
        win=_raw_auto_save_win,
        label="cat",
        vertices=_VERTICES,
    )

    assert len(errors_shown) == 1
    assert errors_shown[0][0] == _raw_auto_save_win.tr("Error saving label data")
    assert "read-only output directory" in errors_shown[0][1]
    assert _raw_auto_save_win.windowTitle().endswith("*")
    assert _raw_auto_save_win._actions.save.isEnabled()
    assert _raw_auto_save_win._actions.save_auto.isChecked()

    canvas = _raw_auto_save_win._canvas_widgets.canvas
    _raw_auto_save_win._switch_canvas_mode(edit=True, create_mode=None)
    qtbot.wait(50)
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)

    assert len(errors_shown) == 1

    close_prompts: list[bool] = []

    def _cancel_close(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        close_prompts.append(True)
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", _cancel_close)
    _raw_auto_save_win.close()

    assert close_prompts == [True]
    assert _raw_auto_save_win.isVisible()

    monkeypatch.setattr(labelme._app, "write_label_file", original_write_label_file)
    monkeypatch.setattr(
        _raw_auto_save_win, "prompt_save_file_path", lambda: str(label_file)
    )
    _raw_auto_save_win._actions.save.trigger()

    qtbot.waitUntil(label_file.exists, timeout=3000)
    assert_labelfile_sanity(str(label_file))
    with open(label_file) as f:
        saved_shapes = json.load(f)["shapes"]
    assert len(saved_shapes) == 1
    assert saved_shapes[0]["label"] == "cat"
    assert saved_shapes[0]["points"] == canvas.shapes[0].points.tolist()
    assert not _raw_auto_save_win.windowTitle().endswith("*")
    assert not _raw_auto_save_win._actions.save.isEnabled()

    monkeypatch.setattr(labelme._app, "write_label_file", _raise_permission_error)
    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)

    assert len(errors_shown) == 2

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )
    close_or_pause(qtbot=qtbot, widget=_raw_auto_save_win, pause=pause)


@pytest.mark.gui
def test_failed_auto_save_shows_error_again_after_target_changes(
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    _raw_auto_save_win: MainWindow,
    tmp_path: Path,
    pause: bool,
) -> None:
    errors_shown: list[bool] = []

    def _record_critical(*args: object, **kwargs: object) -> int:
        errors_shown.append(True)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "critical", _record_critical)

    def _raise_permission_error(*args: object, **kwargs: object) -> None:
        raise PermissionError("read-only output directory")

    monkeypatch.setattr(labelme._app, "write_label_file", _raise_permission_error)

    draw_and_commit_polygon(
        qtbot=qtbot,
        win=_raw_auto_save_win,
        label="cat",
        vertices=_VERTICES,
    )

    canvas = _raw_auto_save_win._canvas_widgets.canvas
    _raw_auto_save_win._switch_canvas_mode(edit=True, create_mode=None)
    qtbot.wait(50)
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)
    assert errors_shown == [True]

    new_output_dir = tmp_path / "new-output"
    new_output_dir.mkdir()
    _raw_auto_save_win._output_dir = new_output_dir

    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)
    assert errors_shown == [True, True]

    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)
    assert errors_shown == [True, True]

    image_path = _raw_auto_save_win._image_path
    assert image_path is not None
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )
    _raw_auto_save_win.close_file()
    _raw_auto_save_win._load_file(image_or_label_path=image_path)

    draw_and_commit_polygon(
        qtbot=qtbot,
        win=_raw_auto_save_win,
        label="cat",
        vertices=_VERTICES,
    )
    assert errors_shown == [True, True, True]

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard,
    )

    close_or_pause(qtbot=qtbot, widget=_raw_auto_save_win, pause=pause)
