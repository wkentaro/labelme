from __future__ import annotations

from concurrent.futures import Future
from concurrent.futures import ThreadPoolExecutor

from PySide6 import QtCore

from ._save_request import SaveRequest
from ._save_request import write_save_request


class SaveWriter(QtCore.QObject):
    finished = QtCore.Signal(object, int, object)
    idle = QtCore.Signal()

    def __init__(self, *, parent: QtCore.QObject) -> None:
        super().__init__(parent)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="save")
        self._active: tuple[SaveRequest, int, Future[None]] | None = None
        self._pending: tuple[SaveRequest, int] | None = None
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(10)
        self._timer.timeout.connect(self._poll)

    @property
    def is_busy(self) -> bool:
        return self._active is not None

    def submit(self, *, request: SaveRequest, revision: int) -> None:
        if self._active is None:
            self._active = (
                request,
                revision,
                self._executor.submit(write_save_request, request),
            )
            self._timer.start()
        else:
            self._pending = (request, revision)

    def discard_pending(self) -> None:
        self._pending = None

    def _poll(self) -> None:
        if self._active is None or not self._active[2].done():
            return
        request, revision, future = self._active
        self._active = None
        error = future.exception()
        if self._pending is None:
            self._timer.stop()
        else:
            pending, pending_revision = self._pending
            self._pending = None
            self.submit(request=pending, revision=pending_revision)
        # Poll on the GUI thread; the worker never calls Qt or live document code.
        self.finished.emit(request, revision, error)
        if self._active is None:
            self.idle.emit()

    def shutdown(self) -> None:
        assert self._active is None and self._pending is None
        self._executor.shutdown(wait=True)
