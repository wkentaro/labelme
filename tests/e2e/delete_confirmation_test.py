from __future__ import annotations

from collections.abc import Callable

import pytest
from PySide6 import QtWidgets

from .conftest import MainWinFactory


def _exec_clicking_role(
    role: QtWidgets.QMessageBox.ButtonRole,
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
