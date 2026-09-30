from __future__ import annotations

import functools

from PySide6 import QtCore

from ._save_request import SaveRequest
from ._save_request import write_save_request


def _write_and_notify(
    request: SaveRequest, completed: QtCore.SignalInstance, /
) -> None:
    try:
        write_save_request(request)
    except BaseException as error:
        # Every worker failure must release the GUI's save barrier.
        completed.emit(error)
    else:
        completed.emit(None)


class SaveWriter(QtCore.QObject):
    finished = QtCore.Signal(object, int, object)
    idle = QtCore.Signal()
    _completed = QtCore.Signal(object)

    def __init__(self, *, parent: QtCore.QObject) -> None:
        super().__init__(parent)
        self._pool = QtCore.QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._active: tuple[SaveRequest, int] | None = None
        self._pending: tuple[SaveRequest, int] | None = None
        # Save state belongs to the GUI thread, even if a write finishes immediately.
        self._completed.connect(
            self._on_finished, QtCore.Qt.ConnectionType.QueuedConnection
        )

    @property
    def is_busy(self) -> bool:
        return self._active is not None

    def get_latest_path(self) -> str | None:
        if self._pending is not None:
            return self._pending[0].filename
        return None if self._active is None else self._active[0].filename

    def submit(self, *, request: SaveRequest, revision: int) -> None:
        if self._active is None:
            self._active = (request, revision)
            self._pool.start(
                functools.partial(_write_and_notify, request, self._completed)
            )
        else:
            self._pending = (request, revision)

    def discard_pending(self) -> None:
        self._pending = None

    @QtCore.Slot(object)
    def _on_finished(self, error: BaseException | None, /) -> None:
        assert self._active is not None
        request, revision = self._active
        self._active = None
        if self._pending is not None:
            pending, pending_revision = self._pending
            self._pending = None
            self.submit(request=pending, revision=pending_revision)
        self.finished.emit(request, revision, error)
        if self._active is None:
            self.idle.emit()

    def shutdown(self) -> None:
        assert self._active is None and self._pending is None
        self._pool.waitForDone()
