from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from labelme.app import MainWindow

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata

_STATUS_MESSAGE_TIMEOUT_MS: Final[int] = 5000


def _wait_for_status_message_containing(
    *,
    qtbot: QtBot,
    win: MainWindow,
    substring: str,
) -> list[str]:
    captured: list[str] = []
    status_bar = win.statusBar()
    assert status_bar is not None

    def _check() -> None:
        msg = status_bar.currentMessage()
        if msg:
            captured.append(msg)
        assert any(substring in m for m in captured)

    qtbot.waitUntil(_check, timeout=_STATUS_MESSAGE_TIMEOUT_MS)
    return captured


@pytest.mark.gui
def test_status_bar_shows_loaded_message_after_opening(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    pause: bool,
) -> None:
    file_path = str(data_path / "raw" / "2011_000003.jpg")
    win = main_win(file_or_dir=file_path)
    win.show()
    captured = _wait_for_status_message_containing(
        qtbot=qtbot,
        win=win,
        substring="Loaded",
    )
    assert any("Loaded" in m and Path(file_path).name in m for m in captured)
    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_save_does_not_emit_transient_status_message(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    pause: bool,
) -> None:
    json_basename: Final[str] = "2011_000003.json"
    NO_TEMP_MESSAGE_TIMEOUT_MS: Final[int] = 3000
    win = main_win(
        file_or_dir=str(data_path / "annotated" / json_basename),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    status_bar = win.statusBar()
    assert status_bar is not None

    def _no_temp_message() -> None:
        assert status_bar.currentMessage() == ""

    qtbot.waitUntil(_no_temp_message, timeout=NO_TEMP_MESSAGE_TIMEOUT_MS)

    label_path = str(tmp_path / json_basename)
    win.save_labels(label_path=label_path)

    assert status_bar.currentMessage() == ""

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)


@pytest.mark.gui
def test_status_bar_shows_error_message_on_corrupt_file(
    main_win: MainWinFactory,
    qtbot: QtBot,
    tmp_path: Path,
    pause: bool,
) -> None:
    DISMISS_TIMEOUT_MS: Final[int] = 3000

    corrupt_json = tmp_path / "corrupt.json"
    corrupt_json.write_text('{"version": "5.0", "shapes": [')

    def _dismiss_error_dialog() -> None:
        qtbot.waitUntil(
            lambda: QApplication.activeModalWidget() is not None,
            timeout=DISMISS_TIMEOUT_MS,
        )
        dlg = QApplication.activeModalWidget()
        assert dlg is not None
        dlg.close()

    QTimer.singleShot(0, _dismiss_error_dialog)

    win = main_win(file_or_dir=str(corrupt_json))
    win.show()

    captured = _wait_for_status_message_containing(
        qtbot=qtbot,
        win=win,
        substring="Error",
    )
    assert any("Error" in m and str(corrupt_json) in m for m in captured)

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
