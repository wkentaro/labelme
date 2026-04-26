from __future__ import annotations

from typing import Final

import pytest
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory

_RESIZE_W: Final[int] = 1100
_RESIZE_H: Final[int] = 800
_MOVE_X: Final[int] = 50
_MOVE_Y: Final[int] = 50
_TOLERANCE_PX: Final[int] = 10


@pytest.mark.gui
def test_window_geometry_persists_across_sessions(
    main_win: MainWinFactory,
    qtbot: QtBot,
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
