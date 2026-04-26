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


def _zoom_until_overflow(canvas: Canvas) -> None:
    # Mutates canvas.scale directly to bypass the public zoom path because
    # this fixture only needs to force overflow; if the zoom pipeline gains
    # additional side effects relevant to a test, route through that instead.
    viewport = canvas._scroll_viewport()
    assert viewport is not None
    while not (
        canvas.pixmap.width() * canvas.scale > viewport.width()
        or canvas.pixmap.height() * canvas.scale > viewport.height()
    ):
        canvas.scale *= 1.5
        canvas.adjustSize()
        canvas.update()


@pytest.mark.gui
def test_middle_drag_emits_pan_request_with_widget_pixel_delta(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    _zoom_until_overflow(canvas=canvas)

    deltas: list[QPoint] = []
    canvas.pan_request.connect(deltas.append)

    start, end = _diagonal_drag_endpoints(canvas=canvas)
    drag_canvas(
        qtbot=qtbot,
        canvas=canvas,
        button=Qt.MiddleButton,
        start=start,
        end=end,
    )

    assert deltas, "pan_request was not emitted during middle-drag"
    total_x = sum(p.x() for p in deltas)
    total_y = sum(p.y() for p in deltas)
    assert total_x == _DRAG_OFFSET_PX
    assert total_y == _DRAG_OFFSET_PX

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)


@pytest.mark.gui
def test_middle_drag_no_pan_when_image_fits_viewport(
    qtbot: QtBot,
    annotated_win: MainWindow,
    pause: bool,
) -> None:
    canvas = annotated_win._canvas_widgets.canvas
    viewport = canvas._scroll_viewport()
    assert viewport is not None
    canvas.scale = (
        min(
            viewport.width() / canvas.pixmap.width(),
            viewport.height() / canvas.pixmap.height(),
        )
        * 0.5
    )
    canvas.adjustSize()
    canvas.update()

    start, end = _diagonal_drag_endpoints(canvas=canvas)

    with qtbot.assertNotEmitted(canvas.pan_request):
        drag_canvas(
            qtbot=qtbot,
            canvas=canvas,
            button=Qt.MiddleButton,
            start=start,
            end=end,
        )

    close_or_pause(qtbot=qtbot, widget=annotated_win, pause=pause)
