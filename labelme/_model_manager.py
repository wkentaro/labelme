from __future__ import annotations

import importlib
import multiprocessing
import os
import shutil
import tempfile
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore

from ._ai_models import AI_ASSIST_MODEL_OPTIONS
from ._ai_models import AI_TEXT_MODEL_OPTIONS

if TYPE_CHECKING:
    import osam


def _pull_model(
    blobs: dict[str, osam.types.Blob],
    cache_root: Path,
    cancel: Event,
    connection: Connection,
    /,
) -> None:
    import osam  # noqa: PLC0415 -- deferred: ~250ms off importing labelme._app

    cached_download = importlib.import_module("gdown.cached_download")
    cached_download.cache_root = str(cache_root)
    # Verified downloads are staged on the destination filesystem, so an
    # uncooperative worker cannot expose a partially published model file.
    cached_download.shutil.move = os.replace  # ty: ignore[invalid-assignment]

    def report_progress(filename: str, done: int, total: int | None) -> None:
        connection.send(("progress", filename, done, total))

    try:
        for blob in blobs.values():
            blob.pull(
                progress=report_progress,
                cancel=cancel,  # ty: ignore[invalid-argument-type]
            )
    except osam.types.PullCancelledError:
        connection.send(("cancelled",))
    except Exception as error:
        connection.send(("error", str(error)))
    else:
        connection.send(("done",))
    finally:
        connection.close()


class _Pull(QtCore.QObject):
    _completed: bool
    _stopped: bool
    _blobs: dict[str, osam.types.Blob]
    _blob_root: Path
    _cache_root: Path | None
    _cancel: Event
    _process: BaseProcess | None
    _context: multiprocessing.context.SpawnContext
    _child_connection: Connection
    _timer: QtCore.QTimer
    _connection: Connection

    model_name: str
    error: str | None
    progress: tuple[str, int, int | None]
    progress_changed = QtCore.Signal()
    finished = QtCore.Signal()

    def __init__(self, *, model_name: str, parent: QtCore.QObject) -> None:
        super().__init__(parent)
        self.model_name = model_name
        self.error: str | None = None
        self.progress = ("", 0, None)
        self._completed = False
        self._stopped = False
        import osam  # noqa: PLC0415 -- deferred: ~250ms off importing labelme._app

        self._blobs = osam.apis.get_model_type_by_name(model_name)._blobs.copy()
        first_blob = next(iter(self._blobs.values()))
        first_path = Path(first_blob.path)
        self._blob_root = (
            first_path.parent.parent if first_blob.attachments else first_path.parent
        )
        self._cache_root = None

        context = multiprocessing.get_context("spawn")
        self._cancel = context.Event()
        self._connection, child_connection = context.Pipe(duplex=False)
        self._process = None
        self._context = context
        self._child_connection = child_connection
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._poll)

    def start(self) -> None:
        try:
            self._blob_root.mkdir(parents=True, exist_ok=True)
            self._cache_root = Path(
                tempfile.mkdtemp(prefix=".labelme-pull-", dir=self._blob_root)
            )
            self._process = self._context.Process(
                target=_pull_model,
                args=(
                    self._blobs,
                    self._cache_root,
                    self._cancel,
                    self._child_connection,
                ),
                daemon=True,
            )
            self._process.start()
        except Exception:
            self._connection.close()
            self._child_connection.close()
            if self._cache_root is not None:
                shutil.rmtree(self._cache_root, ignore_errors=True)
            raise
        self._child_connection.close()
        self._timer.start()

    def revoke(self) -> None:
        self._cancel.set()

    def stop(self) -> bool:
        assert self._process is not None
        self.revoke()
        self._timer.stop()
        self._process.join(timeout=0.1)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=0.5)
        if self._process.is_alive():
            self._process.kill()
            self._process.join(timeout=0.5)
        if self._process.is_alive():
            self.error = "Failed to stop the model download process."
            self._timer.start()
            return False
        self._stopped = True
        self._receive_messages()
        self._connection.close()
        self._process.close()
        assert self._cache_root is not None
        shutil.rmtree(self._cache_root, ignore_errors=True)
        return True

    def _poll(self) -> None:
        assert self._process is not None
        if self._stopped:
            return
        self._receive_messages()
        if self._process.is_alive():
            return
        self._process.join()
        self._receive_messages()
        exitcode = self._process.exitcode
        self._process.close()
        self._connection.close()
        assert self._cache_root is not None
        shutil.rmtree(self._cache_root, ignore_errors=True)
        self._timer.stop()
        self._stopped = True
        if not self._completed and self.error is None:
            self.error = f"Model download process exited with code {exitcode}."
        self.finished.emit()

    def _receive_messages(self) -> None:
        while True:
            try:
                if not self._connection.poll():
                    return
                message = self._connection.recv()
            except (EOFError, OSError):
                return
            if message[0] == "progress":
                if not self._stopped:
                    _, filename, done, total = message
                    self.progress = (filename, done, total)
                    self.progress_changed.emit()
            elif message[0] == "error":
                self.error = message[1]
            elif message[0] in {"cancelled", "done"}:
                self._completed = True


class ModelManager(QtCore.QObject):
    _pull: _Pull | None
    _closed: bool

    changed = QtCore.Signal()
    progress_changed = QtCore.Signal()

    models: dict[str, str]
    errors: dict[str, str]
    queue: list[str]

    def __init__(self, *, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        # Model names are product names, so they stay untranslated.
        self.models = {
            option.model_name: option.display_name for option in AI_ASSIST_MODEL_OPTIONS
        } | dict(AI_TEXT_MODEL_OPTIONS)
        self.errors = {}
        self.queue = []
        self._pull = None
        self._closed = False

    @property
    def active(self) -> str | None:
        return self._pull.model_name if self._pull is not None else None

    @property
    def progress(self) -> tuple[str, int, int | None]:
        return self._pull.progress if self._pull is not None else ("", 0, None)

    def is_ready(self, *, model_name: str) -> bool:
        # Every writer verifies the hash before moving a file into the cache, so
        # presence is enough; a file corrupted later fails the check on load.
        if model_name not in self.models:
            return False
        import osam  # noqa: PLC0415 -- deferred: ~250ms off importing labelme._app

        return osam.apis.get_model_type_by_name(model_name).get_size() is not None

    def get_state(self, *, model_name: str) -> str:
        if model_name in self.queue:
            return "queued"
        if model_name == self.active:
            return "downloading"
        if self.is_ready(model_name=model_name):
            return "downloaded"
        if model_name in self.errors:
            return "failed"
        return "missing"

    def refresh(self) -> None:
        self.changed.emit()

    def enqueue(self, *, model_name: str) -> None:
        if (
            self._closed
            or model_name not in self.models
            or self.is_ready(model_name=model_name)
        ):
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
        self._pull = _Pull(model_name=self.queue.pop(0), parent=self)
        self._pull.progress_changed.connect(self.progress_changed)
        self._pull.finished.connect(self._on_finished)
        try:
            self._pull.start()
        except Exception as error:
            pull = self._pull
            self._pull = None
            self.errors[pull.model_name] = str(error)
            pull.deleteLater()
            self.changed.emit()
            self._start_next()
            return
        self.changed.emit()

    def _on_finished(self) -> None:
        assert self._pull is not None
        pull = self._pull
        self._pull = None
        if pull.error is not None:
            self.errors[pull.model_name] = pull.error
        pull.deleteLater()
        self.changed.emit()
        self._start_next()

    def _stop_active_pull(self) -> bool:
        assert self._pull is not None
        pull = self._pull
        if not pull.stop():
            assert pull.error is not None
            self.errors[pull.model_name] = pull.error
            return False
        self._pull = None
        if pull.error is not None:
            self.errors[pull.model_name] = pull.error
        pull.deleteLater()
        return True

    def cancel(self, model_name: str, /) -> None:
        if model_name in self.queue:
            self.queue.remove(model_name)
            self.changed.emit()
        elif model_name == self.active:
            stopped = self._stop_active_pull()
            self.changed.emit()
            if stopped:
                self._start_next()

    def remove(self, *, model_name: str) -> None:
        if model_name in self.queue:
            self.queue.remove(model_name)
        elif model_name == self.active:
            if not self._stop_active_pull():
                self.changed.emit()
                return
        import osam  # noqa: PLC0415 -- deferred: ~250ms off importing labelme._app

        try:
            osam.apis.get_model_type_by_name(model_name).remove()
        finally:
            self.errors.pop(model_name, None)
            self.changed.emit()
            self._start_next()

    def shutdown(self) -> bool:
        self._closed = True
        if self._pull is not None and not self._stop_active_pull():
            self._closed = False
            return False
        self.queue.clear()
        return True
