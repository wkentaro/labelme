from __future__ import annotations

import threading

import osam
from PySide6 import QtCore

from ._ai_models import AI_ASSIST_MODEL_OPTIONS
from ._ai_models import AI_TEXT_MODEL_OPTIONS


class _Pull(QtCore.QThread):
    model_name: str
    cancel: threading.Event
    error: str | None
    # Byte counts exceed a C++ int for multi-GiB weights, so pass them as objects.
    progress = QtCore.Signal(str, object, object)

    def __init__(self, *, model_name: str, parent: QtCore.QObject) -> None:
        super().__init__(parent)
        self.model_name = model_name
        self.cancel = threading.Event()
        self.error: str | None = None

    def run(self) -> None:
        try:
            osam.apis.get_model_type_by_name(self.model_name).pull(
                progress=self.progress.emit, cancel=self.cancel
            )
        except osam.types.PullCancelledError:
            pass
        except Exception as error:
            self.error = str(error)


class ModelManager(QtCore.QObject):
    changed = QtCore.Signal()
    progress_changed = QtCore.Signal()

    models: dict[str, str]
    errors: dict[str, str]
    queue: list[str]
    active: str | None
    progress: tuple[str, int, int | None]

    def __init__(self, *, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.models = dict(
            [
                (option.model_name, option.display_name)
                for option in AI_ASSIST_MODEL_OPTIONS
            ]
            + list(AI_TEXT_MODEL_OPTIONS)
        )
        self.errors = {}
        self.queue = []
        self.active = None
        self.progress = ("", 0, None)
        self._pull: _Pull | None = None
        self._closed = False

    def is_ready(self, model_name: str, /) -> bool:
        # Every writer verifies the hash before moving a file into the cache, so
        # presence is enough; a file corrupted later fails the check on load.
        if model_name not in self.models:
            return False
        return osam.apis.get_model_type_by_name(model_name).get_size() is not None

    def get_state(self, model_name: str, /) -> str:
        if model_name in self.queue:
            return "queued"
        if model_name == self.active:
            return "downloading"
        if self.is_ready(model_name):
            return "downloaded"
        if model_name in self.errors:
            return "failed"
        return "missing"

    def refresh(self) -> None:
        self.changed.emit()

    def enqueue(self, model_name: str, /) -> None:
        if self._closed or model_name not in self.models or self.is_ready(model_name):
            return
        if model_name == self.active or model_name in self.queue:
            return
        self.queue.append(model_name)
        self.errors.pop(model_name, None)
        self.changed.emit()
        self._start_next()

    def _start_next(self) -> None:
        if self._closed or self._pull is not None or not self.queue:
            return
        self.active = self.queue.pop(0)
        self.progress = ("", 0, None)
        self._pull = _Pull(model_name=self.active, parent=self)
        self._pull.progress.connect(self._on_progress)
        self._pull.finished.connect(self._on_finished)
        self._pull.start()
        self.changed.emit()

    def _on_progress(self, filename: str, done: object, total: object, /) -> None:
        assert isinstance(done, int)
        self.progress = (filename, done, total if isinstance(total, int) else None)
        self.progress_changed.emit()

    def _on_finished(self) -> None:
        assert self._pull is not None
        pull = self._pull
        self._pull = None
        pull.deleteLater()
        if pull.model_name == self.active:
            self.active = None
            if pull.error:
                self.errors[pull.model_name] = pull.error
        self.changed.emit()
        self._start_next()

    def cancel(self, model_name: str, /) -> None:
        if model_name in self.queue:
            self.queue.remove(model_name)
            self.changed.emit()
        elif model_name == self.active:
            assert self._pull is not None
            self._pull.cancel.set()
            self.active = None
            self.changed.emit()

    def remove(self, model_name: str, /) -> None:
        self.cancel(model_name)
        try:
            osam.apis.get_model_type_by_name(model_name).remove()
        finally:
            self.errors.pop(model_name, None)
            self.changed.emit()

    def shutdown(self) -> None:
        self._closed = True
        self.queue.clear()
        self.active = None
        if self._pull is not None:
            self._pull.cancel.set()
            self._pull.wait()
