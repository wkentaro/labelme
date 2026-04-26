from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from typing import Final

import pytest
from PyQt5.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import draw_and_commit_polygon
from .conftest import show_window_and_wait_for_imagedata

_OUTPUT_JSON_NAME: Final = "2011_000003.json"
_VERTICES: Final = ((0.2, 0.2), (0.6, 0.2), (0.6, 0.6))
_draw_and_commit_polygon = partial(draw_and_commit_polygon, vertices=_VERTICES)


def _is_dirty(*, win: MainWindow) -> bool:
    return win.windowTitle().endswith("*")


def _intercept_question(
    *,
    monkeypatch: pytest.MonkeyPatch,
    response: QMessageBox.StandardButton,
) -> list[bool]:
    prompt_shown = [False]

    def _fake(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        prompt_shown[0] = True
        return response

    monkeypatch.setattr(QMessageBox, "question", _fake)
    return prompt_shown


@pytest.fixture()
def _raw_win_no_autosave(raw_win: MainWindow) -> MainWindow:
    raw_win._actions.save_auto.setChecked(False)
    return raw_win


@pytest.fixture()
def _dir_win_no_autosave(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> MainWindow:
    win = main_win(
        file_or_dir=str(data_path / "raw"),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._actions.save_auto.setChecked(False)
    return win


@pytest.mark.gui
def test_close_with_unsaved_changes_cancel_keeps_window_open(
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    _raw_win_no_autosave: MainWindow,
    pause: bool,
) -> None:
    _draw_and_commit_polygon(qtbot=qtbot, win=_raw_win_no_autosave, label="cat")

    assert _is_dirty(win=_raw_win_no_autosave)

    prompt_shown = _intercept_question(
        monkeypatch=monkeypatch, response=QMessageBox.Cancel
    )

    _raw_win_no_autosave.close()

    assert prompt_shown[0]
    assert _raw_win_no_autosave.isVisible()
    assert _is_dirty(win=_raw_win_no_autosave)

    close_or_pause(qtbot=qtbot, widget=_raw_win_no_autosave, pause=pause)


@pytest.mark.gui
def test_close_choose_save_writes_json_and_closes(
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    _raw_win_no_autosave: MainWindow,
    tmp_path: Path,
) -> None:
    _draw_and_commit_polygon(qtbot=qtbot, win=_raw_win_no_autosave, label="cat")

    expected_json = tmp_path / _OUTPUT_JSON_NAME
    assert not expected_json.exists()

    _intercept_question(monkeypatch=monkeypatch, response=QMessageBox.Save)
    monkeypatch.setattr(
        _raw_win_no_autosave,
        "prompt_save_file_path",
        lambda: str(expected_json),
    )

    _raw_win_no_autosave.close()
    qtbot.waitUntil(lambda: not _raw_win_no_autosave.isVisible(), timeout=3000)

    assert expected_json.exists()
    saved = json.loads(expected_json.read_text())
    assert [shape["label"] for shape in saved["shapes"]] == ["cat"]


@pytest.mark.gui
def test_close_choose_discard_no_json_window_closes(
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    _raw_win_no_autosave: MainWindow,
    tmp_path: Path,
) -> None:
    _draw_and_commit_polygon(qtbot=qtbot, win=_raw_win_no_autosave, label="cat")

    expected_json = tmp_path / _OUTPUT_JSON_NAME
    assert not expected_json.exists()

    _intercept_question(monkeypatch=monkeypatch, response=QMessageBox.Discard)

    _raw_win_no_autosave.close()
    qtbot.waitUntil(lambda: not _raw_win_no_autosave.isVisible(), timeout=3000)

    assert not expected_json.exists()


@pytest.mark.gui
def test_navigate_with_unsaved_changes_shows_prompt(
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    _dir_win_no_autosave: MainWindow,
    pause: bool,
) -> None:
    _draw_and_commit_polygon(qtbot=qtbot, win=_dir_win_no_autosave, label="cat")
    assert _is_dirty(win=_dir_win_no_autosave)

    file_list = _dir_win_no_autosave._docks.file_list
    row_before = file_list.currentRow()

    prompt_shown = _intercept_question(
        monkeypatch=monkeypatch, response=QMessageBox.Discard
    )

    # _open_next_image does not call _can_continue itself; it bumps
    # file_list.setCurrentRow, which fires itemSelectionChanged ->
    # _file_list_item_selection_changed, and that is where the prompt is
    # triggered.
    _dir_win_no_autosave._open_next_image()

    qtbot.waitUntil(lambda: prompt_shown[0], timeout=3000)
    qtbot.waitUntil(lambda: not _is_dirty(win=_dir_win_no_autosave), timeout=3000)
    assert file_list.currentRow() == row_before + 1

    close_or_pause(qtbot=qtbot, widget=_dir_win_no_autosave, pause=pause)


@pytest.mark.gui
def test_close_clean_window_no_prompt(
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    _raw_win_no_autosave: MainWindow,
) -> None:
    assert not _is_dirty(win=_raw_win_no_autosave)

    prompt_shown = _intercept_question(
        monkeypatch=monkeypatch, response=QMessageBox.Discard
    )

    _raw_win_no_autosave.close()
    qtbot.waitUntil(lambda: not _raw_win_no_autosave.isVisible(), timeout=3000)

    assert not prompt_shown[0]
