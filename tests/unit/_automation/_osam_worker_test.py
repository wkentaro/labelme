from __future__ import annotations

import os
import struct
import time
from collections.abc import Iterator
from multiprocessing.connection import Connection
from typing import Any
from typing import Final

import numpy as np
import osam
import pytest
from pytestqt.qtbot import QtBot

from labelme._automation import _osam_worker
from labelme._automation._osam_worker import InferenceRequest
from labelme._automation._osam_worker import OsamWorker

_IMAGE: Final = np.zeros((2, 3, 3), dtype=np.uint8)
_WAIT_MS: Final = 30_000


def _scripted_serve(requests: Connection, responses: Connection, /) -> None:
    # Spawned in the worker: the model name scripts how the request goes.
    while True:
        try:
            _, request_id, request = requests.recv()
        except EOFError:
            return
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
        result = {"pid": os.getpid(), "sent_image": request.image is not None}
        responses.send(("done", request_id, result))


def _late_serve(requests: Connection, responses: Connection, /) -> None:
    time.sleep(1)  # a worker still importing reads nothing yet
    _scripted_serve(requests, responses)


def _request(*, model_name: str = "ok", image_id: str = "img") -> InferenceRequest:
    return InferenceRequest(model_name=model_name, image_id=image_id, image=_IMAGE)


@pytest.fixture
def worker(*, qtbot: QtBot) -> Iterator[OsamWorker]:  # noqa: ARG001 -- needs a QApplication
    instance = OsamWorker(target=_scripted_serve, timeout_s=5)
    results: list[tuple[str, object, Any]] = []
    instance.finished.connect(lambda job, r: results.append(("done", job, r)))
    instance.failed.connect(lambda job, m: results.append(("error", job, m)))
    instance.results = results  # ty: ignore[unresolved-attribute]
    yield instance
    instance.shutdown()


def _results(worker: OsamWorker, /) -> list[tuple[str, object, Any]]:
    return worker.results  # ty: ignore[unresolved-attribute]


def _wait_for(qtbot: QtBot, worker: OsamWorker, /, *, count: int) -> None:
    qtbot.waitUntil(lambda: len(_results(worker)) >= count, timeout=_WAIT_MS)


def test_sends_an_image_once_per_image_id(*, worker: OsamWorker, qtbot: QtBot) -> None:
    for job in ["a", "b"]:
        worker.submit(channel=job, job=job, request=_request())
    worker.submit(channel="c", job="c", request=_request(image_id="other"))
    _wait_for(qtbot, worker, count=3)

    assert [(kind, job, r["sent_image"]) for kind, job, r in _results(worker)] == [
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
    _wait_for(qtbot, worker, count=2)

    assert [job for _, job, _ in _results(worker)] == ["running", "latest"]


def test_reports_a_model_error_and_keeps_the_worker(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="x", job="first", request=_request())
    _wait_for(qtbot, worker, count=1)
    worker.submit(channel="x", job="bad", request=_request(model_name="error"))
    worker.submit(channel="y", job="after", request=_request())
    _wait_for(qtbot, worker, count=3)

    (_, _, first), bad, (_, _, after) = _results(worker)
    assert bad == ("error", "bad", "ValueError: bad prompt")
    assert after["pid"] == first["pid"]


@pytest.mark.parametrize(
    ("model_name", "message"),
    [
        ("crash", "AI worker exited with code 3"),
        ("hang", "AI inference timed out after 1 s"),
        ("stall", "AI inference timed out after 1 s"),
    ],
)
def test_restarts_the_worker_after_a_crash_or_hang(
    *, qtbot: QtBot, model_name: str, message: str
) -> None:
    worker = OsamWorker(target=_scripted_serve, timeout_s=1)
    results: list[tuple[object, Any]] = []
    worker.finished.connect(lambda job, r: results.append((job, r)))
    worker.failed.connect(lambda job, m: results.append((job, m)))
    try:
        worker.submit(
            channel="x", job="broken", request=_request(model_name=model_name)
        )
        worker.submit(channel="y", job="next", request=_request())
        qtbot.waitUntil(lambda: len(results) == 2, timeout=_WAIT_MS)
    finally:
        worker.shutdown()

    assert results[0] == ("broken", message)
    job, result = results[1]
    assert job == "next"
    assert result["sent_image"]  # the new worker never saw the image


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


def test_release_fails_the_jobs_it_drops(*, worker: OsamWorker, qtbot: QtBot) -> None:
    worker.submit(channel="x", job="running", request=_request(model_name="hang"))
    worker.submit(channel="y", job="waiting", request=_request())

    worker.release()

    assert _results(worker) == [
        ("error", "running", "AI worker stopped"),
        ("error", "waiting", "AI worker stopped"),
    ]
    worker.submit(channel="x", job="later", request=_request())
    _wait_for(qtbot, worker, count=3)
    assert _results(worker)[2][:2] == ("done", "later")


class _FakeSession:
    calls: list[dict[str, object]]

    def __init__(self) -> None:
        self.calls = []

    def run(self, **kwargs: object) -> osam.types.GenerateResponse:
        self.calls.append(kwargs)
        texts = kwargs["texts"]
        assert isinstance(texts, list)
        return osam.types.GenerateResponse(
            model="fake",
            annotations=[osam.types.Annotation(text=str(t), score=1.0) for t in texts],
        )


@pytest.mark.parametrize(
    ("model_name", "expected_batches"),
    [
        ("sam3:latest", [["dog"], ["cat"]]),
        ("yoloworld:latest", [["dog", "cat"]]),
    ],
)
def test_run_sends_sam3_one_text_at_a_time(
    *,
    monkeypatch: pytest.MonkeyPatch,
    model_name: str,
    expected_batches: list[list[str]],
) -> None:
    # SAM3 reads only the first text of a prompt; YOLO-World takes them all.
    session = _FakeSession()
    monkeypatch.setattr(
        "labelme._automation._osam_session.get_osam_session",
        lambda **_: session,
    )
    request = InferenceRequest(
        model_name=model_name, image_id="img", image=None, texts=["dog", "cat"]
    )

    annotations = _osam_worker._run(request, _IMAGE)

    assert [a.text for a in annotations] == ["dog", "cat"]
    assert [call["texts"] for call in session.calls] == expected_batches
    assert all(call["image"] is _IMAGE for call in session.calls)
