from __future__ import annotations

from typing import Final

import osam
import osam.types
from loguru import logger
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QThread
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QProgressDialog
from PyQt5.QtWidgets import QWidget


class _Cancelled(Exception):
    pass


class _DownloadThread(QThread):
    UNKNOWN_SIZE: Final = -1

    progress = pyqtSignal(int, int, str, int, int)
    succeeded = pyqtSignal()
    error = pyqtSignal(Exception)

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
    KB: Final = 1024
    MB: Final = 1024 * 1024
    if n < KB:
        return f"{n} B"
    if n < MB:
        return f"{n / KB:.0f} KB"
    return f"{n / MB:.1f} MB"


def download_ai_model(model_name: str, parent: QWidget) -> bool:
    model_type = osam.apis.get_model_type_by_name(model_name)

    if model_type.get_size() is not None:
        return True

    dialog = QProgressDialog(
        f"Downloading {model_name}...\n(requires internet connection)",
        "Cancel",
        0,
        0,
        parent,
    )
    dialog.setWindowModality(Qt.WindowModal)
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
    dialog.exec_()

    thread.progress.disconnect(_on_progress)
    thread.succeeded.disconnect(_on_succeeded)
    thread.error.disconnect(_on_error)
    if not thread.wait(5000):
        thread.terminate()
        thread.wait()

    return succeeded
