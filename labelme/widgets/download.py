from __future__ import annotations

import types
import typing

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


class _AiModelDownloadWorker(QRunnable):
    def __init__(self, model_type, signals: _AiModelDownloadSignals):
        super().__init__()
        self.model_type = model_type
        self.signals = signals

    def run(self):
        try:
            self.model_type.pull()
            self.signals.finished.emit()
        except Exception as e:
            self.signals.error.emit(e)


def download_ai_model(model_name: str, parent: QtWidgets.QWidget) -> bool:
    model_type = osam.apis.get_model_type_by_name(model_name)
    model_type = typing.cast(type[osam.types.Model], model_type)

    if _is_already_downloaded := model_type.get_size() is not None:
        return True

    dialog: QProgressDialog = QProgressDialog(
        "Downloading AI model...\n(requires internet connection)",
        None,  # type: ignore
        0,
        0,
        parent,
    )  # type: ignore[call-overload]
    dialog.setWindowModality(Qt.WindowModal)
    dialog.setMinimumDuration(0)

    signals: _AiModelDownloadSignals = _AiModelDownloadSignals()
    worker: _AiModelDownloadWorker = _AiModelDownloadWorker(model_type, signals)
    pool = QThreadPool.globalInstance()

    handle_error_attrs = types.SimpleNamespace(e=None)

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

    dialog.show()
    pool.start(worker)
    dialog.exec_()

    return handle_error_attrs.e is None
