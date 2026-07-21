from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot

from ..conftest import close_or_pause
from .conftest import MainWinFactory
from .conftest import show_window_and_wait_for_imagedata

_RAW_FILE_NAME: Final[str] = "raw/2011_000003.jpg"


@pytest.mark.gui
@pytest.mark.parametrize(
    ("patch_target", "error"),
    [
        ("pathlib.Path.mkdir", PermissionError("read-only output directory")),
        ("os.path.relpath", ValueError("paths are on different drives")),
    ],
)
def test_save_labels_reports_filesystem_failure_without_crashing(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pause: bool,
    patch_target: str,
    error: Exception,
) -> None:
    win = main_win(
        file_or_dir=str(data_path / _RAW_FILE_NAME),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)

    errors_shown: list[bool] = []

    def _record_critical(*args: object, **kwargs: object) -> int:
        errors_shown.append(True)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "critical", _record_critical)

    def _raise(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(patch_target, _raise)

    saved = win.save_labels(label_path=str(tmp_path / "out" / "2011_000003.json"))

    assert saved is False
    assert errors_shown

    close_or_pause(qtbot=qtbot, widget=win, pause=pause)
