from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow
from labelme.widgets.canvas import Canvas

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata


def _open_and_select_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    shape_index: int = 0,
    config_overrides: dict[str, bool] | None = None,
    output_dir: str | None = None,
) -> tuple[MainWindow, Canvas]:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides=config_overrides,
        output_dir=output_dir,
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    assert len(canvas.shapes) == 5

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=shape_index)
    return win, canvas


def _delete_selected_shape(
    win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
) -> None:
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "warning",
        lambda *args, **kwargs: QtWidgets.QMessageBox.Yes,
    )
    win.deleteSelectedShape()
    qtbot.wait(50)


@pytest.mark.gui
def test_select_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win, canvas = _open_and_select_shape(
        main_win=main_win, qtbot=qtbot, data_path=data_path
    )

    assert canvas.selected_shapes[0].label == "person"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_copy_paste_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win, canvas = _open_and_select_shape(
        main_win=main_win,
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )

    original_label = canvas.selected_shapes[0].label
    num_shapes_before = len(canvas.shapes)

    win.copySelectedShape()
    win.pasteSelectedShape()
    qtbot.wait(50)

    assert len(canvas.shapes) == num_shapes_before + 1
    assert canvas.shapes[-1].label == original_label

    win._save_label_file()
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_duplicate_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    win, canvas = _open_and_select_shape(
        main_win=main_win,
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )

    num_shapes_before = len(canvas.shapes)

    win.duplicateSelectedShape()
    qtbot.wait(50)

    assert len(canvas.shapes) == num_shapes_before + 1

    win._save_label_file()
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win, canvas = _open_and_select_shape(
        main_win=main_win,
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )

    _delete_selected_shape(win=win, monkeypatch=monkeypatch, qtbot=qtbot)

    assert len(canvas.shapes) == 4

    win._save_label_file()
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_undo_shape(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    win, canvas = _open_and_select_shape(
        main_win=main_win,
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=dict(auto_save=True),
        output_dir=str(tmp_path),
    )

    _delete_selected_shape(win=win, monkeypatch=monkeypatch, qtbot=qtbot)
    assert len(canvas.shapes) == 4

    win.undoShapeEdit()
    qtbot.wait(50)
    assert len(canvas.shapes) == 5
    assert canvas.shapes[0].label == "person"

    win._save_label_file()
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
