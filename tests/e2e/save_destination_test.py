from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._app import _SaveTarget

from .conftest import MainWinFactory
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata

_STEM: Final = "2011_000003"


def _move_first_shape(*, qtbot: QtBot, win: MainWindow) -> None:
    canvas = win._canvas_widgets.canvas
    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)


def test_auto_save_writes_the_opened_file_not_the_image_named_one(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    # Issue #2967: other.json and 2011_000003.json both record the same Image.
    folder = data_path / "annotated"
    image_named = folder / f"{_STEM}.json"
    opened = folder / "other.json"
    shutil.copy(image_named, opened)
    image_named_before = image_named.read_bytes()
    opened_before = opened.read_bytes()

    win = main_win(file_or_dir=str(opened), config_overrides=dict(auto_save=True))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    _move_first_shape(qtbot=qtbot, win=win)

    # Read only after the save: opening the file while the worker replaces
    # it is a sharing violation on Windows.
    qtbot.waitUntil(lambda: not win._is_changed and not win._save_writer.is_busy)
    assert opened.read_bytes() != opened_before
    assert image_named.read_bytes() == image_named_before


def test_auto_save_writes_the_opened_file_when_its_image_is_elsewhere(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> None:
    # annotated_nested/annotations/x.json records ../images/x.jpg.
    nested = data_path / "annotated_nested"
    opened = nested / "annotations" / f"{_STEM}.json"
    beside_image = nested / "images" / f"{_STEM}.json"
    opened_before = opened.read_bytes()

    win = main_win(file_or_dir=str(opened), config_overrides=dict(auto_save=True))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    _move_first_shape(qtbot=qtbot, win=win)

    qtbot.waitUntil(lambda: not win._is_changed and not win._save_writer.is_busy)
    assert opened.read_bytes() != opened_before
    assert not beside_image.exists()


def test_auto_save_keeps_an_existing_annotation_folder_file(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    opened = data_path / "annotated" / f"{_STEM}.json"
    in_folder = output_dir / f"{_STEM}.json"
    shutil.copy(opened, in_folder)
    in_folder_before = in_folder.read_bytes()
    opened_before = opened.read_bytes()

    win = main_win(
        file_or_dir=str(opened),
        config_overrides=dict(auto_save=True),
        output_dir=str(output_dir),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    _move_first_shape(qtbot=qtbot, win=win)

    qtbot.waitUntil(lambda: not win._is_changed and not win._save_writer.is_busy)
    assert opened.read_bytes() != opened_before
    assert in_folder.read_bytes() == in_folder_before


def test_save_keeps_the_save_as_destination(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> None:
    opened = data_path / "annotated" / f"{_STEM}.json"
    opened_before = opened.read_bytes()
    chosen = tmp_path / "chosen.json"

    win = main_win(file_or_dir=str(opened), config_overrides=dict(auto_save=False))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    _move_first_shape(qtbot=qtbot, win=win)
    # Save As records its choice here before writing; a failed write leaves it.
    win._save_target = _SaveTarget(path=str(chosen), overwrite_confirmed=True)

    win._save_label_file(save_as=False)

    assert chosen.exists()
    assert opened.read_bytes() == opened_before


def test_auto_save_keeps_its_folder_copy_after_a_stale_completion(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    opened = data_path / "annotated" / f"{_STEM}.json"
    in_folder = output_dir / f"{_STEM}.json"
    opened_before = opened.read_bytes()

    win = main_win(
        file_or_dir=str(opened),
        config_overrides=dict(auto_save=True),
        output_dir=str(output_dir),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    # First edit starts the first copy into the Annotation Folder.
    _move_first_shape(qtbot=qtbot, win=win)
    # Second edit with Auto Save off, before the first save's completion is
    # handled: no event loop runs between these calls.
    win._actions.save_auto.setChecked(False)
    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)
    qtbot.waitUntil(lambda: not win._save_writer.is_busy)
    assert in_folder.exists()
    assert win._is_changed
    first_copy = in_folder.read_bytes()

    win._actions.save_auto.setChecked(True)
    qtbot.keyPress(canvas, Qt.Key.Key_Right)
    qtbot.keyRelease(canvas, Qt.Key.Key_Right)

    qtbot.waitUntil(lambda: not win._is_changed and not win._save_writer.is_busy)
    assert in_folder.read_bytes() != first_copy
    assert opened.read_bytes() == opened_before


def test_save_makes_the_first_copy_in_the_annotation_folder(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    opened = data_path / "annotated" / f"{_STEM}.json"
    in_folder = output_dir / f"{_STEM}.json"
    opened_before = opened.read_bytes()

    win = main_win(
        file_or_dir=str(opened),
        config_overrides=dict(auto_save=False),
        output_dir=str(output_dir),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    _move_first_shape(qtbot=qtbot, win=win)

    win._save_label_file(save_as=False)

    assert in_folder.exists()
    assert opened.read_bytes() == opened_before
    assert not win._is_changed
