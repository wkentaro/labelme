from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata


@dataclass(frozen=True)
class _Paths:
    annotated_dir: Path
    next_image: Path
    save_path: Path
    new_output_dir: Path


@pytest.fixture()
def paths(data_path: Path, tmp_path: Path) -> _Paths:
    return _Paths(
        annotated_dir=data_path / "annotated",
        next_image=data_path / "raw" / "2011_000006.jpg",
        save_path=tmp_path / "saved.json",
        new_output_dir=tmp_path / "alt_output",
    )


@pytest.fixture()
def loaded_win(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> MainWindow:
    # All four scenarios need an image already loaded so the action methods
    # have a populated `_image_path` / `image_list` to work with.
    win = main_win(file_or_dir=str(data_path / "raw" / "2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win


def _open_file_dialog_return(paths: _Paths) -> tuple[str, str]:
    return (str(paths.next_image), "")


def _open_dir_dialog_return(paths: _Paths) -> str:
    return str(paths.annotated_dir)


def _save_file_dialog_return(paths: _Paths) -> tuple[str, str]:
    return (str(paths.save_path), "")


def _new_output_dir_dialog_return(paths: _Paths) -> str:
    paths.new_output_dir.mkdir(exist_ok=True)
    return str(paths.new_output_dir)


def _trigger_open_file(win: MainWindow) -> None:
    win._open_file_with_dialog()


def _trigger_open_dir(win: MainWindow) -> None:
    win._open_dir_with_dialog()


def _trigger_save_as(win: MainWindow) -> None:
    win._save_label_file(save_as=True)


def _trigger_change_output_dir(win: MainWindow) -> None:
    win.prompt_output_dir()


def _verify_open_file(win: MainWindow, paths: _Paths) -> bool:
    return (
        win._image_path is not None
        and Path(win._image_path).resolve() == paths.next_image.resolve()
    )


def _verify_open_dir(win: MainWindow, paths: _Paths) -> bool:
    return (
        win._docks.file_list.count() > 0
        and win._image_path is not None
        and Path(win._image_path).parent.resolve() == paths.annotated_dir.resolve()
    )


def _verify_save_as(_win: MainWindow, paths: _Paths) -> bool:
    return paths.save_path.exists()


def _verify_change_output_dir(win: MainWindow, paths: _Paths) -> bool:
    return win._output_dir == paths.new_output_dir


@pytest.mark.gui
@pytest.mark.parametrize(
    ("dialog_method", "dialog_return", "trigger", "verify"),
    [
        pytest.param(
            "getOpenFileName",
            _open_file_dialog_return,
            _trigger_open_file,
            _verify_open_file,
            id="open_file",
        ),
        pytest.param(
            "getExistingDirectory",
            _open_dir_dialog_return,
            _trigger_open_dir,
            _verify_open_dir,
            id="open_dir",
        ),
        pytest.param(
            "getSaveFileName",
            _save_file_dialog_return,
            _trigger_save_as,
            _verify_save_as,
            id="save_as",
        ),
        pytest.param(
            "getExistingDirectory",
            _new_output_dir_dialog_return,
            _trigger_change_output_dir,
            _verify_change_output_dir,
            id="change_output_dir",
        ),
    ],
)
def test_action_via_qfile_dialog(
    qtbot: QtBot,
    loaded_win: MainWindow,
    paths: _Paths,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
    dialog_method: str,
    dialog_return: Callable[[_Paths], tuple[str, str] | str],
    trigger: Callable[[MainWindow], None],
    verify: Callable[[MainWindow, _Paths], bool],
) -> None:
    monkeypatch.setattr(
        QtWidgets.QFileDialog,
        dialog_method,
        lambda *args, **kwargs: dialog_return(paths),
    )

    trigger(loaded_win)
    qtbot.wait(100)

    assert verify(loaded_win, paths)

    close_or_pause(qtbot=qtbot, widget=loaded_win, pause=pause)
