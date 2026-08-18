from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import select_shape
from .conftest import show_window_and_wait_for_imagedata


def _get_shape_list_labels(*, win: MainWindow) -> list[str]:
    return [item.text() for item in win._docks.label_list]


def _exec_clicking_role(
    role: QtWidgets.QMessageBox.ButtonRole,
    /,
) -> Callable[[QtWidgets.QMessageBox], int]:
    def _exec(msg_box: QtWidgets.QMessageBox) -> int:
        for button in msg_box.buttons():
            if msg_box.buttonRole(button) == role:
                button.click()
                return 0
        raise AssertionError(f"no button with role {role}")

    return _exec


@pytest.mark.gui
def test_confirm_deletion_defaults_to_cancel(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win()

    default_role: list[QtWidgets.QMessageBox.ButtonRole] = []

    def _capture_default(msg_box: QtWidgets.QMessageBox) -> int:
        default_role.append(msg_box.buttonRole(msg_box.defaultButton()))
        return 0

    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", _capture_default)

    win._confirm_deletion(message="delete?")

    assert default_role == [QtWidgets.QMessageBox.ButtonRole.RejectRole]


@pytest.mark.gui
def test_confirm_deletion_returns_true_when_delete_clicked(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win()

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "exec",
        _exec_clicking_role(QtWidgets.QMessageBox.ButtonRole.DestructiveRole),
    )

    assert win._confirm_deletion(message="delete?") is True


@pytest.mark.gui
def test_confirm_deletion_returns_false_when_cancel_clicked(
    *,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    win = main_win()

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "exec",
        _exec_clicking_role(QtWidgets.QMessageBox.ButtonRole.RejectRole),
    )

    assert win._confirm_deletion(message="delete?") is False


@pytest.mark.gui
def test_shape_deletion_warning_matches_working_undo(
    *,
    qtbot: QtBot,
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    ANNOTATED_FILE_NAME: Final[str] = "annotated/2011_000003.json"
    SHAPE_TIMEOUT_MS: Final[int] = 5_000

    # Auto-save is what makes the saved shape count observable without driving
    # a save action, and the untranslated source language is what makes the
    # warning assertions below independent of the developer's system locale.
    win = main_win(
        file_or_dir=str(data_path / ANNOTATED_FILE_NAME),
        config_overrides=dict(auto_save=True, language="en_US"),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    labels = [shape.label for shape in canvas.shapes]
    rows = _get_shape_list_labels(win=win)
    assert labels
    shape_count = len(labels)

    shown_messages: list[str] = []
    click_delete = _exec_clicking_role(QtWidgets.QMessageBox.ButtonRole.DestructiveRole)

    def _capture_then_delete(msg_box: QtWidgets.QMessageBox) -> int:
        shown_messages.append(msg_box.text())
        return click_delete(msg_box)

    monkeypatch.setattr(QtWidgets.QMessageBox, "exec", _capture_then_delete)

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    win._actions.delete.trigger()
    qtbot.waitUntil(
        lambda: len(canvas.shapes) == shape_count - 1, timeout=SHAPE_TIMEOUT_MS
    )

    assert len(shown_messages) == 1
    warning = shown_messages[0]
    assert "cannot be undone" not in warning
    assert "restore" in warning
    assert "Undo" in warning

    label_file = tmp_path / Path(ANNOTATED_FILE_NAME).name
    with open(label_file) as f:
        assert len(json.load(f)["shapes"]) == shape_count - 1

    # The warning promises Undo, which is only true when the action offering it
    # is enabled, so drive the action itself rather than its callback.
    assert win._actions.undo.isEnabled()
    win._actions.undo.trigger()
    qtbot.waitUntil(lambda: len(canvas.shapes) == shape_count, timeout=SHAPE_TIMEOUT_MS)

    assert [shape.label for shape in canvas.shapes] == labels
    assert _get_shape_list_labels(win=win) == rows
    with open(label_file) as f:
        assert len(json.load(f)["shapes"]) == shape_count

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
