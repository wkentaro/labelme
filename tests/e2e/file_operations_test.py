from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata


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
def test_close_file_disables_clipboard_and_ai_controls(
    *, annotated_win: MainWindow, qtbot: QtBot, pause: bool
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    annotated_win._actions.copy.trigger()
    annotated_win._switch_canvas_mode(edit=False, create_mode="ai_points_to_shape")

    assert annotated_win._actions.paste.isEnabled()
    assert annotated_win._ai_annotation._body.isEnabled()

    annotated_win.close_file()

    assert not annotated_win._actions.paste.isEnabled()
    assert not annotated_win._actions.delete.isEnabled()
    assert not annotated_win._actions.edit_mode.isEnabled()
    assert not annotated_win._ai_annotation._body.isEnabled()
    assert not annotated_win._ai_text._body.isEnabled()
    assert canvas.shapes == []

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_close_file_clears_selection_so_same_image_can_reopen(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(file_or_dir=str(data_path / "annotated"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    file_list = win._docks.file_list
    assert file_list.currentRow() == 0

    win.close_file()

    assert file_list.currentRow() == -1
    item = file_list.item(0)
    qtbot.mouseClick(
        file_list.viewport(),
        Qt.MouseButton.LeftButton,
        pos=file_list.visualItemRect(item).center(),
    )
    qtbot.waitUntil(lambda: win._annotation is not None)
    assert file_list.currentRow() == 0
    assert win._canvas_widgets.canvas.isEnabled()
    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_save_as_is_available_for_flags_only_annotations(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "raw/2011_000003.jpg"),
        config_overrides={"auto_save": False, "flags": ["approved"]},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._docks.flag_list.item(0).setCheckState(Qt.CheckState.Checked)

    assert win.has_no_shapes()
    assert win._is_changed
    assert win._actions.save_as.isEnabled()

    win.mark_clean()
    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


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
    assert all(not action.isEnabled() for action in win._actions.on_shapes_present)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_label_file_resets_image_flags(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "annotated"),
        config_overrides={"flags": ["approved"]},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    flag = win._docks.flag_list.item(0)
    flag.setCheckState(Qt.CheckState.Checked)
    assert win._read_flag_dock_states() == {"approved": True}

    monkeypatch.setattr(win, "_confirm_deletion", lambda *_args, **_kwargs: True)
    win.delete_file()

    assert win._read_flag_dock_states() == {"approved": False}
    assert not win._is_changed

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


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
    assert not win._is_changed

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_label_file_tolerates_disappearance_after_confirmation(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    label_path = data_path / "annotated/2011_000003.json"
    win = main_win(file_or_dir=str(label_path))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    def remove_before_accepting(*_args: object, **_kwargs: object) -> bool:
        label_path.unlink()
        return True

    monkeypatch.setattr(win, "_confirm_deletion", remove_before_accepting)
    win.delete_file()

    assert win._canvas_widgets.canvas.shapes == []
    assert not win._actions.undo.isEnabled()
    assert not win._is_changed

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_label_file_reports_os_error_without_clearing_session(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    annotation_path = data_path / "annotated/2011_000003.json"
    win = main_win(file_or_dir=str(annotation_path))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    original_shapes = list(win._canvas_widgets.canvas.shapes)
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(win, "_confirm_deletion", lambda **_kwargs: True)
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda _path: (_ for _ in ()).throw(PermissionError("read-only")),
    )
    monkeypatch.setattr(
        win,
        "show_error_message",
        lambda *, title, message: errors.append((title, message)) or 0,
    )

    win.delete_file()

    assert errors == [
        (
            "Delete failed",
            f"Could not delete annotation file:\n{annotation_path}\n\nread-only",
        )
    ]
    assert win._canvas_widgets.canvas.shapes == original_shapes
    assert win._annotation is not None
    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
