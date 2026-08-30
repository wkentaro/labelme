from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

import labelme._app

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import draw_and_commit_polygon
from .conftest import show_window_and_wait_for_imagedata


@pytest.mark.gui
def test_file_search_filters_loaded_images_without_changing_active_annotation(
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    image_dir = data_path / "annotated_nested/images"
    annotation_dir = data_path / "annotated_nested/annotations"
    scan_calls: list[str] = []
    scan_image_files = labelme._app._scan_image_files

    def _track_scan_image_files(*, root_dir: str) -> list[str]:
        scan_calls.append(root_dir)
        return scan_image_files(root_dir=root_dir)

    monkeypatch.setattr(labelme._app, "_scan_image_files", _track_scan_image_files)

    win = main_win(
        file_or_dir=str(image_dir),
        config_overrides={"auto_save": False},
        output_dir=str(annotation_dir),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    all_image_paths = win.image_list[:]
    assert len(all_image_paths) == 3
    assert scan_calls == [str(image_dir)]

    draw_and_commit_polygon(
        qtbot=qtbot,
        win=win,
        label="cat",
        vertices=((0.2, 0.2), (0.6, 0.2), (0.6, 0.6)),
    )
    assert win.windowTitle().endswith("*")

    active_image_path = win._image_path
    active_annotation = win._annotation
    active_shape_ids = [id(shape) for shape in win._canvas_widgets.canvas.shapes]
    continue_checks: list[bool] = []
    load_calls: list[str] = []
    questions: list[bool] = []
    can_continue = win._can_continue
    load_file = win._load_file

    def _track_can_continue() -> bool:
        continue_checks.append(True)
        return can_continue()

    def _track_load_file(*, image_or_label_path: str) -> None:
        load_calls.append(image_or_label_path)
        load_file(image_or_label_path=image_or_label_path)

    def _track_question(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        questions.append(True)
        return QMessageBox.StandardButton.Discard

    monkeypatch.setattr(win, "_can_continue", _track_can_continue)
    monkeypatch.setattr(win, "_load_file", _track_load_file)
    monkeypatch.setattr(QMessageBox, "question", _track_question)

    win._docks.file_search.setText(r"2011_00000[6]\.jpg$")

    assert [Path(path).name for path in win.image_list] == ["2011_000006.jpg"]
    assert win._docks.file_list.currentItem() is None
    assert win._image_path == active_image_path
    assert win._annotation is active_annotation
    assert [
        id(shape) for shape in win._canvas_widgets.canvas.shapes
    ] == active_shape_ids
    assert win.windowTitle().endswith("*")
    assert scan_calls == [str(image_dir)]
    assert continue_checks == []
    assert load_calls == []
    assert questions == []

    win._docks.file_search.setText(r"JPG$")

    assert win.image_list == []
    assert win._image_path == active_image_path
    assert win._annotation is active_annotation
    assert scan_calls == [str(image_dir)]
    assert continue_checks == []
    assert load_calls == []
    assert questions == []

    win._docks.file_search.clear()

    assert win.image_list == all_image_paths
    current_item = win._docks.file_list.currentItem()
    assert current_item is not None
    assert current_item.text() == active_image_path
    assert win._image_path == active_image_path
    assert win._annotation is active_annotation
    assert [
        id(shape) for shape in win._canvas_widgets.canvas.shapes
    ] == active_shape_ids
    assert win.windowTitle().endswith("*")
    assert scan_calls == [str(image_dir)]
    assert continue_checks == []
    assert load_calls == []
    assert questions == []

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
