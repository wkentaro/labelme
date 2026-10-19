from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


def _checked(win: MainWindow, /) -> list[bool]:
    file_list = win._docks.file_list
    return [
        file_list.item(i).checkState() == Qt.CheckState.Checked
        for i in range(file_list.count())
    ]


def _save_as(
    *, win: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, path: Path
) -> None:
    monkeypatch.setattr(win, "prompt_save_file_path", lambda: str(path))
    win._save_label_file(save_as=True)
    qtbot.waitUntil(path.exists)


def _delete(*, win: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(win, "_confirm_deletion", lambda **_kwargs: True)
    win.delete_file()


@pytest.mark.gui
def test_save_as_onto_another_images_annotation_file_does_not_claim_that_image(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    other = out / "2011_000006.json"
    win = main_win(file_or_dir=data_path / "raw", output_dir=out)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    _save_as(win=win, qtbot=qtbot, monkeypatch=monkeypatch, path=other)
    assert _checked(win) == [False, False, False]
    win._docks.file_list.setCurrentRow(1)
    qtbot.waitUntil(
        lambda: win._file_list_image_path == str(data_path / "raw/2011_000006.jpg")
    )
    assert win._image_path == str(data_path / "raw/2011_000006.jpg")
    assert win._canvas_widgets.canvas.shapes == []
    # Return to the explicitly saved source before deleting its Save As copy.
    win._load_file(image_or_label_path=str(other))

    _delete(win=win, monkeypatch=monkeypatch)
    assert not other.exists()
    assert _checked(win) == [False, False, False]


@pytest.mark.gui
def test_save_as_outside_the_annotation_folder_checks_nothing(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    win = main_win(file_or_dir=data_path / "raw", output_dir=out)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    _save_as(win=win, qtbot=qtbot, monkeypatch=monkeypatch, path=tmp_path / "copy.json")
    assert _checked(win) == [False, False, False]


@pytest.mark.gui
def test_deleting_a_save_as_copy_keeps_the_images_checkmark(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    images = tmp_path / "images"
    shutil.copytree(data_path / "annotated", images)
    copy = tmp_path / "copy.json"
    win = main_win(file_or_dir=images)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    _save_as(win=win, qtbot=qtbot, monkeypatch=monkeypatch, path=copy)

    _delete(win=win, monkeypatch=monkeypatch)
    assert not copy.exists()
    assert _checked(win) == [True, True, True]


@pytest.mark.gui
@pytest.mark.skipif(os.name == "nt", reason="directory symlinks require privileges")
def test_save_through_a_symlinked_annotation_folder_checks_the_image(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    saved = real / "2011_000006.json"
    win = main_win(file_or_dir=data_path / "raw", output_dir=link)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._docks.file_list.setCurrentRow(1)
    qtbot.waitUntil(
        lambda: win._file_list_image_path == str(data_path / "raw/2011_000006.jpg")
    )

    _save_as(win=win, qtbot=qtbot, monkeypatch=monkeypatch, path=saved)
    assert _checked(win) == [False, True, False]

    _delete(win=win, monkeypatch=monkeypatch)
    assert not saved.exists()
    assert _checked(win) == [False, False, False]


@pytest.mark.gui
def test_save_whose_name_differs_only_in_case_checks_the_image(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "probe").touch()
    if not (out / "PROBE").exists():
        pytest.skip("needs a case-insensitive filesystem")
    (out / "probe").unlink()
    saved = out / "2011_000006.JSON"
    win = main_win(file_or_dir=data_path / "raw", output_dir=out)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._docks.file_list.setCurrentRow(1)
    qtbot.waitUntil(
        lambda: win._file_list_image_path == str(data_path / "raw/2011_000006.jpg")
    )

    _save_as(win=win, qtbot=qtbot, monkeypatch=monkeypatch, path=saved)
    assert _checked(win) == [False, True, False]

    _delete(win=win, monkeypatch=monkeypatch)
    assert _checked(win) == [False, False, False]


@pytest.mark.gui
@pytest.mark.parametrize(
    ("image_name", "saved_name"),
    [("..jpg", "..json"), ("café.jpg", "café.json")],
    ids=["dot-stem", "unicode-form"],
)
def test_save_onto_the_annotation_file_of_an_unusual_name_checks_it(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    image_name: str,
    saved_name: str,
) -> None:
    images = tmp_path / "images"
    images.mkdir()
    shutil.copy(data_path / "raw" / "2011_000003.jpg", images / "a.jpg")
    shutil.copy(data_path / "raw" / "2011_000003.jpg", images / image_name)
    saved = images / saved_name
    saved.touch()
    if not (images / f"{Path(image_name).stem}.json").exists():
        pytest.skip("needs a filesystem that treats both names as one")
    saved.unlink()
    win = main_win(file_or_dir=images)
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    for row in range(win._docks.file_list.count()):
        if win._docks.file_list.item(row).data(Qt.ItemDataRole.UserRole) == str(
            images / image_name
        ):
            win._docks.file_list.setCurrentRow(row)
            break
    qtbot.waitUntil(lambda: win._file_list_image_path == str(images / image_name))
    assert _checked(win) == [False, False]

    _save_as(win=win, qtbot=qtbot, monkeypatch=monkeypatch, path=saved)
    assert sorted(_checked(win)) == [False, True]
