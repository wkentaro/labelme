from __future__ import annotations

import dataclasses
import itertools
import multiprocessing
import queue
import threading
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import TYPE_CHECKING
from typing import Any
from typing import Final
from typing import Literal
from typing import NamedTuple

import numpy as np
from loguru import logger
from numpy.typing import NDArray
from PySide6 import QtCore
from PySide6 import QtWidgets

from .._ai_models import Device
from .._ai_models import model_info

if TYPE_CHECKING:
    import osam

InferenceStage = Literal["loading", "encoding", "generating"]
WorkerStage = Literal["starting"] | InferenceStage
# Called as each stage starts, with the model's device once it has loaded.
ProgressCallback = Callable[[InferenceStage, str | None], None]

# ponytail: one deadline covers spawning, loading and running, so a first run
# that compiles a model counts as slow, not hung. Split it per stage if a
# real hang needs faster detection.
_TIMEOUT_S: Final = 600.0


@dataclasses.dataclass(frozen=True)
class InferenceRequest:
    model_name: str
    image_id: str
    # None once the worker holds the image for image_id.
    image: NDArray[np.uint8] | None
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
    image: NDArray[np.uint8],
    encoded: dict[str, str],
    progress: ProgressCallback,
) -> list[osam.types.Annotation]:
    # ponytail: encoded holds the image each model last segmented, a guess at
    # osam's embedding cache for the progress label; a revisited image osam
    # still holds shows as encoding. Ask osam if the label must be exact.
    model = request.model_name
    info = model_info(client=client, name=model)
    devices = {running.name: running.device for running in client.ps()}
    if model not in devices:
        if info.size is None:
            # Such as after a fall back to the CPU, for which some models
            # download other files; osam would download them unasked.
            raise RuntimeError(f"{model} is not downloaded for this device")
        progress("loading", None)
        client.load(model, keep_alive=-1)
        devices = {running.name: running.device for running in client.ps()}
    # Models that take points encode an image once for its prompts; the
    # others run whole on each.
    stage: InferenceStage = (
        "encoding"
        if "points" in info.prompt_kinds and encoded.get(model) != request.image_id
        else "generating"
    )
    progress(stage, devices[model])
    t_start = time.perf_counter()
    annotations = client.segment(
        model, image, keep_alive=-1, **_segment_kwargs(request=request)
    )
    encoded[model] = request.image_id
    logger.info(
        "Segmented with {!r} in {:.0f} ms",
        model,
        (time.perf_counter() - t_start) * 1000,
    )
    return annotations


def serve(requests: Connection, responses: Connection, device: Device, /) -> None:
    # Answers each ("run", id, request) with ("stage", id, (stage, device)) as
    # each stage starts, the device once the model loads, then ("done", id,
    # annotations), or ("error" | "fault", id, message), where a fault comes
    # from ONNX Runtime and may be the device's.
    from .._ai_models import osam_client  # noqa: PLC0415 -- child only

    client = osam_client(device=device, max_loaded_models=2)
    image: NDArray[np.uint8] | None = None
    image_id: str | None = None
    encoded: dict[str, str] = {}
    while True:
        try:
            message = requests.recv()
        except EOFError:
            return
        _, request_id, request = message
        try:
            if request.image is not None:
                image, image_id = request.image, request.image_id
            if image is None or image_id != request.image_id:
                raise RuntimeError(f"image {request.image_id!r} was never sent")
            annotations = _run(
                client=client,
                request=request,
                image=image,
                encoded=encoded,
                progress=lambda stage, device: responses.send(
                    ("stage", request_id, (stage, device))
                ),
            )
        except Exception as error:
            logger.opt(exception=error).error("AI inference failed")
            kind = (
                "fault" if type(error).__module__.startswith("onnxruntime") else "error"
            )
            responses.send((kind, request_id, f"{type(error).__name__}: {error}"))
        else:
            responses.send(("done", request_id, annotations))


# The UI thread never touches a pipe: a large image or mask blocks its
# transfer until the other side reads, which a starting, hung or dead worker
# may never do. Each pump owns and closes its end.
def _pump_out(connection: Connection, outbox: queue.SimpleQueue, /) -> None:
    with connection:
        while (message := outbox.get()) is not None:
            try:
                connection.send(message)
            except OSError:
                return  # the worker stopped; polling reports it


def _pump_in(connection: Connection, inbox: queue.SimpleQueue, /) -> None:
    with connection:
        while True:
            try:
                inbox.put(connection.recv())
            except (EOFError, OSError):
                return


class _WorkerProcess(NamedTuple):
    process: BaseProcess
    on_cpu: bool
    outbox: queue.SimpleQueue  # carried to the worker by _pump_out
    inbox: queue.SimpleQueue  # filled from the worker by _pump_in
    # The image the worker holds, so a request for it is sent without one.
    sent_image_id: str | None = None


@dataclasses.dataclass
class _Active:
    request_id: int
    channel: object
    job: object
    request: InferenceRequest  # with its image, to retry on a new worker
    deadline: float
    device: str | None = None  # None until the model loads
    # What the worker reported it is doing; "starting" while a new worker
    # spawns for this job, None until a warm worker reports.
    stage: WorkerStage | None = None
    stage_started_at: float = dataclasses.field(default_factory=time.monotonic)


def _log_stage(*, active: _Active) -> None:
    # Measured here, as the worker's own log never reaches the app's. Only a
    # slow stage, so previews under a moving cursor never flood the log.
    SLOW_STAGE_MS: Final = 1000
    elapsed_ms = (time.monotonic() - active.stage_started_at) * 1000
    if active.stage is None or elapsed_ms < SLOW_STAGE_MS:
        return
    logger.info(
        "AI {!r} {} on {} took {:.0f} ms",
        active.request.model_name,
        active.stage,
        active.device or "an unknown device",
        elapsed_ms,
    )


class OsamWorker(QtCore.QObject):
    """Runs OSAM in a child process, so a slow, hung or crashed model never
    blocks or takes down the UI.

    Each submit names a channel; a newer submit on a channel replaces its
    request that has not started. A job that a caller replaced or abandoned
    still finishes; callers drop results for jobs they no longer expect.

    A crash, hang or ONNX Runtime error off the CPU restarts the worker on
    CPU and retries the job there once; the worker stays on CPU until the
    device is set again.
    """

    _target: Callable[[Connection, Connection, Device], None]
    _timeout_s: float
    _context: multiprocessing.context.SpawnContext
    _worker: _WorkerProcess | None
    _device: Device
    _fell_back: bool
    _pending: dict[object, tuple[object, InferenceRequest]]
    _active: _Active | None
    _request_ids: itertools.count[int]
    _timer: QtCore.QTimer

    finished = QtCore.Signal(object, object)  # job, list[osam.types.Annotation]
    failed = QtCore.Signal(object, str)  # job, message
    activity_changed = QtCore.Signal()  # job, queued, stage or device changed

    def __init__(
        self,
        *,
        parent: QtCore.QObject | None = None,
        target: Callable[[Connection, Connection, Device], None] = serve,
        timeout_s: float = _TIMEOUT_S,
    ) -> None:
        super().__init__(parent)
        self._target = target
        self._timeout_s = timeout_s
        self._context = multiprocessing.get_context("spawn")
        self._worker = None
        self._device = "auto"
        self._fell_back = False
        self._pending = {}
        self._active = None
        self._request_ids = itertools.count()
        self._timer = QtCore.QTimer(self)
        POLL_INTERVAL_MS: Final = 20
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

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
        # None while idle or before a warm worker reports.
        return None if self._active is None else self._active.stage

    @property
    def model_name(self) -> str | None:
        return None if self._active is None else self._active.request.model_name

    def set_device(self, *, device: Device) -> None:
        # The running job finishes where it is; the next one starts a worker
        # on this device. Choosing a device again retries the GPU.
        self._device = device
        self._fell_back = False

    @property
    def _cpu_only(self) -> bool:
        return self._device == "cpu" or self._fell_back

    def _set_active(self, *, active: _Active | None) -> None:
        self._active = active
        self.activity_changed.emit()

    def release(self) -> None:
        # Stops the worker, freeing every model it loaded; the next submit
        # restarts it. Jobs it drops fail, so no caller waits for them.
        jobs = [job for job, _ in self._pending.values()]
        if self._active is not None:
            jobs.insert(0, self._active.job)
        self.shutdown()
        for job in jobs:
            self.failed.emit(job, "AI worker stopped")

    def shutdown(self) -> None:
        self._pending.clear()
        self._stop_process()
        if self._active is not None:
            self._set_active(active=None)

    def _start_next(self) -> None:
        if self._active is not None or not self._pending:
            return
        channel = next(iter(self._pending))
        job, request = self._pending.pop(channel)
        previous = self._worker
        try:
            worker = self._ensure_process()
            sent = request
            if request.image_id == worker.sent_image_id:
                sent = dataclasses.replace(request, image=None)
            request_id = next(self._request_ids)
            worker.outbox.put(("run", request_id, sent))
        except Exception as error:
            logger.opt(exception=error).error("Failed to start AI inference")
            self._stop_process()
            self.failed.emit(job, f"{type(error).__name__}: {error}")
            self._start_next()
            return
        self._worker = worker._replace(sent_image_id=request.image_id)
        self._set_active(
            active=_Active(
                request_id=request_id,
                channel=channel,
                job=job,
                request=request,
                deadline=time.monotonic() + self._timeout_s,
                device="cpu" if worker.on_cpu else None,
                stage="starting" if worker is not previous else None,
            )
        )
        self._timer.start()

    def _ensure_process(self) -> _WorkerProcess:
        if (
            (worker := self._worker) is not None
            and worker.process.is_alive()
            and worker.on_cpu == self._cpu_only
        ):
            return worker
        self._stop_process()
        child_requests, requests = self._context.Pipe(duplex=False)
        responses, child_responses = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=self._target,
            args=(
                child_requests,
                child_responses,
                "cpu" if self._cpu_only else self._device,
            ),
            daemon=True,
        )
        try:
            process.start()
        finally:
            child_requests.close()
            child_responses.close()
        # Kept before the pumps start, so a failure stops the process.
        self._worker = worker = _WorkerProcess(
            process=process,
            on_cpu=self._cpu_only,
            outbox=queue.SimpleQueue(),
            inbox=queue.SimpleQueue(),
        )
        threading.Thread(
            target=_pump_out, args=(requests, worker.outbox), daemon=True
        ).start()
        threading.Thread(
            target=_pump_in, args=(responses, worker.inbox), daemon=True
        ).start()
        logger.debug("Started AI worker process pid={}", process.pid)
        return worker

    def _stop_process(self) -> None:
        self._timer.stop()
        worker, self._worker = self._worker, None
        if worker is None:
            return
        worker.outbox.put(None)  # closes the requests end, so serve returns
        process = worker.process
        process.join(timeout=0.1)
        if process.is_alive():
            process.kill()
            process.join(timeout=1.0)
        if not process.is_alive():
            process.close()

    def _poll(self) -> None:
        active = self._active
        if active is None:
            self._timer.stop()
            return
        # A result changes what the user edits. A modal dialog, such as a
        # label edit, runs its own event loop, so the result waits it out.
        if QtWidgets.QApplication.activeModalWidget() is not None:
            return
        outcome = self._receive(active=active)
        if outcome is None:
            return
        _log_stage(active=active)
        self._set_active(active=None)
        kind, payload = outcome
        if kind == "done":
            self.finished.emit(active.job, payload)
        elif kind == "fault" and active.device != "cpu":
            self._fall_back_to_cpu(active=active, error=payload)
        else:
            self.failed.emit(active.job, payload)
        self._start_next()

    def _fall_back_to_cpu(self, *, active: _Active, error: str) -> None:
        logger.warning(
            "AI inference failed on {}: {}; retrying on CPU",
            active.device or "an unknown device",
            error,
        )
        self._fell_back = True
        self._stop_process()
        if active.channel in self._pending:
            self.failed.emit(active.job, error)  # a newer job replaces it
        else:
            self._pending = {
                active.channel: (active.job, active.request),
                **self._pending,
            }

    def _receive(self, *, active: _Active) -> tuple[str, Any] | None:
        worker = self._worker
        assert worker is not None
        while not worker.inbox.empty():  # the only reader, so no race
            kind, request_id, payload = worker.inbox.get_nowait()
            if request_id != active.request_id:
                continue
            if kind == "stage":
                stage, device = payload
                if device is not None:
                    active.device = device  # where the stage just ended ran
                _log_stage(active=active)
                active.stage, active.stage_started_at = stage, time.monotonic()
                self.activity_changed.emit()
            else:
                return kind, payload
        if not worker.process.is_alive():
            error = f"AI worker exited with code {worker.process.exitcode}"
        elif time.monotonic() > active.deadline:
            error = f"AI inference timed out after {self._timeout_s:.0f} s"
        else:
            return None
        logger.error("{}; restarting the AI worker", error)
        self._stop_process()
        return "fault", error
