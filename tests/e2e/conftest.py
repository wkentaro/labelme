from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from PyQt5.QtCore import QSettings

import labelme.app


@pytest.fixture(autouse=True)
def _isolated_qtsettings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    settings_file = tmp_path / "qtsettings.ini"
    settings: QSettings = QSettings(str(settings_file), QSettings.IniFormat)
    monkeypatch.setattr(
        labelme.app.QtCore, "QSettings", lambda *args, **kwargs: settings
    )
    yield
