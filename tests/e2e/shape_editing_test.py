from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._widgets.canvas import Canvas

from ..conftest import assert_labelfile_sanity
from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata


def _open_and_select_shape(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    config_overrides: dict[str, bool] | None,
    output_dir: str | None,
) -> tuple[MainWindow, Canvas]:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        config_overrides=config_overrides,
        output_dir=output_dir,
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    assert len(canvas.shapes) == 5

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    return win, canvas


def _delete_selected_shape(
    *,
    win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
) -> None:
    monkeypatch.setattr(win, "_confirm_deletion", lambda *_args, **_kwargs: True)
    win.delete_selected_shapes()
    qtbot.wait(50)


@pytest.mark.gui
def test_select_shape(
    *,
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win, canvas = _open_and_select_shape(
        main_win=main_win,
        qtbot=qtbot,
        data_path=data_path,
        config_overrides=None,
        output_dir=None,
    )

    assert canvas.selected_shapes[0].label == "amber_kite"

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_copy_paste_shape(
    *,
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

    win._actions.copy.trigger()
    win._actions.paste.trigger()
    qtbot.wait(50)

    assert len(canvas.shapes) == num_shapes_before + 1
    assert canvas.shapes[-1].label == original_label

    win._save_label_file(save_as=False)
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_duplicate_shape(
    *,
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

    win._actions.duplicate.trigger()
    qtbot.wait(50)

    assert len(canvas.shapes) == num_shapes_before + 1

    win._save_label_file(save_as=False)
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_shape(
    *,
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

    win._save_label_file(save_as=False)
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_delete_undo_shape(
    *,
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

    win.undo_shape_edit()
    qtbot.wait(50)
    assert len(canvas.shapes) == 5
    assert canvas.shapes[0].label == "amber_kite"

    win._save_label_file(save_as=False)
    assert_labelfile_sanity(str(tmp_path / "2011_000003.json"))

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
