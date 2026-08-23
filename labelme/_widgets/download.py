from __future__ import annotations

import html
import inspect
from pathlib import Path
from typing import Final

import osam
import osam.types
from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtCore import QThread
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import QProgressDialog
from PySide6.QtWidgets import QWidget

from .. import _ai_models


class _Cancelled(Exception):
    pass


class _DownloadThread(QThread):
    UNKNOWN_SIZE: Final = -1

    progress = Signal(int, int, str, int, int)
    succeeded = Signal()
    error = Signal(Exception)

    def __init__(self, model_type: type[osam.types.Model], parent: QWidget) -> None:
        super().__init__(parent)
        self._model_type = model_type
        self._total_files = sum(
            1 + len(blob.attachments) for blob in model_type._blobs.values()
        )

    def cancel(self) -> None:
        self.requestInterruption()

    def run(self) -> None:
        file_index = -1
        current_filename: str | None = None

        def _on_progress(
            filename: str,
            bytes_so_far: int,
            bytes_total: int | None,
        ) -> None:
            nonlocal file_index, current_filename
            if self.isInterruptionRequested():
                raise _Cancelled()
            if filename != current_filename:
                file_index += 1
                current_filename = filename
            self.progress.emit(
                file_index,
                self._total_files,
                filename,
                bytes_so_far,
                bytes_total if bytes_total is not None else self.UNKNOWN_SIZE,
            )

        try:
            self._model_type.pull(progress=_on_progress)
            self.succeeded.emit()
        except _Cancelled:
            pass
        except Exception as e:
            self.error.emit(e)


def _format_bytes(n: int) -> str:
    UNIT: Final = 1024
    value = float(n)
    # Advance a tier when the value rounds up to a full UNIT, so the display
    # never reads "1024 KB" / "1024.0 MB". The boundary rounds to a whole unit
    # (round(value)), independent of each tier's display precision. TB is the
    # terminal unit.
    for suffix, decimals in (("B", 0), ("KB", 0), ("MB", 1), ("GB", 1)):
        if round(value) < UNIT:
            return f"{value:.{decimals}f} {suffix}"
        value /= UNIT
    return f"{value:.1f} TB"


def _make_model_info_message_box(*, model_name: str, parent: QWidget) -> QMessageBox:
    model_type = osam.apis.get_model_type_by_name(model_name)
    metadata = model_type.metadata
    license_path = Path(inspect.getfile(model_type)).with_name("LICENSE")

    message_box = QMessageBox(parent)
    message_box.setWindowTitle("AI Model Information")
    message_box.setIcon(QMessageBox.Icon.Information)
    message_box.setTextFormat(Qt.TextFormat.RichText)
    message_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
    message_box.setText(f"<b>{html.escape(model_name)}</b>")
    message_box.setInformativeText(
        f"License: {html.escape(metadata.license_name)}<br>"
        f'<a href="{html.escape(metadata.license_url)}">License terms</a><br>'
        f'<a href="{html.escape(metadata.source_url)}">Model source and provenance</a>'
    )
    message_box.setDetailedText(license_path.read_text(encoding="utf-8"))
    return message_box


def show_ai_model_info(*, model_name: str, parent: QWidget) -> None:
    message_box = _make_model_info_message_box(
        model_name=model_name,
        parent=parent,
    )
    message_box.setStandardButtons(QMessageBox.StandardButton.Close)
    message_box.exec()


def _confirm_ai_model_download(*, model_name: str, parent: QWidget) -> bool:
    message_box = _make_model_info_message_box(
        model_name=model_name,
        parent=parent,
    )
    message_box.setWindowTitle("Download AI Model")
    message_box.setText(f"Download <b>{html.escape(model_name)}</b>?")
    download_button = message_box.addButton(
        "Download", QMessageBox.ButtonRole.AcceptRole
    )
    cancel_button = message_box.addButton(QMessageBox.StandardButton.Cancel)
    message_box.setDefaultButton(cancel_button)
    message_box.exec()
    return message_box.clickedButton() is download_button


def download_ai_model(model_name: str, parent: QWidget) -> bool:
    _ai_models.require_model_available(model_name=model_name)
    model_type = osam.apis.get_model_type_by_name(model_name)

    if model_type.get_size() is not None:
        return True

    if not _confirm_ai_model_download(model_name=model_name, parent=parent):
        return False

    dialog = QProgressDialog(
        f"Downloading {model_name}...\n(requires internet connection)",
        "Cancel",
        0,
        0,
        parent,
    )
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.setMinimumWidth(400)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)

    thread = _DownloadThread(model_type=model_type, parent=parent)
    succeeded = False

    def _on_progress(
        file_index: int,
        file_count: int,
        filename: str,
        bytes_so_far: int,
        bytes_total: int,
    ) -> None:
        if succeeded:
            return
        label = (
            f"Downloading {model_name} ({file_index + 1}/{file_count})\n\n{filename}\n"
        )
        if bytes_total != _DownloadThread.UNKNOWN_SIZE:
            dialog.setRange(0, bytes_total)
            dialog.setValue(bytes_so_far)
            label += f"{_format_bytes(bytes_so_far)} / {_format_bytes(bytes_total)}"
        else:
            dialog.setRange(0, 0)
            if bytes_so_far > 0:
                label += _format_bytes(bytes_so_far)
        dialog.setLabelText(label)

    def _on_succeeded() -> None:
        nonlocal succeeded
        succeeded = True
        dialog.close()

    def _on_error(e: Exception) -> None:
        logger.error("Exception occurred: {}", e)
        dialog.setRange(0, 1)
        dialog.setLabelText(
            f"Failed to download {model_name}.\n(check internet connection)"
        )
        dialog.setCancelButtonText("Close")

    dialog.canceled.connect(thread.cancel)
    thread.progress.connect(_on_progress)
    thread.succeeded.connect(_on_succeeded)
    thread.error.connect(_on_error)

    dialog.show()
    thread.start()
    dialog.exec()

    thread.progress.disconnect(_on_progress)
    thread.succeeded.disconnect(_on_succeeded)
    thread.error.disconnect(_on_error)
    if not thread.wait(5000):
        thread.terminate()
        thread.wait()

    return succeeded
