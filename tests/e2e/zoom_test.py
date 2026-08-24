from __future__ import annotations

import math
from pathlib import Path
from typing import Final

import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import QPoint
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from labelme._app import MainWindow
from labelme._app import _ZoomMode

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import image_to_widget_pos
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
def test_zoom_fit_width_does_not_scroll_horizontally(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
) -> None:
    image_path = tmp_path / "portrait.png"
    image = QtGui.QImage(2076, 3000, QtGui.QImage.Format.Format_RGB32)
    image.fill(0)
    assert image.save(str(image_path))
    win = main_win(file_or_dir=str(image_path))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    win.set_fit_width_mode(True)
    scroll_bars = win._canvas_widgets.scroll_bars
    qtbot.waitUntil(
        lambda: scroll_bars[Qt.Orientation.Vertical].maximum() > 0
        and scroll_bars[Qt.Orientation.Horizontal].maximum() == 0
    )
    assert scroll_bars[Qt.Orientation.Horizontal].maximum() == 0

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_fit_width_uses_full_width_when_quantized_image_fits_height(
    qtbot: QtBot,
    _win: MainWindow,
    pause: bool,
) -> None:
    scroll_area = _win.centralWidget()
    assert isinstance(scroll_area, QtWidgets.QScrollArea)
    viewport_size = scroll_area.maximumViewportSize()
    zoom_widget = _win._canvas_widgets.zoom_widget
    precision = 10 ** zoom_widget.decimals()
    image_width = viewport_size.width() + 1
    expected_percent = (
        math.floor(viewport_size.width() / image_width * 100 * precision) / precision
    )
    expected_scale = expected_percent / 100
    image_height = math.floor(viewport_size.height() / expected_scale) + 1
    image = QtGui.QImage(
        image_width,
        image_height,
        QtGui.QImage.Format.Format_RGB32,
    )
    image.fill(0)
    _win._image = image
    _win._canvas_widgets.canvas.load_pixmap(QtGui.QPixmap.fromImage(image))

    _win.set_fit_width_mode(True)

    assert image_height * expected_scale > viewport_size.height()
    assert int(image_height * expected_scale) == viewport_size.height()
    assert zoom_widget.value() == expected_percent
    assert all(bar.maximum() == 0 for bar in _win._canvas_widgets.scroll_bars.values())

    close_or_pause(qtbot=qtbot, widget=_win, pause=pause)


@pytest.mark.gui
def test_manual_zoom_only_scrolls_the_overflowing_axis(
    qtbot: QtBot,
    _win: MainWindow,
    pause: bool,
) -> None:
    _win._set_zoom_to_original()
    _win._set_zoom(value=110)

    scroll_bars = _win._canvas_widgets.scroll_bars
    qtbot.waitUntil(
        lambda: scroll_bars[Qt.Orientation.Horizontal].maximum() > 0
        and scroll_bars[Qt.Orientation.Vertical].maximum() == 0
    )
    assert scroll_bars[Qt.Orientation.Vertical].maximum() == 0

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

    canvas = win._canvas_widgets.canvas
    win._set_zoom(value=_VIEWPORT_ZOOM)
    scroll_bars = win._canvas_widgets.scroll_bars
    first_scroll_values = _set_scroll_bars_to_fraction(
        qtbot=qtbot,
        win=win,
        numerator=1,
        denominator=3,
    )
    canvas.pan_view(step=QPointF(17, 23))
    first_view_offset = canvas.get_view_offset()

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
        assert canvas.get_view_offset() == first_view_offset
    else:
        qtbot.waitUntil(
            lambda: win._zoom_mode == _ZoomMode.FIT_WINDOW
            and all(bar.value() == bar.minimum() for bar in scroll_bars.values())
        )
        assert win._zoom_mode == _ZoomMode.FIT_WINDOW
        assert win._canvas_widgets.zoom_widget.value() != 300
        for bar in scroll_bars.values():
            assert bar.value() == bar.minimum()
        assert canvas.get_view_offset().isNull()

    win._set_zoom(value=250)
    second_scroll_values = _set_scroll_bars_to_fraction(
        qtbot=qtbot,
        win=win,
        numerator=2,
        denominator=3,
    )
    canvas.pan_view(step=QPointF(-31, -19))
    assert second_scroll_values != first_scroll_values
    assert canvas.get_view_offset() != first_view_offset

    win._open_prev_image()
    qtbot.waitUntil(lambda: win._image_path == first_image_path)
    _wait_for_viewport(
        qtbot=qtbot,
        win=win,
        scroll_values=first_scroll_values,
    )
    assert canvas.get_view_offset() == first_view_offset

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_navigation_restores_view_offset_with_retained_brightness(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / "raw"),
        config_overrides={
            "keep_prev_scale": True,
            "keep_prev_brightness_contrast": True,
        },
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    canvas = win._canvas_widgets.canvas
    canvas.pan_view(step=QPointF(17, 23))
    expected_view_offset = canvas.get_view_offset()
    first_image_path = win._image_path
    assert first_image_path is not None
    win._brightness_contrast_values[first_image_path] = (75, 50)

    win._open_next_image()
    qtbot.waitUntil(lambda: win._image_path != first_image_path)

    assert canvas.get_view_offset() == expected_view_offset

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_navigation_restores_viewport_after_layout_settles(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
) -> None:
    for name, size in [("a.png", (1000, 1500)), ("b.png", (1200, 800))]:
        image = QtGui.QImage(*size, QtGui.QImage.Format.Format_RGB32)
        image.fill(0)
        assert image.save(str(tmp_path / name))
    win = main_win(
        file_or_dir=str(tmp_path),
        config_overrides={"keep_prev_scale": True},
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    win.set_fit_width_mode(True)
    v_bar = win._canvas_widgets.scroll_bars[Qt.Orientation.Vertical]
    qtbot.waitUntil(lambda: v_bar.maximum() > 0)
    v_bar.setValue(v_bar.maximum() * 2 // 3)
    with qtbot.waitSignal(v_bar.rangeChanged):
        win._add_zoom(increment=0.9)

    first_image_path = win._image_path
    assert first_image_path is not None
    expected_scroll_values = {
        orientation: bar.value()
        for orientation, bar in win._canvas_widgets.scroll_bars.items()
    }
    expected_view_offset = win._canvas_widgets.canvas.get_view_offset()

    win._open_next_image()
    qtbot.waitUntil(lambda: win._image_path != first_image_path)
    win._open_prev_image()
    qtbot.waitUntil(lambda: win._image_path == first_image_path)
    qtbot.waitUntil(
        lambda: win._canvas_widgets.canvas.size()
        == win._canvas_widgets.canvas.sizeHint()
        and all(
            win._canvas_widgets.scroll_bars[orientation].value() == expected
            for orientation, expected in expected_scroll_values.items()
        )
        and win._canvas_widgets.canvas.get_view_offset() == expected_view_offset
    )

    for orientation, expected in expected_scroll_values.items():
        assert win._canvas_widgets.scroll_bars[orientation].value() == expected
    assert win._canvas_widgets.canvas.get_view_offset() == expected_view_offset

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
    phase: Qt.ScrollPhase = Qt.ScrollPhase.NoScrollPhase,
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
        phase,
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
    ("angle_delta", "phase"),
    [
        pytest.param(QPoint(), Qt.ScrollPhase.ScrollBegin, id="scroll_begin"),
        pytest.param(
            QPoint(120, 0),
            Qt.ScrollPhase.NoScrollPhase,
            id="horizontal_only",
        ),
    ],
)
def test_canvas_wheel_event_ignores_non_vertical_zoom(
    qtbot: QtBot,
    _win: MainWindow,
    pause: bool,
    angle_delta: QPoint,
    phase: Qt.ScrollPhase,
) -> None:
    canvas = _win._canvas_widgets.canvas

    with qtbot.assertNotEmitted(canvas.zoom_request):
        canvas.wheelEvent(
            _make_wheel_event(
                pos=QPointF(canvas.width() / 2, canvas.height() / 2),
                angle_delta=angle_delta,
                modifiers=Qt.KeyboardModifier.ControlModifier,
                phase=phase,
            )
        )

    close_or_pause(qtbot=qtbot, widget=_win, pause=pause)


@pytest.mark.gui
@pytest.mark.parametrize(
    ("angle_delta", "repetitions"),
    [
        pytest.param(120, 1, id="zoom_in"),
        pytest.param(-120, 12, id="repeated_zoom_out"),
    ],
)
def test_ctrl_wheel_keeps_image_point_under_cursor(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
    angle_delta: int,
    repetitions: int,
) -> None:
    win = main_win(file_or_dir=str(data_path / "raw/2011_000003.jpg"))
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    canvas = win._canvas_widgets.canvas
    viewport = canvas._scroll_viewport()
    assert viewport is not None

    image_pos = QPointF(canvas.pixmap.width() * 0.8, canvas.pixmap.height() / 2)
    cursor = QPointF(
        canvas.mapTo(viewport, image_to_widget_pos(canvas=canvas, image_pos=image_pos))
    ) + QPointF(0.25, 0.75)

    def _get_image_point_under_cursor() -> QPointF:
        return canvas.transform_widget_point_to_image(canvas.mapFrom(viewport, cursor))

    before = _get_image_point_under_cursor()
    for _ in range(repetitions):
        old_scale = canvas.scale
        QtWidgets.QApplication.sendEvent(
            canvas,
            _make_wheel_event(
                pos=canvas.mapFrom(viewport, cursor),
                angle_delta=QPoint(0, angle_delta),
                modifiers=Qt.KeyboardModifier.ControlModifier,
            ),
        )
        qtbot.waitUntil(
            lambda: canvas.scale != old_scale and canvas.size() == canvas.sizeHint()
        )

        after = _get_image_point_under_cursor()
        assert after.x() == pytest.approx(before.x(), abs=0.01)
        assert after.y() == pytest.approx(before.y(), abs=0.01)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
