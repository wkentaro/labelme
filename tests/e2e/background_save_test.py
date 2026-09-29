from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from PySide6 import QtCore
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._save_snapshot import SaveSnapshot
from labelme._shape import Shape


@pytest.fixture
def blocked_writer(
    *, raw_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[threading.Event, threading.Event, list[SaveSnapshot]]]:
    entered = threading.Event()
    release = threading.Event()
    writes: list[SaveSnapshot] = []
    original = SaveSnapshot.write

    def write(snapshot: SaveSnapshot, /) -> None:
        writes.append(snapshot)
        if len(writes) == 1:
            entered.set()
            assert release.wait(5), "test did not release the writer"
        original(snapshot)

    monkeypatch.setattr(SaveSnapshot, "write", write)
    raw_win._actions.save_auto.setChecked(True)
    yield entered, release, writes
    release.set()
    raw_win._wait_for_save()


def _edit(*, win: MainWindow, x: float) -> None:
    win._commit_shapes(
        [Shape(label="object", points=np.array([[x, 10], [20, 10], [20, 20]]))]
    )


def test_background_save_coalesces_and_keeps_newer_edits_dirty(
    *,
    raw_win: MainWindow,
    blocked_writer: tuple[threading.Event, threading.Event, list[SaveSnapshot]],
    qtbot: QtBot,
) -> None:
    entered, release, writes = blocked_writer
    _edit(win=raw_win, x=1)
    qtbot.waitUntil(entered.is_set)
    assert raw_win._is_changed
    assert raw_win._status_bar.save.text() == "Saving…"
    _edit(win=raw_win, x=2)
    _edit(win=raw_win, x=3)
    states: list[bool] = []
    raw_win._save_writer.finished.connect(
        lambda *_args: states.append(raw_win._is_changed)
    )
    release.set()
    qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
    assert states == [True, False]
    assert [s.annotation.shapes[0]["points"][0][0] for s in writes] == [1, 3]
    assert raw_win._status_bar.save.text() == "Saved"
    assert raw_win._canvas_widgets.canvas.can_restore_shape
    with open(writes[-1].filename) as f:
        assert json.load(f)["shapes"][0]["points"][0][0] == 3


@pytest.mark.parametrize(
    "action", ["save_as", "delete", "close_file", "close", "output_dir"]
)
def test_transitions_wait_for_active_writer(
    *,
    raw_win: MainWindow,
    blocked_writer: tuple[threading.Event, threading.Event, list[SaveSnapshot]],
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    entered, release, writes = blocked_writer
    _edit(win=raw_win, x=1)
    qtbot.waitUntil(entered.is_set)
    _edit(win=raw_win, x=2)
    old_path = Path(writes[0].filename)
    new_path = tmp_path / "save-as.json"
    QtCore.QTimer.singleShot(50, release.set)
    if action == "save_as":
        monkeypatch.setattr(raw_win, "prompt_save_file_path", lambda: str(new_path))
        raw_win._save_label_file(save_as=True)
        _edit(win=raw_win, x=3)
        qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
        assert writes[-1].filename == str(new_path)
        assert json.loads(new_path.read_text())["shapes"][0]["points"][0][0] == 3
    elif action == "delete":
        monkeypatch.setattr(raw_win, "_confirm_deletion", lambda **_kwargs: True)
        raw_win.delete_file()
        assert not old_path.exists()
        assert not raw_win._canvas_widgets.canvas.shapes
        qtbot.wait(30)
        assert not old_path.exists()
    elif action == "close_file":
        raw_win.close_file()
        assert raw_win._image_path is None
        assert json.loads(old_path.read_text())["shapes"][0]["points"][0][0] == 2
    elif action == "close":
        raw_win.close()
        assert not raw_win.isVisible()
        assert json.loads(old_path.read_text())["shapes"][0]["points"][0][0] == 2
    else:
        output = tmp_path / "new-output"
        output.mkdir()
        monkeypatch.setattr(
            QtWidgets.QFileDialog, "getExistingDirectory", lambda *_a, **_k: str(output)
        )
        raw_win.prompt_output_dir()
        assert raw_win._output_dir == output
        assert json.loads(old_path.read_text())["shapes"][0]["points"][0][0] == 2
    assert not raw_win._save_writer.is_busy


def test_failed_background_save_retries_only_on_request_or_edit(
    *,
    raw_win: MainWindow,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[SaveSnapshot] = []

    def fail(snapshot: SaveSnapshot, /) -> None:
        attempts.append(snapshot)
        raise PermissionError("read-only output")

    monkeypatch.setattr(SaveSnapshot, "write", fail)
    raw_win._actions.save_auto.setChecked(True)
    _edit(win=raw_win, x=1)
    qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
    assert raw_win._is_changed
    assert raw_win._status_bar.save.text() == "Save failed"
    qtbot.wait(50)
    assert len(attempts) == 1
    raw_win._status_bar.retry.click()
    qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
    assert len(attempts) == 2
    _edit(win=raw_win, x=2)
    qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
    assert len(attempts) == 3
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *_a, **_k: QtWidgets.QMessageBox.StandardButton.Cancel,
    )
    assert not raw_win._can_continue()
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *_a, **_k: QtWidgets.QMessageBox.StandardButton.Discard,
    )
    assert raw_win._can_continue()
