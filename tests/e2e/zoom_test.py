from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow
from labelme.app import _ZoomMode

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
    _win.setFitWindow(True)

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
    _win.setFitWindow(True)
    _win.setFitWidth(True)

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
    _win.setFitWindow(True)
    assert _win._canvas_widgets.zoom_widget.value() != 100

    _win._set_zoom_to_original()

    assert _win._canvas_widgets.zoom_widget.value() == 100
    assert _win._zoom_mode == _ZoomMode.MANUAL_ZOOM

    close_or_pause(qtbot=qtbot, widget=_win, pause=pause)
