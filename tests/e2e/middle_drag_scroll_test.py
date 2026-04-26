from __future__ import annotations

from typing import Final

import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow
from labelme.widgets.canvas import Canvas

from ..conftest import close_or_pause
from .conftest import drag_canvas

_DRAG_OFFSET_PX: Final[int] = 40


def _diagonal_drag_endpoints(canvas: Canvas) -> tuple[QPoint, QPoint]:
    start = QPoint(canvas.width() // 2, canvas.height() // 2)
    end = QPoint(start.x() + _DRAG_OFFSET_PX, start.y() + _DRAG_OFFSET_PX)
    return start, end


@pytest.mark.gui
def test_middle_drag_emits_scroll_request(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    canvas.enable_dragging(enabled=True)

    horizontal: list[int] = []
    vertical: list[int] = []

    def _on_scroll(delta: int, orientation: Qt.Orientation) -> None:
        if orientation == Qt.Horizontal:
            horizontal.append(delta)
        else:
            vertical.append(delta)

    canvas.scroll_request.connect(_on_scroll)

    start, end = _diagonal_drag_endpoints(canvas=canvas)
    drag_canvas(
        qtbot=qtbot,
        canvas=canvas,
        button=Qt.MiddleButton,
        start=start,
        end=end,
    )

    assert any(d != 0 for d in horizontal)
    assert any(d != 0 for d in vertical)

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_middle_drag_disabled_is_noop(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    canvas.enable_dragging(enabled=False)

    start, end = _diagonal_drag_endpoints(canvas=canvas)

    with qtbot.assertNotEmitted(canvas.scroll_request):
        drag_canvas(
            qtbot=qtbot,
            canvas=canvas,
            button=Qt.MiddleButton,
            start=start,
            end=end,
        )

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)
