from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

import osam.apis
import osam.types
import osam.types._blob
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QLabel
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import QProgressDialog
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

import labelme._widgets.download as download_module
from labelme._widgets.download import _confirm_ai_model_download
from labelme._widgets.download import _format_bytes
from labelme._widgets.download import _make_model_info_message_box
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


@pytest.fixture()
def choose_download(monkeypatch: pytest.MonkeyPatch) -> None:
    def click_download(message_box: QMessageBox) -> int:
        for button in message_box.buttons():
            if message_box.buttonRole(button) == QMessageBox.ButtonRole.AcceptRole:
                button.click()
                return 0
        raise AssertionError("Download button not found")

    monkeypatch.setattr(QMessageBox, "exec", click_download)


@pytest.mark.gui
@pytest.mark.parametrize(
    "model_name",
    [model_type.name for model_type in osam.apis.registered_model_types],
)
def test_model_info_has_clickable_links_and_offline_license(
    qtbot: QtBot,
    model_name: str,
) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    message_box = _make_model_info_message_box(
        model_name=model_name,
        parent=parent,
    )
    qtbot.addWidget(message_box)
    message_box.show()

    metadata = osam.apis.get_model_metadata(model_name)
    assert metadata.license_url in message_box.informativeText()
    assert metadata.source_url in message_box.informativeText()
    assert message_box.detailedText().strip()
    assert metadata.license_name.split()[0] in message_box.detailedText()
    assert any(
        label.openExternalLinks()
        and metadata.license_url in label.text()
        and metadata.source_url in label.text()
        for label in message_box.findChildren(QLabel)
    )


@pytest.mark.gui
def test_model_download_defaults_to_cancel(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    def click_cancel(message_box: QMessageBox) -> int:
        cancel_button = next(
            button
            for button in message_box.buttons()
            if message_box.buttonRole(button) == QMessageBox.ButtonRole.RejectRole
        )
        assert message_box.defaultButton() is cancel_button
        assert any(button.text() == "Download" for button in message_box.buttons())
        cancel_button.click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", click_cancel)

    assert _confirm_ai_model_download(model_name=_MODEL_NAME, parent=parent) is False


@pytest.mark.gui
def test_cancelled_model_download_does_not_pull(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    isolated_model_type: type[osam.types.Model],
) -> None:
    def cancel_download(*, model_name: str, parent: QWidget) -> bool:
        return False

    monkeypatch.setattr(
        download_module,
        "_confirm_ai_model_download",
        cancel_download,
    )

    def fail_if_called(
        cls: type[osam.types.Model],
        progress: Callable[[str, int, int | None], None] | None = None,
    ) -> None:
        raise AssertionError("model download started")

    monkeypatch.setattr(isolated_model_type, "pull", classmethod(fail_if_called))
    parent = QWidget()
    qtbot.addWidget(parent)

    assert download_ai_model(model_name=_MODEL_NAME, parent=parent) is False


@pytest.mark.gui
def test_unavailable_model_is_rejected_before_download(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LABELME_AI_MODEL_ALLOWLIST", "sam2:latest")
    parent = QWidget()
    qtbot.addWidget(parent)

    with pytest.raises(ValueError, match="not included"):
        download_ai_model(model_name="blocked-model", parent=parent)


@pytest.mark.gui
def test_download_ai_model_returns_true_when_pull_succeeds(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    isolated_model_type: type[osam.types.Model],
    close_failed_download_dialog: None,
    choose_download: None,
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
    choose_download: None,
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


@pytest.mark.gui
@pytest.mark.network
def test_download_ai_model_from_network(
    qtbot: QtBot,
    isolated_model_type: type[osam.types.Model],
    close_failed_download_dialog: None,
    choose_download: None,
) -> None:
    expected_paths = [Path(blob.path) for blob in isolated_model_type._blobs.values()]

    parent = QWidget()
    qtbot.addWidget(parent)

    assert download_ai_model(model_name=_MODEL_NAME, parent=parent) is True
    assert all(path.is_file() for path in expected_paths)


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "0 B"),
        (1023, "1023 B"),
        (1024, "1 KB"),
        (1536, "2 KB"),
        (1048063, "1023 KB"),
        (1048064, "1.0 MB"),
        (1048576, "1.0 MB"),
        (1572864, "1.5 MB"),
        (1073217535, "1023.5 MB"),
        (1073217536, "1.0 GB"),
        (1610612736, "1.5 GB"),
        (1828519936, "1.7 GB"),
        (1099511627776, "1.0 TB"),
    ],
)
def test_format_bytes(n: int, expected: str) -> None:
    assert _format_bytes(n) == expected
