from __future__ import annotations

from typing import Final

import pytest
from PyQt5.QtCore import QPointF
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow
from labelme.widgets.label_dialog import LabelDialog

from ..conftest import close_or_pause
from .conftest import draw_triangle
from .conftest import schedule_on_dialog
from .conftest import select_shape
from .conftest import submit_label_dialog

_SHAPE_TIMEOUT_MS: Final[int] = 5_000


def _schedule_capture_then_cancel(
    label_dialog: LabelDialog,
    captured: list[str],
) -> None:
    def _action() -> None:
        captured.append(label_dialog.edit.text())
        label_dialog.reject()

    schedule_on_dialog(label_dialog=label_dialog, action=_action)


def _draw_triangle(qtbot: QtBot, win: MainWindow) -> None:
    draw_triangle(
        qtbot=qtbot,
        win=win,
        vertices=((0.2, 0.2), (0.6, 0.2), (0.6, 0.6)),
    )


def _draw_and_commit_polygon(qtbot: QtBot, win: MainWindow, label: str) -> None:
    canvas = win._canvas_widgets.canvas
    _draw_triangle(qtbot=qtbot, win=win)
    # Schedule the dialog handler before pressing Return: the Return key closes
    # the polygon which opens the dialog, at which point the queued poller fills
    # it in. Swapping these two lines would deadlock the test.
    submit_label_dialog(qtbot=qtbot, label_dialog=win._label_dialog, label=label)
    qtbot.keyPress(canvas, Qt.Key_Return)

    def shape_committed() -> None:
        assert any(s.label == label for s in canvas.shapes)

    qtbot.waitUntil(shape_committed, timeout=_SHAPE_TIMEOUT_MS)


@pytest.mark.gui
def test_last_label_memo(
    qtbot: QtBot,
    raw_win: MainWindow,
    pause: bool,
) -> None:
    canvas = raw_win._canvas_widgets.canvas
    label_dialog = raw_win._label_dialog

    _draw_and_commit_polygon(qtbot=qtbot, win=raw_win, label="foo")

    captured: list[str] = []
    _schedule_capture_then_cancel(label_dialog=label_dialog, captured=captured)

    _draw_triangle(qtbot=qtbot, win=raw_win)
    qtbot.keyPress(canvas, Qt.Key_Return)

    qtbot.waitUntil(lambda: bool(captured), timeout=_SHAPE_TIMEOUT_MS)

    assert captured[0] == "foo"

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)


@pytest.mark.gui
def test_restore_last_shape_via_undo(
    qtbot: QtBot,
    raw_win: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
) -> None:
    canvas = raw_win._canvas_widgets.canvas

    _draw_and_commit_polygon(qtbot=qtbot, win=raw_win, label="restore_me")
    raw_win._switch_canvas_mode(edit=True)

    assert len(canvas.shapes) == 1
    original_points = [QPointF(p) for p in canvas.shapes[0].points]

    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.Yes,
    )

    select_shape(qtbot=qtbot, canvas=canvas, shape_index=0)
    raw_win.delete_selected_shapes()
    qtbot.waitUntil(lambda: len(canvas.shapes) == 0, timeout=_SHAPE_TIMEOUT_MS)

    raw_win.undo_shape_edit()
    qtbot.waitUntil(lambda: len(canvas.shapes) == 1, timeout=_SHAPE_TIMEOUT_MS)

    restored = canvas.shapes[0]
    assert restored.label == "restore_me"
    assert [QPointF(p) for p in restored.points] == original_points

    close_or_pause(qtbot=qtbot, widget=raw_win, pause=pause)
