from __future__ import annotations

import dataclasses
import itertools
import multiprocessing
import os
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

import numpy as np
from loguru import logger
from numpy.typing import NDArray
from PySide6 import QtCore
from PySide6 import QtWidgets

if TYPE_CHECKING:
    import osam

    from ._osam_session import OsamSession

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


def _run(
    session: OsamSession, request: InferenceRequest, image: NDArray[np.uint8], /
) -> list[osam.types.Annotation]:
    if request.texts is None or request.points is not None:
        # SAM3 finds every match for a box with text and one object without.
        return session.run(
            image=image,
            image_id=request.image_id,
            points=request.points,
            point_labels=request.point_labels,
            texts=request.texts,
        ).annotations
    # ponytail: SAM3 reads only the first text of a prompt, so it runs once per
    # text, reusing the cached image embedding. Drop this once osam's SAM3 takes
    # several texts.
    batches: list[list[str]] = (
        [[text] for text in request.texts]
        if request.model_name.startswith("sam3:")
        else [request.texts]
    )
    return [
        annotation
        for texts in batches
        for annotation in session.run(
            image=image, image_id=request.image_id, texts=texts
        ).annotations
    ]


def serve(
    requests: Connection, responses: Connection, providers: str | None, /
) -> None:
    # Answers each ("run", id, request) with ("device", id, device), once the
    # model loads, then ("done", id, annotations), or ("error" | "fault", id,
    # message), where a fault comes from ONNX Runtime and may be the device's.
    from ._osam_session import get_osam_session  # noqa: PLC0415 -- child only

    if providers is not None:
        os.environ["OSAM_ONNX_PROVIDERS"] = providers
    image: NDArray[np.uint8] | None = None
    image_id: str | None = None
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
            session = get_osam_session(model_name=request.model_name)
            responses.send(("device", request_id, session.device))
            annotations = _run(session, request, image)
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


@dataclasses.dataclass
class _Active:
    request_id: int
    channel: object
    job: object
    request: InferenceRequest  # with its image, to retry on a new worker
    deadline: float
    device: str | None = None  # None until the model loads


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

    finished = QtCore.Signal(object, object)  # job, list[osam.types.Annotation]
    failed = QtCore.Signal(object, str)  # job, message
    activity_changed = QtCore.Signal()  # job or device changed

    def __init__(
        self,
        *,
        parent: QtCore.QObject | None = None,
        target: Callable[[Connection, Connection, str | None], None] = serve,
        timeout_s: float = _TIMEOUT_S,
    ) -> None:
        super().__init__(parent)
        self._target = target
        self._timeout_s = timeout_s
        self._context = multiprocessing.get_context("spawn")
        self._process: BaseProcess | None = None
        self._outbox: queue.SimpleQueue | None = None
        self._inbox: queue.SimpleQueue = queue.SimpleQueue()
        self._sent_image_id: str | None = None
        self._device: Literal["auto", "cpu"] = "auto"
        self._fell_back = False
        self._process_on_cpu = False
        self._pending: dict[object, tuple[object, InferenceRequest]] = {}
        self._active: _Active | None = None
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

    @property
    def job(self) -> object:
        # The running job; None while idle.
        return None if self._active is None else self._active.job

    @property
    def device(self) -> str | None:
        # Where the running job's model loaded; None while idle or loading.
        return None if self._active is None else self._active.device

    def set_device(self, device: Literal["auto", "cpu"], /) -> None:
        # The running job finishes where it is; the next one starts a worker
        # on this device. Choosing a device again retries the GPU.
        self._device = device
        self._fell_back = False

    @property
    def _cpu_only(self) -> bool:
        return self._device == "cpu" or self._fell_back

    def _set_active(self, active: _Active | None, /) -> None:
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
            self._set_active(None)

    def _start_next(self) -> None:
        if self._active is not None or not self._pending:
            return
        channel = next(iter(self._pending))
        job, request = self._pending.pop(channel)
        try:
            outbox = self._ensure_process()
            sent = request
            if request.image_id == self._sent_image_id:
                sent = dataclasses.replace(request, image=None)
            request_id = next(self._request_ids)
            outbox.put(("run", request_id, sent))
        except Exception as error:
            logger.opt(exception=error).error("Failed to start AI inference")
            self._stop_process()
            self.failed.emit(job, f"{type(error).__name__}: {error}")
            self._start_next()
            return
        self._sent_image_id = request.image_id
        self._set_active(
            _Active(
                request_id=request_id,
                channel=channel,
                job=job,
                request=request,
                deadline=time.monotonic() + self._timeout_s,
                device="cpu" if self._process_on_cpu else None,
            )
        )
        self._timer.start()

    def _ensure_process(self) -> queue.SimpleQueue:
        if (
            self._process is not None
            and self._process.is_alive()
            and self._process_on_cpu == self._cpu_only
        ):
            assert self._outbox is not None
            return self._outbox
        self._stop_process()
        child_requests, requests = self._context.Pipe(duplex=False)
        responses, child_responses = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=self._target,
            args=(
                child_requests,
                child_responses,
                "CPUExecutionProvider" if self._cpu_only else None,
            ),
            daemon=True,
        )
        try:
            process.start()
        finally:
            child_requests.close()
            child_responses.close()
        self._process = process
        self._process_on_cpu = self._cpu_only
        self._outbox = queue.SimpleQueue()
        self._inbox = queue.SimpleQueue()
        threading.Thread(
            target=_pump_out, args=(requests, self._outbox), daemon=True
        ).start()
        threading.Thread(
            target=_pump_in, args=(responses, self._inbox), daemon=True
        ).start()
        logger.debug("Started AI worker process pid={}", process.pid)
        return self._outbox

    def _stop_process(self) -> None:
        self._timer.stop()
        self._sent_image_id = None
        if self._outbox is not None:
            self._outbox.put(None)  # closes the requests end, so serve returns
            self._outbox = None
        process, self._process = self._process, None
        if process is None:
            return
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
        self._set_active(None)
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
        assert self._process is not None
        while not self._inbox.empty():  # the only reader, so no race
            kind, request_id, payload = self._inbox.get_nowait()
            if request_id != active.request_id:
                continue
            if kind == "device":
                active.device = payload
                self.activity_changed.emit()
            else:
                return kind, payload
        if not self._process.is_alive():
            error = f"AI worker exited with code {self._process.exitcode}"
        elif time.monotonic() > active.deadline:
            error = f"AI inference timed out after {self._timeout_s:.0f} s"
        else:
            return None
        logger.error("{}; restarting the AI worker", error)
        self._stop_process()
        return "fault", error
