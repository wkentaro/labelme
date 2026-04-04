from __future__ import annotations

import contextlib
import importlib
import types

import osam
from loguru import logger
from PyQt5 import QtWidgets
from PyQt5.QtCore import QObject
from PyQt5.QtCore import QRunnable
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QThreadPool
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QProgressDialog


class _AiModelDownloadSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(Exception)
    progress = pyqtSignal(int, int, str)


def _format_num_bytes(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    raise AssertionError("unreachable")


def _format_download_label(
    blob_index: int,
    num_blobs: int,
    *,
    percent: int | None = None,
    current_size: int | None = None,
    total_size: int | None = None,
) -> str:
    part_suffix: str = (
        f" ({blob_index}/{num_blobs})" if num_blobs > 1 else ""
    )
    if percent is None or current_size is None or total_size is None:
        return (
            f"Downloading AI model...{part_suffix}\n"
            "(requires internet connection)"
        )
    return (
        f"Downloading AI model...{part_suffix}\n"
        f"{percent}% - {_format_num_bytes(current_size)} / "
        f"{_format_num_bytes(total_size)}"
    )


@contextlib.contextmanager
def _patched_gdown_tqdm(progress_factory):
    gdown_download = importlib.import_module("gdown.download")
    original_tqdm = gdown_download.tqdm.tqdm
    gdown_download.tqdm.tqdm = progress_factory
    try:
        yield
    finally:
        gdown_download.tqdm.tqdm = original_tqdm


class _AiModelDownloadWorker(QRunnable):
    def __init__(self, model_type, signals: _AiModelDownloadSignals):
        super().__init__()
        self.model_type = model_type
        self.signals = signals

    def _download_blob(self, blob, blob_index: int, num_blobs: int) -> None:
        self.signals.progress.emit(
            0,
            0,
            _format_download_label(blob_index=blob_index, num_blobs=num_blobs),
        )

        worker = self

        class _QtSignalTqdm:
            def __init__(self, *args, total=None, initial=0, **kwargs):
                del args, kwargs
                self._total = total
                self._current = initial
                self._last_percent: int | None = None
                self._emit_progress(force=True)

            def update(self, amount=1):
                self._current += amount
                self._emit_progress()

            def close(self):
                self._emit_progress(force=True)

            def _emit_progress(self, *, force: bool = False):
                if not self._total:
                    if force:
                        worker.signals.progress.emit(
                            0,
                            0,
                            _format_download_label(
                                blob_index=blob_index, num_blobs=num_blobs
                            ),
                        )
                    return

                percent: int = max(
                    0,
                    min(
                        100,
                        int(round(self._current * 100 / self._total)),
                    ),
                )
                if not force and percent == self._last_percent:
                    return
                self._last_percent = percent
                worker.signals.progress.emit(
                    100,
                    percent,
                    _format_download_label(
                        blob_index=blob_index,
                        num_blobs=num_blobs,
                        percent=percent,
                        current_size=min(self._current, self._total),
                        total_size=self._total,
                    ),
                )

        with _patched_gdown_tqdm(_QtSignalTqdm):
            blob.pull()

        self.signals.progress.emit(
            100,
            100,
            _format_download_label(
                blob_index=blob_index,
                num_blobs=num_blobs,
                percent=100,
                current_size=blob.size or 0,
                total_size=blob.size or 0,
            ),
        )

    def run(self):
        try:
            blobs = list(self.model_type._blobs.values())
            for blob_index, blob in enumerate(blobs, start=1):
                self._download_blob(
                    blob=blob,
                    blob_index=blob_index,
                    num_blobs=len(blobs),
                )
            self.signals.finished.emit()
        except Exception as e:
            self.signals.error.emit(e)


def download_ai_model(model_name: str, parent: QtWidgets.QWidget) -> bool:
    model_type = osam.apis.get_model_type_by_name(model_name)

    if _is_already_downloaded := model_type.get_size() is not None:
        return True

    dialog: QProgressDialog = QProgressDialog(
        "Downloading AI model...\n(requires internet connection)",
        None,  # type: ignore
        0,
        100,
        parent,
    )  # type: ignore[call-overload]
    dialog.setWindowModality(Qt.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    progress_bar = QtWidgets.QProgressBar(dialog)
    progress_bar.setTextVisible(True)
    progress_bar.setFormat("%p%")
    dialog.setBar(progress_bar)
    dialog.setValue(0)

    signals: _AiModelDownloadSignals = _AiModelDownloadSignals()
    worker: _AiModelDownloadWorker = _AiModelDownloadWorker(model_type, signals)
    pool = QThreadPool.globalInstance()

    handle_error_attrs = types.SimpleNamespace(e=None)

    def handle_progress(maximum: int, value: int, label_text: str):
        dialog.setLabelText(label_text)
        dialog.setRange(0, maximum)
        dialog.setValue(value)

    def handle_error(e: Exception):
        logger.error("Exception occurred: {}", e)
        handle_error_attrs.e = e
        #
        QtWidgets.QApplication.setOverrideCursor(Qt.ArrowCursor)
        dialog.setRange(0, 1)  # pause busy mode
        dialog.setLabelText("Failed to download AI model.\n(check internet connection)")
        dialog.setCancelButtonText("Close")

    signals.finished.connect(dialog.close)
    signals.error.connect(handle_error)
    signals.progress.connect(handle_progress)

    dialog.show()
    pool.start(worker)
    dialog.exec_()

    return handle_error_attrs.e is None
