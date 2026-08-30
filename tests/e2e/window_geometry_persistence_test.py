from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from PySide6.QtCore import QByteArray
from PySide6.QtCore import QPoint
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from labelme._app import WINDOW_LAYOUT_KEY
from labelme._app import WINDOW_POSITION_KEY
from labelme._app import WINDOW_SIZE_KEY

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import draw_and_commit_polygon
from .conftest import show_window_and_wait_for_imagedata

_RESIZE_W: Final[int] = 1100
_RESIZE_H: Final[int] = 800
_MOVE_X: Final[int] = 50
_MOVE_Y: Final[int] = 50
_TOLERANCE_PX: Final[int] = 10


@pytest.mark.gui
def test_window_geometry_persists_across_sessions(
    main_win: MainWinFactory,
    qtbot: QtBot,
    *,
    pause: bool,
) -> None:
    win1 = main_win(size=None)
    win1.show()
    qtbot.wait(100)

    win1.resize(_RESIZE_W, _RESIZE_H)
    win1.move(_MOVE_X, _MOVE_Y)
    qtbot.wait(100)

    saved_size = win1.size()
    saved_pos = win1.pos()

    win1.close()
    qtbot.wait(100)

    win2 = main_win(size=None)
    win2.show()
    qtbot.wait(100)

    restored_size = win2.size()
    restored_pos = win2.pos()

    assert abs(restored_size.width() - saved_size.width()) <= _TOLERANCE_PX
    assert abs(restored_size.height() - saved_size.height()) <= _TOLERANCE_PX
    assert abs(restored_pos.x() - saved_pos.x()) <= _TOLERANCE_PX
    assert abs(restored_pos.y() - saved_pos.y()) <= _TOLERANCE_PX

    close_or_pause(qtbot=qtbot, widget=win2, pause=pause)


@pytest.mark.gui
def test_cancelled_close_keeps_persisted_window_state(
    main_win: MainWinFactory,
    monkeypatch: pytest.MonkeyPatch,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    *,
    pause: bool,
) -> None:
    PERSISTED_SIZE: Final[QSize] = QSize(900, 700)
    PERSISTED_POSITION: Final[QPoint] = QPoint(10, 10)
    PERSISTED_STATE: Final[QByteArray] = QByteArray(b"dock-layout-of-the-last-close")
    VERTICES: Final = ((0.2, 0.2), (0.6, 0.2), (0.6, 0.6))

    win = main_win(
        file_or_dir=str(data_path / "raw/2011_000003.jpg"),
        config_overrides={"auto_save": False},
        output_dir=str(tmp_path),
        size=None,
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    win._window_state.setValue(WINDOW_SIZE_KEY, PERSISTED_SIZE)
    win._window_state.setValue(WINDOW_POSITION_KEY, PERSISTED_POSITION)
    win._window_state.setValue(WINDOW_LAYOUT_KEY, PERSISTED_STATE)

    win.resize(_RESIZE_W, _RESIZE_H)
    win.move(_MOVE_X, _MOVE_Y)
    qtbot.wait(100)
    assert win.size() != PERSISTED_SIZE
    assert win.pos() != PERSISTED_POSITION

    draw_and_commit_polygon(qtbot=qtbot, win=win, label="cat", vertices=VERTICES)

    prompt_shown = [False]

    def cancel_save_prompt(
        *_args: object, **_kwargs: object
    ) -> QMessageBox.StandardButton:
        prompt_shown[0] = True
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", cancel_save_prompt)

    win.close()

    assert prompt_shown[0]
    assert win.isVisible()
    assert win._window_state.value(WINDOW_SIZE_KEY) == PERSISTED_SIZE
    assert win._window_state.value(WINDOW_POSITION_KEY) == PERSISTED_POSITION
    assert win._window_state.value(WINDOW_LAYOUT_KEY) == PERSISTED_STATE

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
