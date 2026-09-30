from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

import labelme._app
import labelme._save_writer
from labelme._app import MainWindow
from labelme._save_request import SaveRequest
from labelme._shape import Shape


@pytest.fixture
def blocked_writer(
    *, raw_win: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[threading.Event, threading.Event, list[SaveRequest]]]:
    entered = threading.Event()
    release = threading.Event()
    writes: list[SaveRequest] = []
    original = labelme._save_writer.write_save_request

    def write(request: SaveRequest, /) -> None:
        writes.append(request)
        if len(writes) == 1:
            entered.set()
            assert release.wait(5), "test did not release the writer"
        original(request)

    monkeypatch.setattr(labelme._save_writer, "write_save_request", write)

    monkeypatch.setattr(labelme._app, "write_save_request", write)
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
    blocked_writer: tuple[threading.Event, threading.Event, list[SaveRequest]],
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
    blocked_writer: tuple[threading.Event, threading.Event, list[SaveRequest]],
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
    attempts: list[SaveRequest] = []

    def fail(request: SaveRequest, /) -> None:
        attempts.append(request)
        raise PermissionError("read-only output")

    monkeypatch.setattr(labelme._save_writer, "write_save_request", fail)

    monkeypatch.setattr(labelme._app, "write_save_request", fail)
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


def test_retry_preserves_failed_save_as_destination(
    *,
    raw_win: MainWindow,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_win._actions.save_auto.setChecked(True)
    _edit(win=raw_win, x=1)
    qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
    old_path = Path(raw_win.current_label_file_path())
    destination = tmp_path / "renamed.json"
    original = labelme._save_writer.write_save_request

    def fail(_request: SaveRequest, /) -> None:
        raise PermissionError("read-only output")

    monkeypatch.setattr(raw_win, "prompt_save_file_path", lambda: str(destination))
    monkeypatch.setattr(raw_win, "show_error_message", lambda **_kwargs: 0)
    monkeypatch.setattr(labelme._save_writer, "write_save_request", fail)
    monkeypatch.setattr(labelme._app, "write_save_request", fail)
    raw_win._save_label_file(save_as=True)
    assert raw_win._status_bar.save.text() == "Save failed"
    monkeypatch.setattr(labelme._save_writer, "write_save_request", original)
    monkeypatch.setattr(labelme._app, "write_save_request", original)
    raw_win._status_bar.retry.click()
    qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
    _edit(win=raw_win, x=2)
    qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
    assert json.loads(destination.read_text())["shapes"][0]["points"][0][0] == 2
    assert json.loads(old_path.read_text())["shapes"][0]["points"][0][0] == 1


def test_edit_during_manual_retry_does_not_leave_saving_status(
    *,
    raw_win: MainWindow,
    qtbot: QtBot,
    blocked_writer: tuple[threading.Event, threading.Event, list[SaveRequest]],
) -> None:
    entered, release, _writes = blocked_writer
    raw_win._actions.save_auto.setChecked(False)
    _edit(win=raw_win, x=1)
    raw_win._show_save_failure(
        label_path=raw_win.current_label_file_path(),
        error=PermissionError("read-only output"),
    )
    raw_win._status_bar.retry.click()
    qtbot.waitUntil(entered.is_set)
    _edit(win=raw_win, x=2)
    release.set()
    qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
    assert raw_win._is_changed
    assert raw_win._status_bar.save.text() == "Unsaved changes"
    assert raw_win._status_bar.retry.isVisible()
    raw_win._status_bar.retry.click()
    qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
    assert not raw_win._is_changed


def test_output_directory_replaces_save_as_target_for_open_json(
    *,
    raw_win: MainWindow,
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_win._actions.save_auto.setChecked(True)
    _edit(win=raw_win, x=1)
    qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
    assert raw_win._load_file(image_or_label_path=raw_win.current_label_file_path())
    assert raw_win._file_list_image_path is None
    previous = tmp_path / "previous.json"
    monkeypatch.setattr(raw_win, "prompt_save_file_path", lambda: str(previous))
    raw_win._save_label_file(save_as=True)
    output = tmp_path / "other-output"
    output.mkdir()
    monkeypatch.setattr(
        QtWidgets.QFileDialog, "getExistingDirectory", lambda *_a, **_k: str(output)
    )
    raw_win.prompt_output_dir()
    _edit(win=raw_win, x=2)
    qtbot.waitUntil(lambda: not raw_win._save_writer.is_busy)
    assert Path(raw_win.current_label_file_path()).parent == output
    assert json.loads(previous.read_text())["shapes"][0]["points"][0][0] == 1


def test_manual_save_supersedes_pending_edits_and_marks_clean(
    *,
    raw_win: MainWindow,
    qtbot: QtBot,
    blocked_writer: tuple[threading.Event, threading.Event, list[SaveRequest]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release, _writes = blocked_writer
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *_a, **_k: QtWidgets.QMessageBox.StandardButton.Discard,
    )
    _edit(win=raw_win, x=1)
    qtbot.waitUntil(entered.is_set)
    _edit(win=raw_win, x=2)
    path = raw_win.current_label_file_path()
    QtCore.QTimer.singleShot(50, release.set)
    assert raw_win.save_labels(label_path=path)
    assert json.loads(Path(path).read_text())["shapes"][0]["points"][0][0] == 2
    assert not raw_win._is_changed
    assert not raw_win._save_writer.is_busy


def test_save_barrier_defers_completion_until_dialog_events_are_processed(
    *,
    raw_win: MainWindow,
    blocked_writer: tuple[threading.Event, threading.Event, list[SaveRequest]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release, _writes = blocked_writer
    _edit(win=raw_win, x=1)
    assert entered.wait(5)
    writer = raw_win._save_writer
    writer._timer.stop()
    assert writer._active is not None
    release.set()
    writer._active[2].result(timeout=5)

    class CompletingDialog(QtWidgets.QProgressDialog):
        def showEvent(self, event: QtGui.QShowEvent, /) -> None:
            super().showEvent(event)
            writer._poll()

        def exec(self) -> int:
            # Deliver completion while showing, before the nested event loop.
            # Inspect visibility instead of entering a loop that could hang.
            self.show()
            assert not writer.is_busy
            assert self.isVisible()
            QtCore.QCoreApplication.processEvents()
            assert not self.isVisible()
            return int(QtWidgets.QDialog.DialogCode.Accepted)

    monkeypatch.setattr(QtWidgets, "QProgressDialog", CompletingDialog)
    raw_win._wait_for_save()
    assert not raw_win._is_changed


def test_manual_save_waits_for_first_auto_save_before_choosing_path(
    *,
    raw_win: MainWindow,
    blocked_writer: tuple[threading.Event, threading.Event, list[SaveRequest]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release, writes = blocked_writer
    _edit(win=raw_win, x=1)
    assert entered.wait(5)
    assert raw_win._label_file_path is None

    def reject_prompt() -> str:
        pytest.fail("The first auto-save already has a destination")

    monkeypatch.setattr(raw_win, "prompt_save_file_path", reject_prompt)
    QtCore.QTimer.singleShot(50, release.set)
    raw_win._save_label_file(save_as=False)
    assert raw_win._label_file_path == writes[0].filename
    assert (
        json.loads(Path(writes[0].filename).read_text())["shapes"][0]["points"][0][0]
        == 1
    )
    assert not raw_win._is_changed
    assert not raw_win._save_writer.is_busy
