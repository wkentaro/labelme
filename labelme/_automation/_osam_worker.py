from __future__ import annotations

import dataclasses
import functools
import itertools
import queue
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING
from typing import Any
from typing import Final
from typing import Literal
from typing import cast

import numpy as np
from loguru import logger
from numpy.typing import NDArray
from PySide6 import QtCore
from PySide6 import QtWidgets

from .._ai_models import Device
from .._ai_models import osam_client

if TYPE_CHECKING:
    import osam

WorkerStage = Literal["starting", "loading", "generating"]
# Called as each stage starts, with the model's device once it has loaded.
ProgressCallback = Callable[[WorkerStage, str | None], None]


@dataclasses.dataclass(frozen=True)
class InferenceRequest:
    model_name: str
    image: NDArray[np.uint8]
    points: NDArray[np.floating] | None = None
    point_labels: NDArray[np.intp] | None = None
    texts: list[str] | None = None


def _segment_kwargs(*, request: InferenceRequest) -> dict[str, Any]:
    # The canvas's prompt as osam takes it: labels 0 and 1 are points and 2
    # and 3 a box's corners, or, with texts, 2 and 3 an example box's and 4
    # and 5 a counter-example's.
    points = request.points
    labels = request.point_labels
    if request.texts is not None:
        examples: dict[str, NDArray] = {}
        if points is not None and labels is not None and len(points):
            # Corners come in pairs; SAM3 reads the boxes by their edges, as
            # drawn.
            is_example = labels[::2] == 2  # noqa: PLR2004
            examples = {
                "example_boxes": points.reshape(-1, 4),
                "example_box_labels": is_example.astype(int),
            }
        return {
            "texts": request.texts,
            **examples,
            # Every candidate; the user's Score and IoU filter later.
            "iou_threshold": 1.0,
            "score_threshold": 0.01,
            "max_annotations": 1000,
        }
    assert points is not None and labels is not None
    # The canvas spans pixel c from c to c + 1, and SAM decoders read an
    # integer as a pixel center.
    points = points - 0.5
    is_point = labels < 2  # noqa: PLR2004
    return {
        "points": points[is_point] if is_point.any() else None,
        "point_labels": labels[is_point] if is_point.any() else None,
        "box": points[~is_point].ravel() if (~is_point).any() else None,
    }


def _run(
    *,
    client: osam.Client,
    request: InferenceRequest,
    progress: ProgressCallback,
) -> list[osam.types.Annotation]:
    model = request.model_name
    device = next((r.device for r in client.ps() if r.name == model), None)
    if device is None:
        progress("loading", None)
        t_start = time.perf_counter()
        running = client.load(model, keep_alive=-1)
        logger.info(
            "Loaded {!r} in {:.0f} ms", model, (time.perf_counter() - t_start) * 1000
        )
        device = None if running is None else running.device
    progress("generating", device)
    t_start = time.perf_counter()
    annotations = client.segment(
        model, request.image, keep_alive=-1, **_segment_kwargs(request=request)
    )
    logger.info(
        "Segmented with {!r} in {:.0f} ms",
        model,
        (time.perf_counter() - t_start) * 1000,
    )
    return annotations


@dataclasses.dataclass
class _Active:
    request_id: int
    job: object
    model_name: str
    device: str | None = None  # None until the model loads
    stage: WorkerStage | None = None


class OsamWorker(QtCore.QObject):
    """Runs OSAM on its private server from one thread, so a slow, hung or
    crashed model never blocks or takes down the UI.

    Each submit names a channel; a newer submit on a channel replaces its
    request that has not started. A job that a caller replaced or abandoned
    still finishes; callers drop results for jobs they no longer expect.
    """

    _device: Device
    _pending: dict[object, tuple[object, InferenceRequest]]
    _active: _Active | None
    _request_ids: itertools.count[int]
    _inbox: queue.SimpleQueue[tuple[int, Device, InferenceRequest] | None]
    # The thread's client and its device, which release closes from the UI,
    # and the first request id it still runs.
    _lock: threading.Lock
    _client: tuple[Device, osam.Client] | None
    _first_live_id: int

    finished = QtCore.Signal(object, object)  # job, list[osam.types.Annotation]
    failed = QtCore.Signal(object, str)  # job, message
    # Before failing the job: the model's files for the device, None for the
    # one osam picks, aren't on disk, such as the CPU's after a fall back.
    not_pulled = QtCore.Signal(object)  # device
    activity_changed = QtCore.Signal()  # job, queued, stage or device changed
    # From the thread, so queued: request id, kind, payload.
    _reported = QtCore.Signal(int, str, object)

    def __init__(self, *, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._device = "auto"
        self._pending = {}
        self._active = None
        self._request_ids = itertools.count()
        self._inbox = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._client = None
        self._first_live_id = 0
        self._reported.connect(self._on_reported)
        threading.Thread(target=self._serve, name="osam-worker", daemon=True).start()

    def submit(
        self, *, channel: object, job: object, request: InferenceRequest
    ) -> None:
        self._pending.pop(channel, None)
        self._pending[channel] = (job, request)
        self._start_next()
        if channel in self._pending:
            self.activity_changed.emit()  # queued behind the running job

    def cancel(self, *, channel: object) -> None:
        # Drops the channel's request that has not started; a running one
        # still finishes.
        self._pending.pop(channel, None)

    @property
    def job(self) -> object:
        # The running job; None while idle.
        return None if self._active is None else self._active.job

    @property
    def device(self) -> str | None:
        # Where the running job's model loaded; None while idle or loading.
        return None if self._active is None else self._active.device

    @property
    def stage(self) -> WorkerStage | None:
        return None if self._active is None else self._active.stage

    @property
    def model_name(self) -> str | None:
        return None if self._active is None else self._active.model_name

    def set_device(self, *, device: Device) -> None:
        # The running job finishes where it is; the next one starts a server
        # on this device.
        self._device = device

    def release(self) -> None:
        # Stops the server, freeing every model it loaded; the next submit
        # starts another. Jobs it drops fail, so no caller waits for them.
        jobs = [job for job, _ in self._pending.values()]
        if self._active is not None:
            jobs.insert(0, self._active.job)
        self._drop_requests()
        self._close_client()  # a running request fails, unreported
        for job in jobs:
            self.failed.emit(job, "AI worker stopped")

    def shutdown(self) -> None:
        # Returns at once: the thread closes the server, which also exits
        # with this process, so quitting never waits on a running request.
        self._drop_requests()
        self._inbox.put(None)

    def _drop_requests(self) -> None:
        # The thread skips the dropped ones, and their results go unreported.
        self._pending.clear()
        with self._lock:
            self._first_live_id = next(self._request_ids)
        if self._active is not None:
            self._set_active(active=None)

    def _close_client(self) -> None:
        with self._lock:
            client, self._client = self._client, None
        if client is not None:
            client[1].close()

    def _set_active(self, *, active: _Active | None) -> None:
        self._active = active
        self.activity_changed.emit()

    def _start_next(self) -> None:
        if self._active is not None or not self._pending:
            return
        channel = next(iter(self._pending))
        job, request = self._pending.pop(channel)
        request_id = next(self._request_ids)
        self._inbox.put((request_id, self._device, request))
        self._set_active(
            active=_Active(
                request_id=request_id, job=job, model_name=request.model_name
            )
        )

    def _serve(self) -> None:
        from osam import ResponseError  # noqa: PLC0415 -- deferred

        while (item := self._inbox.get()) is not None:
            request_id, device, request = item
            progress = functools.partial(self._report_stage, request_id)
            try:
                client = self._client_for(
                    request_id=request_id, device=device, progress=progress
                )
                if client is None:
                    continue  # released
                annotations = _run(client=client, request=request, progress=progress)
            except Exception as error:
                if (
                    isinstance(error, ResponseError)
                    and error.code == "model_not_pulled"
                ):
                    logger.warning("AI inference failed: {}", error)
                    self._reported.emit(
                        request_id, "not_pulled", (str(error), error.device)
                    )
                    continue
                logger.opt(exception=error).error("AI inference failed")
                self._reported.emit(
                    request_id, "error", f"{type(error).__name__}: {error}"
                )
            else:
                self._reported.emit(request_id, "done", annotations)
        self._close_client()

    def _report_stage(
        self, request_id: int, stage: WorkerStage, device: str | None, /
    ) -> None:
        self._reported.emit(request_id, "stage", (stage, device))

    def _client_for(
        self,
        *,
        request_id: int,
        device: Device,
        progress: ProgressCallback,
    ) -> osam.Client | None:
        # ponytail: one timeout covers each of loading and running, so a
        # first run that compiles a model counts as slow, not hung. Split it
        # per stage if a real hang needs faster detection.
        TIMEOUT_S: Final = 600.0

        with self._lock:
            if request_id < self._first_live_id:
                return None
            if self._client is not None and self._client[0] == device:
                return self._client[1]
            stale, self._client = self._client, None
        if stale is not None:
            stale[1].close()
        progress("starting", None)
        # Started unlocked, so release never waits on a server starting up.
        # A private server: a crash or a 500 restarts it and retries once, and
        # a timeout restarts it. Loading downloads nothing; downloads go
        # through ModelManager, which asks first and shows progress.
        client = osam_client(
            device=device,
            in_process=False,
            max_loaded_models=2,
            timeout=TIMEOUT_S,
            auto_pull=False,
        )
        with self._lock:
            if request_id >= self._first_live_id:
                self._client = (device, client)
                return client
        client.close()  # released while it started
        return None

    def _on_reported(self, request_id: int, kind: str, payload: object, /) -> None:
        active = self._active
        if active is None or active.request_id != request_id:
            return  # released
        if kind == "stage":
            active.stage, active.device = cast(tuple[WorkerStage, str | None], payload)
            self.activity_changed.emit()
            return
        # A result changes what the user edits. A modal dialog, such as a
        # label edit, runs its own event loop, so the result waits it out.
        if QtWidgets.QApplication.activeModalWidget() is not None:
            QtCore.QTimer.singleShot(
                100, self, lambda: self._on_reported(request_id, kind, payload)
            )
            return
        self._set_active(active=None)
        if kind == "done":
            self.finished.emit(active.job, payload)
        elif kind == "not_pulled":
            message, device = cast(tuple[str, str | None], payload)
            self.not_pulled.emit(device)
            self.failed.emit(active.job, message)
        else:
            self.failed.emit(active.job, cast(str, payload))
        self._start_next()
