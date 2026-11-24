from __future__ import annotations

import threading
from typing import TYPE_CHECKING
from typing import Final

from PySide6 import QtCore

from ._ai_models import AI_ASSIST_MODEL_OPTIONS
from ._ai_models import AI_TEXT_MODEL_OPTIONS
from ._ai_models import Device
from ._ai_models import model_info
from ._ai_models import osam_client

if TYPE_CHECKING:
    import osam


class _Pull(QtCore.QObject):
    _cancel: threading.Event
    _thread: threading.Thread

    model_name: str
    error: str | None
    progress: tuple[str, int, int | None]
    progress_changed = QtCore.Signal()
    finished = QtCore.Signal()
    # Emitted from the download thread, so Qt delivers it on this object's.
    _ended = QtCore.Signal()

    def __init__(
        self,
        *,
        model_name: str,
        device: Device,
        parent: QtCore.QObject,
    ) -> None:
        super().__init__(parent)
        self.model_name = model_name
        self.error = None
        self.progress = ("", 0, None)
        self._cancel = threading.Event()
        self._thread = threading.Thread(
            target=self._run, kwargs={"device": device}, daemon=True
        )
        self._ended.connect(self._on_ended)

    def start(self) -> None:
        self._thread.start()

    def _run(self, *, device: Device) -> None:
        import osam  # noqa: PLC0415 -- deferred: ~250ms off importing labelme._app

        def report(line: dict) -> None:
            self.progress = (
                line["status"].removeprefix("pulling "),
                line["completed"],
                line["total"],
            )
            if not self._cancel.is_set():
                self.progress_changed.emit()

        try:
            osam_client(device=device).pull(
                self.model_name, progress=report, cancel=self._cancel
            )
        except osam.types.PullCancelledError:
            pass
        except Exception as error:
            self.error = str(error)
        if not self._cancel.is_set():  # else stop may have deleted this
            self._ended.emit()

    def stop(self) -> None:
        # The cancel deletes the partial files and ends a stalled read. A
        # stalled TLS handshake ignores it until its 30 s timeout, so the
        # thread is left to end on its own, having written nothing.
        STOP_TIMEOUT_S: Final = 1.0
        self._cancel.set()
        self._thread.join(timeout=STOP_TIMEOUT_S)

    def _on_ended(self) -> None:
        if not self._cancel.is_set():  # else stop already took it off
            self.finished.emit()


class ModelManager(QtCore.QObject):
    _pull: _Pull | None
    _closed: bool
    _device: Device
    _catalog: dict[str, osam.types.ModelInfo] | None

    changed = QtCore.Signal()
    progress_changed = QtCore.Signal()
    remove_failed = QtCore.Signal(str)  # message

    models: dict[str, str]
    errors: dict[str, str]
    queue: list[str]
    removing: set[str]  # unusable while their files wait to be deleted

    def __init__(self, *, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        # Model names are product names, so they stay untranslated.
        self.models = {
            option.model_name: option.display_name for option in AI_ASSIST_MODEL_OPTIONS
        } | dict(AI_TEXT_MODEL_OPTIONS)
        self.errors = {}
        self.queue = []
        self.removing = set()
        self._pull = None
        self._closed = False
        self._device = "auto"
        self._catalog = None

    def set_device(self, *, device: Device) -> None:
        # Some models download other files for each device, so what is
        # ready changes with it; a download under way finishes as it started.
        self._device = device
        self.refresh()

    @property
    def active(self) -> str | None:
        return self._pull.model_name if self._pull is not None else None

    @property
    def progress(self) -> tuple[str, int, int | None]:
        return self._pull.progress if self._pull is not None else ("", 0, None)

    def catalog(self) -> dict[str, osam.types.ModelInfo]:
        # The toolbar and dialog share the same snapshot until the next refresh.
        if self._catalog is None:
            self._catalog = {
                info.name: info for info in osam_client(device=self._device).list()
            }
        return self._catalog

    def get_model_info(self, *, model_name: str) -> osam.types.ModelInfo:
        return model_info(client=osam_client(device=self._device), name=model_name)

    def is_ready(
        self,
        *,
        model_name: str,
        catalog: dict[str, osam.types.ModelInfo] | None = None,
    ) -> bool:
        # osam verifies each file before moving it into place, so presence is
        # enough; a file corrupted later fails the check on load.
        if model_name not in self.models or model_name in self.removing:
            return False
        info = (
            self.get_model_info(model_name=model_name)
            if catalog is None
            else catalog[model_name]
        )
        return info.size is not None

    def download_sizes(self) -> dict[str, int]:
        # Bytes each model downloads for this device before its first use.
        return {
            info.name: info.download_size
            for info in self.catalog().values()
            if info.name in self.models and info.download_size is not None
        }

    def get_state(
        self,
        *,
        model_name: str,
        catalog: dict[str, osam.types.ModelInfo] | None = None,
    ) -> str:
        if model_name in self.removing:
            return "deleting"
        if model_name in self.queue:
            return "queued"
        if model_name == self.active:
            return "downloading"
        if self.is_ready(model_name=model_name, catalog=catalog):
            return "downloaded"
        if model_name in self.errors:
            return "failed"
        return "missing"

    def refresh(self) -> None:
        self._catalog = None
        self.changed.emit()

    def enqueue(self, *, model_name: str) -> None:
        if (
            self._closed
            or model_name not in self.models
            or model_name in self.removing
            or self.is_ready(model_name=model_name)
        ):
            return
        if model_name == self.active or model_name in self.queue:
            return
        self.queue.append(model_name)
        self.errors.pop(model_name, None)
        self.refresh()
        self._start_next()

    def _start_next(self) -> None:
        if self._closed or self._pull is not None or not self.queue:
            return
        self._pull = _Pull(
            model_name=self.queue.pop(0), device=self._device, parent=self
        )
        self._pull.progress_changed.connect(self.progress_changed)
        self._pull.finished.connect(self._on_finished)
        self._pull.start()
        self.refresh()

    def _on_finished(self) -> None:
        assert self._pull is not None
        pull = self._pull
        self._pull = None
        if pull.error is not None:
            self.errors[pull.model_name] = pull.error
        pull.deleteLater()
        self.refresh()
        self._start_next()

    def _stop_active_pull(self) -> None:
        assert self._pull is not None
        self._pull.stop()
        self._pull.deleteLater()
        self._pull = None

    def cancel(self, *, model_name: str) -> None:
        if model_name in self.queue:
            self.queue.remove(model_name)
            self.refresh()
        elif model_name == self.active:
            self._stop_active_pull()
            self.refresh()
            self._start_next()

    def start_removing(self, *, model_name: str) -> None:
        # remove deletes its files later, once nothing holds them open.
        self.removing.add(model_name)
        self.refresh()

    def remove(self, *, model_name: str) -> None:
        if model_name in self.queue:
            self.queue.remove(model_name)
        elif model_name == self.active:
            self._stop_active_pull()
        try:
            osam_client(device=self._device).remove(model_name)
        except OSError as error:
            self.remove_failed.emit(str(error))
        finally:
            self.removing.discard(model_name)
            self.errors.pop(model_name, None)
            self.refresh()
            self._start_next()

    def shutdown(self) -> None:
        self._closed = True
        if self._pull is not None:
            self._stop_active_pull()
        self.queue.clear()
