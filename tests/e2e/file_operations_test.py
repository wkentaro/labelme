from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._label_file import read_label_file

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
@pytest.mark.skipif(os.name == "nt", reason="directory symlinks require privileges")
@pytest.mark.parametrize("use_image_alias", [False, True])
def test_save_through_directory_alias_reopens_source_image(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    use_image_alias: bool,
) -> None:
    project = tmp_path / "nested" / "project"
    (project / "labels").mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(project, target_is_directory=True)
    image_path = data_path / "raw" / "2011_000003.jpg"
    if use_image_alias:
        (project / "image.jpg").symlink_to(image_path)
        image_path = alias / "image.jpg"
    win = main_win(
        file_or_dir=str(image_path), config_overrides={"with_image_data": False}
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    assert win._annotation is not None
    image_data = win._annotation.image_data
    label_path = alias / "labels" / "saved.json"

    assert win.save_labels(label_path=str(label_path))
    saved = read_label_file(filename=str(label_path))
    assert saved.image_data == image_data
    assert (label_path.parent / saved.image_path).samefile(image_path)
    if use_image_alias:
        assert saved.image_path == "../image.jpg"
    assert win._load_file(image_or_label_path=str(label_path))
    assert win._annotation is not None
    assert win._annotation.image_data == image_data
    assert win._image_path is not None
    assert Path(win._image_path).samefile(image_path)
    assert win.save_labels(label_path=str(label_path))
    assert read_label_file(filename=str(label_path)).image_data == image_data


@pytest.mark.gui
@pytest.mark.parametrize(
    "set_fit_mode",
    [MainWindow.set_fit_window_mode, MainWindow.set_fit_width_mode],
)
def test_close_file(
    *,
    annotated_win: MainWindow,
    qtbot: QtBot,
    pause: bool,
    set_fit_mode: Callable[[MainWindow], None],
) -> None:
    assert annotated_win._annotation is not None
    assert annotated_win._canvas_widgets.canvas.isEnabled()

    set_fit_mode(annotated_win)
    annotated_win.close_file()
    annotated_win.resize(annotated_win.width() + 50, annotated_win.height() + 50)
    qtbot.wait(50)

    assert not annotated_win._canvas_widgets.canvas.isEnabled()
    assert annotated_win._annotation is None
    assert annotated_win.windowTitle() == "Labelme"

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_delete_label_file(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated"),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    label_file = data_path / "annotated/2011_000003.json"
    assert label_file.exists()

    item = win._docks.file_list.currentItem()
    assert item is not None
    assert item.checkState() == Qt.CheckState.Checked

    monkeypatch.setattr(win, "_confirm_deletion", lambda *_args, **_kwargs: True)
    win.delete_file()
    qtbot.wait(50)

    assert not label_file.exists()

    item = win._docks.file_list.currentItem()
    assert item is not None
    assert item.checkState() == Qt.CheckState.Unchecked

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_label_file_keeps_image(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated"),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    assert not canvas.pixmap.isNull()
    assert canvas.shapes
    assert len(win._docks.label_list) > 0

    monkeypatch.setattr(win, "_confirm_deletion", lambda *_args, **_kwargs: True)
    win.delete_file()
    qtbot.wait(50)

    # The annotations are cleared, but the image stays on the canvas.
    assert not canvas.pixmap.isNull()
    assert canvas.isEnabled()
    assert canvas.shapes == []
    assert len(win._docks.label_list) == 0
    assert win._image_path is not None
    assert win._annotation is not None

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_failed_delete_preserves_annotation_and_reports_error(
    *,
    annotated_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    critical_messages: list[str],
) -> None:
    label_path = Path(annotated_win.current_label_file_path())
    original_bytes = label_path.read_bytes()
    annotated_win._actions.save_auto.setChecked(False)
    annotated_win._canvas_widgets.canvas.shapes[0].label = "unsaved edit"
    annotated_win.mark_dirty()
    shapes = annotated_win._canvas_widgets.canvas.shapes[:]
    original_unlink = Path.unlink

    def reject_unlink(path: Path, /, *, missing_ok: bool = False) -> None:
        if path == label_path:
            raise PermissionError("read-only directory")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", reject_unlink)
    monkeypatch.setattr(annotated_win, "_confirm_deletion", lambda **_kwargs: True)
    annotated_win.delete_file()

    assert label_path.read_bytes() == original_bytes
    assert annotated_win._canvas_widgets.canvas.shapes == shapes
    assert annotated_win._is_changed
    assert annotated_win._actions.delete_file.isEnabled()
    assert len(critical_messages) == 1
    assert "read-only directory" in critical_messages[0]
    annotated_win.mark_clean()


@pytest.mark.gui
def test_delete_file_respects_output_dir(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "raw/2011_000003.jpg"),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    saved_path = tmp_path / "2011_000003.json"
    image_adjacent_path = data_path / "raw/2011_000003.json"
    assert not saved_path.exists()
    assert not image_adjacent_path.exists()

    # Before any save, no label file is tracked, so the prospective path must
    # still resolve under the output dir rather than next to the image.
    assert win.current_label_file_path() == str(saved_path)
    assert not win.has_label_file()

    win.save_labels(label_path=str(saved_path))
    assert saved_path.exists()

    assert win.current_label_file_path() == str(saved_path)
    assert win.has_label_file()

    monkeypatch.setattr(win, "_confirm_deletion", lambda *_args, **_kwargs: True)
    win.delete_file()
    qtbot.wait(50)

    assert not saved_path.exists()
    assert not image_adjacent_path.exists()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_current_label_file_path_prefers_opened_file(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    opened_path = data_path / "annotated/2011_000003.json"
    win = main_win(
        file_or_dir=str(opened_path),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    assert win.current_label_file_path() == str(opened_path)
    assert win.has_label_file()
    assert not (tmp_path / "2011_000003.json").exists()

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_undo_after_delete_file_does_not_restore_shapes(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated"),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    monkeypatch.setattr(win, "_confirm_deletion", lambda *_args, **_kwargs: True)

    # A prior shape edit in the same session enables the undo action.
    win._switch_canvas_mode(edit=True, create_mode=None)
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    win.delete_selected_shapes()
    qtbot.wait(50)
    assert canvas.can_restore_shape
    assert win._actions.undo.isEnabled()

    win.delete_file()
    qtbot.wait(50)
    assert canvas.shapes == []

    # Undo must not resurrect the annotations of the file removed from disk.
    assert not canvas.can_restore_shape
    assert not win._actions.undo.isEnabled()
    win.undo_shape_edit()
    assert canvas.shapes == []
    assert len(win._docks.label_list) == 0

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
