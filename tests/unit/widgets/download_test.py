from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

import osam.apis
import osam.types
import osam.types._blob
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QProgressDialog
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from labelme._widgets.download import download_ai_model

_MODEL_NAME: Final = "efficientsam:10m"


@pytest.fixture()
def isolated_model_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> type[osam.types.Model]:
    # Redirect osam blob storage to a temp directory so the model reads as not
    # downloaded, without touching the real model cache in ~/.cache/osam.
    blob_base = tmp_path / "osam_blobs"

    def patched_path(self: osam.types._blob.Blob) -> str:
        if self.attachments:
            safe_hash = self.hash.replace("sha256:", "sha256-")
            return str(blob_base / safe_hash / self.filename)
        return str(blob_base / self.hash)

    monkeypatch.setattr(osam.types._blob.Blob, "path", property(patched_path))
    return osam.apis.get_model_type_by_name(_MODEL_NAME)


@pytest.mark.gui
def test_download_ai_model_returns_true_when_pull_succeeds(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    isolated_model_type: type[osam.types.Model],
    close_failed_download_dialog: None,
) -> None:
    expected_paths = [Path(blob.path) for blob in isolated_model_type._blobs.values()]
    TEST_MODEL_DATA: Final = b"test model"

    def fake_pull(
        cls: type[osam.types.Model],
        progress: Callable[[str, int, int | None], None] | None = None,
    ) -> None:
        for blob in cls._blobs.values():
            path = Path(blob.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if progress is not None:
                progress(blob.filename, 0, len(TEST_MODEL_DATA))
            path.write_bytes(TEST_MODEL_DATA)
            if progress is not None:
                progress(
                    blob.filename,
                    len(TEST_MODEL_DATA),
                    len(TEST_MODEL_DATA),
                )

    monkeypatch.setattr(isolated_model_type, "pull", classmethod(fake_pull))

    parent = QWidget()
    qtbot.addWidget(parent)

    assert download_ai_model(model_name=_MODEL_NAME, parent=parent) is True
    assert all(path.read_bytes() == TEST_MODEL_DATA for path in expected_paths)
    assert not any(
        isinstance(widget, QProgressDialog) and widget.isVisible()
        for widget in QApplication.topLevelWidgets()
    )


@pytest.mark.gui
def test_download_ai_model_returns_false_when_pull_fails(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    close_failed_download_dialog: None,
) -> None:
    model_type = osam.apis.get_model_type_by_name(_MODEL_NAME)

    def fail_pull(
        cls: type[osam.types.Model],
        progress: Callable[[str, int, int | None], None] | None = None,
    ) -> None:
        raise RuntimeError("download failed")

    monkeypatch.setattr(model_type, "get_size", classmethod(lambda cls: None))
    monkeypatch.setattr(model_type, "pull", classmethod(fail_pull))

    parent = QWidget()
    qtbot.addWidget(parent)

    assert download_ai_model(model_name=_MODEL_NAME, parent=parent) is False
