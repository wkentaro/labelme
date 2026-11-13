from __future__ import annotations

import builtins
import dataclasses
import multiprocessing
import os
import struct
import sys
import time
from collections.abc import Iterator
from multiprocessing.connection import Connection
from typing import Any
from typing import Final

import numpy as np
import osam
import pytest
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._automation import _osam_worker
from labelme._automation._osam_worker import InferenceRequest
from labelme._automation._osam_worker import OsamWorker

_IMAGE: Final = np.zeros((2, 3, 3), dtype=np.uint8)
_WAIT_MS: Final = 30_000


def _scripted_serve(
    requests: Connection, responses: Connection, device: str, /
) -> None:
    # Spawned in the worker: the model name scripts how the request goes. A
    # "gpu-" model runs on WebGPU and fails there unless the worker is on CPU.
    cpu_only = device == "cpu"
    while True:
        try:
            _, request_id, request = requests.recv()
        except EOFError:
            return
        on_gpu = request.model_name.startswith("gpu-") and not cpu_only
        if request.model_name == "stages":
            responses.send(("stage", request_id + 1, ("encoding", "stale")))
            responses.send(("stage", request_id, ("loading", None)))
            responses.send(("stage", request_id, ("encoding", "cpu")))
        responses.send(
            ("stage", request_id, ("generating", "webgpu" if on_gpu else "cpu"))
        )
        if on_gpu and request.model_name == "gpu-crash":
            os._exit(3)
        if on_gpu and request.model_name == "gpu-fault":
            responses.send(("fault", request_id, "Fail: device lost"))
            continue
        if request.model_name == "cpu-fault":
            responses.send(("fault", request_id, "Fail: bad model"))
            continue
        if request.model_name == "crash":
            os._exit(3)
        if request.model_name == "hang":
            time.sleep(60)
        if request.model_name == "stall":  # a response cut off mid-transfer
            os.write(responses.fileno(), struct.pack("!i", 1024))
            time.sleep(60)
        if request.model_name == "error":
            responses.send(("error", request_id, "ValueError: bad prompt"))
            continue
        result = {
            "pid": os.getpid(),
            "sent_image": request.image is not None,
            "cpu_only": cpu_only,
        }
        responses.send(("done", request_id, result))


def _late_serve(requests: Connection, responses: Connection, device: str, /) -> None:
    time.sleep(1)  # a worker still importing reads nothing yet
    _scripted_serve(requests, responses, device)


def _request(*, model_name: str = "ok", image_id: str = "img") -> InferenceRequest:
    return InferenceRequest(model_name=model_name, image_id=image_id, image=_IMAGE)


@pytest.fixture
def worker(*, qtbot: QtBot) -> Iterator[OsamWorker]:  # noqa: ARG001 -- needs a QApplication
    instance = OsamWorker(target=_scripted_serve, timeout_s=_WAIT_MS / 1000)
    results: list[tuple[str, object, Any]] = []
    instance.finished.connect(lambda job, r: results.append(("done", job, r)))
    instance.failed.connect(lambda job, m: results.append(("error", job, m)))
    instance.results = results  # ty: ignore[unresolved-attribute]
    yield instance
    instance.shutdown()


def _results(*, worker: OsamWorker) -> list[tuple[str, object, Any]]:
    return worker.results  # ty: ignore[unresolved-attribute]


def _wait_for(*, qtbot: QtBot, worker: OsamWorker, count: int) -> None:
    qtbot.waitUntil(lambda: len(_results(worker=worker)) >= count, timeout=_WAIT_MS)


def test_sends_an_image_once_per_image_id(*, worker: OsamWorker, qtbot: QtBot) -> None:
    for job in ["a", "b"]:
        worker.submit(channel=job, job=job, request=_request())
    worker.submit(channel="c", job="c", request=_request(image_id="other"))
    _wait_for(qtbot=qtbot, worker=worker, count=3)

    assert [
        (kind, job, r["sent_image"]) for kind, job, r in _results(worker=worker)
    ] == [
        ("done", "a", True),
        ("done", "b", False),
        ("done", "c", True),
    ]
    assert worker._active is None
    assert not worker._pending


def test_newer_submit_replaces_a_waiting_one_on_its_channel(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="finalize", job="running", request=_request())
    worker.submit(channel="preview", job="stale", request=_request())
    worker.submit(channel="preview", job="latest", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=2)

    assert [job for _, job, _ in _results(worker=worker)] == ["running", "latest"]


def test_reports_a_model_error_and_keeps_the_worker(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="x", job="first", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=1)
    worker.submit(channel="x", job="bad", request=_request(model_name="error"))
    worker.submit(channel="y", job="after", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=3)

    (_, _, first), bad, (_, _, after) = _results(worker=worker)
    assert bad == ("error", "bad", "ValueError: bad prompt")
    assert after["pid"] == first["pid"]


@pytest.mark.parametrize(
    ("model_name", "message"),
    [
        ("crash", "AI worker exited with code 3"),
        ("hang", "AI inference timed out after 1 s"),
        pytest.param(
            "stall",
            "AI inference timed out after 1 s",
            marks=pytest.mark.skipif(
                sys.platform == "win32",
                reason="Windows pipes deliver whole messages, so none stalls midway",
            ),
        ),
    ],
)
def test_restarts_the_worker_after_a_crash_or_hang(
    *, qtbot: QtBot, model_name: str, message: str
) -> None:
    # The deadline also covers spawning, which takes seconds on CI, so only
    # the broken job runs under the short one.
    worker = OsamWorker(target=_scripted_serve, timeout_s=_WAIT_MS / 1000)
    results: list[tuple[object, Any]] = []
    worker.finished.connect(lambda job, r: results.append((job, r)))
    worker.failed.connect(lambda job, m: results.append((job, m)))
    try:
        worker.submit(channel="x", job="warm", request=_request())
        qtbot.waitUntil(lambda: len(results) == 1, timeout=_WAIT_MS)
        worker._timeout_s = 1
        worker.submit(
            channel="x", job="broken", request=_request(model_name=model_name)
        )
        qtbot.waitUntil(lambda: len(results) == 2, timeout=_WAIT_MS)
        worker._timeout_s = _WAIT_MS / 1000
        worker.submit(channel="y", job="next", request=_request())
        qtbot.waitUntil(lambda: len(results) == 3, timeout=_WAIT_MS)
    finally:
        worker.shutdown()

    assert results[1] == ("broken", message)
    job, result = results[2]
    assert job == "next"
    assert result["sent_image"]  # the new worker never saw the image
    assert result["pid"] != results[0][1]["pid"]


def test_submit_returns_before_a_late_worker_reads_a_large_image(
    *, qtbot: QtBot
) -> None:
    worker = OsamWorker(target=_late_serve)
    results: list[tuple[object, Any]] = []
    worker.finished.connect(lambda job, r: results.append((job, r)))
    image = np.zeros((2000, 2000, 3), dtype=np.uint8)  # far past a pipe buffer
    try:
        started = time.monotonic()
        worker.submit(
            channel="x",
            job="big",
            request=InferenceRequest(model_name="ok", image_id="img", image=image),
        )
        assert time.monotonic() - started < 0.5
        qtbot.waitUntil(lambda: len(results) == 1, timeout=_WAIT_MS)
    finally:
        worker.shutdown()

    assert results[0][0] == "big"


def test_holds_results_while_a_modal_dialog_is_open(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    # A label edit or a warning: its result would open a second dialog or
    # change the Shapes under it.
    dialog = QtWidgets.QDialog()
    dialog.setModal(True)
    dialog.show()
    worker.submit(channel="x", job="job", request=_request())
    qtbot.wait(1000)
    assert _results(worker=worker) == []

    dialog.close()
    _wait_for(qtbot=qtbot, worker=worker, count=1)
    assert _results(worker=worker)[0][:2] == ("done", "job")


@pytest.mark.parametrize("model_name", ["gpu-crash", "gpu-fault"])
def test_retries_a_gpu_failure_once_on_cpu(
    *, worker: OsamWorker, qtbot: QtBot, model_name: str
) -> None:
    worker.submit(channel="x", job="job", request=_request(model_name=model_name))
    _wait_for(qtbot=qtbot, worker=worker, count=1)
    worker.submit(channel="x", job="later", request=_request(model_name=model_name))
    _wait_for(qtbot=qtbot, worker=worker, count=2)

    (kind, job, result), (_, _, later) = _results(worker=worker)
    assert (kind, job) == ("done", "job")
    assert result["cpu_only"]
    assert result["sent_image"]  # the CPU worker gets the image again
    assert later["pid"] == result["pid"]  # it stays on CPU


def test_fails_a_cpu_fault_without_retrying(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="x", job="job", request=_request(model_name="cpu-fault"))
    worker.submit(channel="y", job="next", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=2)

    (kind, job, message), (_, _, after) = _results(worker=worker)
    assert (kind, job, message) == ("error", "job", "Fail: bad model")
    assert not after["cpu_only"]


def test_a_newer_job_replaces_the_retry(*, worker: OsamWorker, qtbot: QtBot) -> None:
    worker.submit(channel="x", job="old", request=_request(model_name="gpu-crash"))
    worker.submit(channel="x", job="new", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=2)

    (kind, job, message), (_, new_job, result) = _results(worker=worker)
    assert (kind, job, message) == ("error", "old", "AI worker exited with code 3")
    assert new_job == "new"
    assert result["cpu_only"]


def test_set_device_restarts_the_worker_for_the_next_job(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="x", job="gpu", request=_request(model_name="gpu-ok"))
    _wait_for(qtbot=qtbot, worker=worker, count=1)
    worker.set_device(device="cpu")
    worker.submit(channel="x", job="cpu", request=_request(model_name="gpu-ok"))
    _wait_for(qtbot=qtbot, worker=worker, count=2)

    (_, _, on_gpu), (_, _, on_cpu) = _results(worker=worker)
    assert not on_gpu["cpu_only"]
    assert on_cpu["cpu_only"]
    assert on_cpu["pid"] != on_gpu["pid"]


def test_set_device_retries_the_gpu_after_a_fallback(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="x", job="job", request=_request(model_name="gpu-fault"))
    _wait_for(qtbot=qtbot, worker=worker, count=1)
    worker.set_device(device="auto")
    worker.submit(channel="x", job="next", request=_request(model_name="gpu-ok"))
    _wait_for(qtbot=qtbot, worker=worker, count=2)

    assert _results(worker=worker)[0][2]["cpu_only"]
    assert not _results(worker=worker)[1][2]["cpu_only"]


def test_reports_activity_and_the_device_it_runs_on(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    seen: list[tuple[bool, str | None]] = []
    worker.activity_changed.connect(
        lambda: seen.append((worker.job is not None, worker.device))
    )
    worker.submit(channel="x", job="job", request=_request(model_name="gpu-ok"))
    _wait_for(qtbot=qtbot, worker=worker, count=1)
    worker.set_device(device="cpu")
    worker.submit(channel="x", job="next", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=2)

    assert seen == [
        (True, None),  # starting the worker
        (True, "webgpu"),
        (False, None),
        (True, "cpu"),  # known before loading on a CPU worker
        (True, "cpu"),
        (False, None),
    ]


def test_reports_the_stages_of_its_own_request(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    seen: list[tuple[str | None, str | None]] = []
    worker.activity_changed.connect(lambda: seen.append((worker.stage, worker.device)))
    worker.submit(channel="x", job="job", request=_request(model_name="stages"))
    assert worker.model_name == "stages"
    _wait_for(qtbot=qtbot, worker=worker, count=1)
    worker.submit(channel="x", job="warm", request=_request(model_name="stages"))
    _wait_for(qtbot=qtbot, worker=worker, count=2)

    run = [
        ("loading", None),
        ("encoding", "cpu"),
        ("generating", "cpu"),
        (None, None),
    ]
    # Only a job that spawns the worker starts it; another request's is ignored.
    assert seen == [("starting", None), *run, (None, None), *run]
    assert worker.model_name is None


def test_reports_a_job_queued_behind_the_running_one(*, worker: OsamWorker) -> None:
    worker.submit(channel="x", job="running", request=_request(model_name="hang"))
    seen: list[bool] = []
    worker.activity_changed.connect(lambda: seen.append(worker.job is not None))

    worker.submit(channel="y", job="queued", request=_request())

    assert seen == [True]
    worker.release()


def test_release_fails_the_jobs_it_drops(*, worker: OsamWorker, qtbot: QtBot) -> None:
    worker.submit(channel="x", job="running", request=_request(model_name="hang"))
    worker.submit(channel="y", job="waiting", request=_request())

    worker.release()

    assert _results(worker=worker) == [
        ("error", "running", "AI worker stopped"),
        ("error", "waiting", "AI worker stopped"),
    ]
    worker.submit(channel="x", job="later", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=3)
    assert _results(worker=worker)[2][:2] == ("done", "later")


@pytest.mark.parametrize(
    ("points", "point_labels", "texts", "expected"),
    [
        # SAM decoders read an integer as a pixel center.
        (
            [[5, 7], [1, 1], [9, 9]],
            [1, 2, 3],
            None,
            {"points": [[4.5, 6.5]], "point_labels": [1], "box": [0.5, 0.5, 8.5, 8.5]},
        ),
        (
            [[5, 7]],
            [0],
            None,
            {"points": [[4.5, 6.5]], "point_labels": [0], "box": None},
        ),
        # SAM3 reads an example box by its edges, as the canvas draws them.
        (
            [[1, 1], [9, 9], [2, 2], [3, 3]],
            [2, 3, 4, 5],
            ["visual"],
            {
                "texts": ["visual"],
                "example_boxes": [[1, 1, 9, 9], [2, 2, 3, 3]],
                "example_box_labels": [1, 0],
            },
        ),
        ([], [], ["dog", "cat"], {"texts": ["dog", "cat"]}),
    ],
)
def test_segment_kwargs_translate_the_canvas_prompt(
    *,
    points: list[list[float]],
    point_labels: list[int],
    texts: list[str] | None,
    expected: dict[str, object],
) -> None:
    request = InferenceRequest(
        model_name="sam3:latest",
        image_id="img",
        image=None,
        points=np.array(points, dtype=float),
        point_labels=np.array(point_labels, dtype=int),
        texts=texts,
    )

    kwargs = _osam_worker._segment_kwargs(request=request)

    for key, value in expected.items():
        if value is None:
            assert kwargs[key] is None
        else:
            np.testing.assert_array_equal(kwargs[key], value)


class _OrtFail(Exception):
    pass


_OrtFail.__module__ = "onnxruntime.capi.onnxruntime_pybind11_state"


class _FailingClient:
    _error: Exception

    def __init__(self, error: Exception, /) -> None:
        self._error = error

    def ps(self) -> builtins.list[osam.types.RunningModel]:
        return [
            osam.types.RunningModel(name="sam:100m", device="webgpu", expires_at=None)
        ]

    def segment(self, *_: object, **__: object) -> builtins.list[osam.types.Annotation]:
        raise self._error

    def list(self) -> builtins.list[osam.types.ModelInfo]:
        return osam.Client(in_process=True).list()


@pytest.mark.parametrize(
    ("error", "kind"),
    [(_OrtFail("device lost"), "fault"), (ValueError("bad prompt"), "error")],
)
def test_serve_reports_onnx_runtime_errors_as_faults(
    *, monkeypatch: pytest.MonkeyPatch, error: Exception, kind: str
) -> None:
    # A fault may be the device's, so the worker retries it on CPU.
    monkeypatch.setattr(
        "labelme._ai_models.osam_client", lambda **_: _FailingClient(error)
    )
    requests, to_serve = multiprocessing.Pipe(duplex=False)
    from_serve, responses = multiprocessing.Pipe(duplex=False)
    to_serve.send(
        (
            "run",
            7,
            dataclasses.replace(
                _request(),
                model_name="sam:100m",
                points=np.array([[0.0, 0.0]]),
                point_labels=np.array([1]),
            ),
        )
    )
    to_serve.close()

    _osam_worker.serve(requests, responses, "auto")

    assert from_serve.recv() == ("stage", 7, ("encoding", "webgpu"))
    assert from_serve.recv()[:2] == (kind, 7)
