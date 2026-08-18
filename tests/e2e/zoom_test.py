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
_VIEWPORT_ZOOM: Final[int] = 300


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


def _set_scroll_bars_to_fraction(
    qtbot: QtBot,
    win: MainWindow,
    numerator: int,
    denominator: int,
) -> dict[Qt.Orientation, int]:
    scroll_bars = win._canvas_widgets.scroll_bars
    qtbot.waitUntil(lambda: all(bar.maximum() > 0 for bar in scroll_bars.values()))

    values: dict[Qt.Orientation, int] = {}
    for orientation, bar in scroll_bars.items():
        value = bar.maximum() * numerator // denominator
        assert value > 0
        bar.setValue(value)
        values[orientation] = value
    return values


def _wait_for_viewport(
    qtbot: QtBot,
    win: MainWindow,
    scroll_values: dict[Qt.Orientation, int],
) -> None:
    scroll_bars = win._canvas_widgets.scroll_bars
    qtbot.waitUntil(
        lambda: win._canvas_widgets.zoom_widget.value() == _VIEWPORT_ZOOM
        and all(
            scroll_bars[orientation].value() == expected
            for orientation, expected in scroll_values.items()
        )
    )
    assert win._canvas_widgets.zoom_widget.value() == _VIEWPORT_ZOOM
    for orientation, expected in scroll_values.items():
        assert scroll_bars[orientation].value() == expected


@pytest.fixture(name="scrolled_win")
def _make_scrolled_win(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
) -> tuple[MainWindow, dict[Qt.Orientation, int]]:
    win = main_win(
        file_or_dir=str(data_path / "raw/2011_000003.jpg"),
        config_overrides={"keep_prev_scale": True},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    win._set_zoom(value=_VIEWPORT_ZOOM)
    scroll_values = _set_scroll_bars_to_fraction(
        qtbot=qtbot,
        win=win,
        numerator=1,
        denominator=3,
    )
    return win, scroll_values


@pytest.mark.gui
@pytest.mark.parametrize("keep_prev_scale", [True, False])
def test_navigation_restores_each_image_viewport(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    keep_prev_scale: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "raw"),
        config_overrides={"keep_prev_scale": keep_prev_scale},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    win._set_zoom(value=_VIEWPORT_ZOOM)
    scroll_bars = win._canvas_widgets.scroll_bars
    first_scroll_values = _set_scroll_bars_to_fraction(
        qtbot=qtbot,
        win=win,
        numerator=1,
        denominator=3,
    )

    first_image_path = win._image_path
    assert first_image_path is not None
    win._open_next_image()
    qtbot.waitUntil(lambda: win._image_path != first_image_path)

    if keep_prev_scale:
        _wait_for_viewport(
            qtbot=qtbot,
            win=win,
            scroll_values=first_scroll_values,
        )
    else:
        qtbot.waitUntil(
            lambda: win._zoom_mode == _ZoomMode.FIT_WINDOW
            and all(bar.value() == bar.minimum() for bar in scroll_bars.values())
        )
        assert win._zoom_mode == _ZoomMode.FIT_WINDOW
        assert win._canvas_widgets.zoom_widget.value() != 300
        for bar in scroll_bars.values():
            assert bar.value() == bar.minimum()

    win._set_zoom(value=250)
    second_scroll_values = _set_scroll_bars_to_fraction(
        qtbot=qtbot,
        win=win,
        numerator=2,
        denominator=3,
    )
    assert second_scroll_values != first_scroll_values

    win._open_prev_image()
    qtbot.waitUntil(lambda: win._image_path == first_image_path)
    _wait_for_viewport(
        qtbot=qtbot,
        win=win,
        scroll_values=first_scroll_values,
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_open_file_keeps_previous_viewport(
    scrolled_win: tuple[MainWindow, dict[Qt.Orientation, int]],
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win, expected_scroll_values = scrolled_win
    next_image_path = str(data_path / "raw/2011_000006.jpg")

    win._load_from_file_or_dir(file_or_dir=next_image_path)
    qtbot.waitUntil(lambda: win._image_path == next_image_path)
    _wait_for_viewport(
        qtbot=qtbot,
        win=win,
        scroll_values=expected_scroll_values,
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_file_search_keeps_previous_viewport(
    scrolled_win: tuple[MainWindow, dict[Qt.Orientation, int]],
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win, expected_scroll_values = scrolled_win
    next_image_path = str(data_path / "raw/2011_000006.jpg")

    win._docks.file_search.setText("2011_000006")
    win._open_next_image()
    qtbot.waitUntil(lambda: win._image_path == next_image_path)
    _wait_for_viewport(
        qtbot=qtbot,
        win=win,
        scroll_values=expected_scroll_values,
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize("next_image_name", ["2011_000003.jpg", "2011_000006.jpg"])
def test_close_and_open_restores_viewport(
    scrolled_win: tuple[MainWindow, dict[Qt.Orientation, int]],
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    next_image_name: str,
) -> None:
    win, expected_scroll_values = scrolled_win
    next_image_path = str(data_path / "raw" / next_image_name)

    win.close_file()
    win._load_from_file_or_dir(file_or_dir=next_image_path)
    qtbot.waitUntil(lambda: win._image_path == next_image_path)
    _wait_for_viewport(
        qtbot=qtbot,
        win=win,
        scroll_values=expected_scroll_values,
    )

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


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
