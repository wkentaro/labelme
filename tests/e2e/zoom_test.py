from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from PySide6 import QtGui
from PySide6.QtCore import QPoint
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._app import _ZoomMode

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata

_TEST_FILE_NAME: Final[str] = "annotated/2011_000003.json"


@pytest.fixture()
def _win(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> MainWindow:
    win = main_win(
        file_or_dir=str(data_path / _TEST_FILE_NAME),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win


@pytest.mark.gui
def test_zoom_fit_window(
    qtbot: QtBot,
    _win: MainWindow,
    pause: bool,
) -> None:
    _win.set_fit_window_mode(True)

    zoom_value = _win._canvas_widgets.zoom_widget.value()
    assert zoom_value != 100
    assert zoom_value > 0
    assert _win._zoom_mode == _ZoomMode.FIT_WINDOW

    close_or_pause(qtbot=qtbot, widget=_win, pause=pause)


@pytest.mark.gui
def test_zoom_fit_width(
    qtbot: QtBot,
    _win: MainWindow,
    pause: bool,
) -> None:
    _win.set_fit_window_mode(True)
    _win.set_fit_width_mode(True)

    fit_width_zoom = _win._canvas_widgets.zoom_widget.value()
    assert fit_width_zoom > 0
    assert _win._zoom_mode == _ZoomMode.FIT_WIDTH

    close_or_pause(qtbot=qtbot, widget=_win, pause=pause)


@pytest.mark.gui
def test_zoom_to_original(
    qtbot: QtBot,
    _win: MainWindow,
    pause: bool,
) -> None:
    _win.set_fit_window_mode(True)
    assert _win._canvas_widgets.zoom_widget.value() != 100

    _win._set_zoom_to_original()

    assert _win._canvas_widgets.zoom_widget.value() == 100
    assert _win._zoom_mode == _ZoomMode.MANUAL_ZOOM

    close_or_pause(qtbot=qtbot, widget=_win, pause=pause)


@pytest.mark.gui
def test_zoom_step_keeps_fractional_precision(
    qtbot: QtBot,
    _win: MainWindow,
    pause: bool,
) -> None:
    _win._canvas_widgets.zoom_widget.setValue(105)
    _win._add_zoom(increment=1.1)
    # 105 * 1.1 = 115.5; the old integer widget clamped this up to 116.
    assert _win._canvas_widgets.zoom_widget.value() == pytest.approx(115.5)

    close_or_pause(qtbot=qtbot, widget=_win, pause=pause)


def _make_wheel_event(
    pos: QPointF,
    angle_delta: QPoint,
    modifiers: Qt.KeyboardModifier,
) -> QtGui.QWheelEvent:
    # PySide6's QWheelEvent constructor takes positional args;
    # the 8-arg form matches the modern Qt6 signature.
    return QtGui.QWheelEvent(
        pos,
        pos,
        QPoint(0, 0),
        angle_delta,
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


@pytest.mark.gui
@pytest.mark.parametrize(
    ("modifiers", "angle_delta", "signal_attr", "expected_orientation"),
    [
        pytest.param(
            Qt.KeyboardModifier.ControlModifier,
            QPoint(0, 120),
            "zoom_request",
            None,
            id="ctrl_zoom",
        ),
        pytest.param(
            Qt.KeyboardModifier.NoModifier,
            QPoint(0, 120),
            "scroll_request",
            Qt.Orientation.Vertical,
            id="plain_scroll",
        ),
        pytest.param(
            Qt.KeyboardModifier.ShiftModifier,
            QPoint(0, 120),
            "scroll_request",
            Qt.Orientation.Horizontal,
            id="shift_horizontal_scroll",
        ),
    ],
)
def test_canvas_wheel_event_dispatches_signal(
    qtbot: QtBot,
    _win: MainWindow,
    pause: bool,
    modifiers: Qt.KeyboardModifier,
    angle_delta: QPoint,
    signal_attr: str,
    expected_orientation: Qt.Orientation | None,
) -> None:
    canvas = _win._canvas_widgets.canvas
    captured: list[tuple[object, ...]] = []
    signal = getattr(canvas, signal_attr)
    signal.connect(lambda *args: captured.append(args))

    canvas.wheelEvent(
        _make_wheel_event(
            pos=QPointF(canvas.width() / 2, canvas.height() / 2),
            angle_delta=angle_delta,
            modifiers=modifiers,
        )
    )

    assert captured, f"{signal_attr} was not emitted"
    if expected_orientation is not None:
        # The plain-scroll branch emits an empty horizontal step (delta.x() == 0)
        # before the real vertical one, so filter to non-zero deltas. There must
        # be exactly one non-zero emission, on the expected axis, carrying the
        # full angle_delta.y(). Anything looser would silently pass if the
        # canvas dropped the real emission and only kept the zero step.
        non_zero = [args for args in captured if args[0] != 0]
        assert len(non_zero) == 1, (
            f"{signal_attr} expected exactly one non-zero emission, got {non_zero!r}"
        )
        assert non_zero[0] == (angle_delta.y(), expected_orientation)

    close_or_pause(qtbot=qtbot, widget=_win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize(
    "config_overrides",
    [
        None,
        {"shortcuts": {"zoom_out": ["Ctrl+-", "Ctrl+_"]}},
        {"shortcuts": {"zoom_in": None}},
        {"shortcuts": {"zoom_in": ["Z", "Ctrl+Z"]}},
    ],
)
def test_zoom_widget_whats_this_renders_shortcuts_cleanly(
    qtbot: QtBot,
    main_win: MainWinFactory,
    pause: bool,
    config_overrides: dict | None,
) -> None:
    win = main_win(config_overrides=config_overrides)

    whats_this = win._canvas_widgets.zoom_widget.whatsThis()

    assert "also work on the canvas" in whats_this
    assert "[" not in whats_this
    assert "'" not in whats_this

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
