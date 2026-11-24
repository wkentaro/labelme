from __future__ import annotations

import builtins
import gc
import threading
import time
from collections.abc import Iterator
from typing import Any
from typing import Final
from typing import cast

import numpy as np
import osam
import PIL.Image
import pytest
from PySide6 import QtGui
from PySide6 import QtWidgets
from pytestqt.qtbot import QtBot

from labelme._automation import _osam_worker
from labelme._automation._osam_worker import InferenceRequest
from labelme._automation._osam_worker import OsamWorker

_IMAGE: Final = QtGui.QImage(3, 2, QtGui.QImage.Format.Format_RGB32)
_WAIT_MS: Final = 30_000


class _ScriptedClient:
    # The model name scripts how a request goes.
    device: str
    closed: bool
    loaded: set[str]
    release: threading.Event

    def __init__(self, *, device: str) -> None:
        self.device = device
        self.closed = False
        self.loaded = set()
        self.release = threading.Event()

    def ps(self) -> builtins.list[osam.types.RunningModel]:
        return [
            osam.types.RunningModel(name=name, device=self.device, expires_at=None)
            for name in self.loaded
        ]

    def list(self) -> builtins.list[osam.types.ModelInfo]:
        return [
            osam.types.ModelInfo.model_construct(
                name=name, input_size=1024, input_resize="fit"
            )
            for name in self.loaded
        ]

    def load(self, *args: object, **kwargs: object) -> osam.types.RunningModel:
        name = cast(str, args[0])  # positional, as osam takes it
        if kwargs.get("keep_alive") == 0:
            self.loaded.discard(name)
        else:
            self.loaded.add(name)
        return osam.types.RunningModel(name=name, device=self.device, expires_at=None)

    def segment(self, *args: object, **_: object) -> dict[str, object]:
        model = args[0]  # positional, as osam takes it
        if model == "hang":
            self.release.wait(timeout=_WAIT_MS / 1000)
        if self.closed:
            raise RuntimeError("the osam client is closed")
        if model == "error":
            raise ValueError("bad prompt")
        if model == "not-pulled":
            raise osam.ResponseError(
                "not pulled for cpu",
                status_code=404,
                code="model_not_pulled",
                device="cpu",
            )
        return {"client": self}

    def close(self) -> None:
        self.closed = True
        self.release.set()


def _request(*, model_name: str = "ok") -> InferenceRequest:
    return InferenceRequest(
        model_name=model_name,
        image=_IMAGE,
        points=np.array([[0.0, 0.0]]),
        point_labels=np.array([1]),
    )


@pytest.fixture
def worker(
    *,
    qtbot: QtBot,  # noqa: ARG001 -- needs a QApplication
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[OsamWorker]:
    monkeypatch.setattr(
        _osam_worker,
        "osam_client",
        lambda *, device, **_: _ScriptedClient(
            device="cpu" if device == "cpu" else "webgpu"
        ),
    )
    instance = OsamWorker()
    results: list[tuple[str, object, Any]] = []
    instance.finished.connect(lambda job, r: results.append(("done", job, r)))
    instance.failed.connect(lambda job, m: results.append(("error", job, m)))
    instance.results = results  # ty: ignore[unresolved-attribute]
    yield instance
    instance.shutdown()


def _client(*, worker: OsamWorker) -> _ScriptedClient:
    assert worker._client is not None
    return cast(_ScriptedClient, worker._client[1])


def _results(*, worker: OsamWorker) -> list[tuple[str, object, Any]]:
    return worker.results  # ty: ignore[unresolved-attribute]


def _wait_for(*, qtbot: QtBot, worker: OsamWorker, count: int) -> None:
    qtbot.waitUntil(lambda: len(_results(worker=worker)) >= count, timeout=_WAIT_MS)


def test_newer_submit_replaces_a_waiting_one_on_its_channel(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="finalize", job="running", request=_request())
    worker.submit(channel="preview", job="stale", request=_request())
    worker.submit(channel="preview", job="latest", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=2)

    assert [job for _, job, _ in _results(worker=worker)] == ["running", "latest"]
    assert worker._active is None
    assert not worker._pending


def test_reports_a_model_error_and_keeps_the_server(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="x", job="first", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=1)
    worker.submit(channel="x", job="bad", request=_request(model_name="error"))
    worker.submit(channel="y", job="after", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=3)

    (_, _, first), bad, (_, _, after) = _results(worker=worker)
    assert bad == ("error", "bad", "ValueError: bad prompt")
    assert after.annotations["client"] is first.annotations["client"]


def test_reports_a_model_not_pulled_for_the_device(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    not_pulled: list[object] = []
    worker.not_pulled.connect(not_pulled.append)
    worker.submit(channel="x", job="job", request=_request(model_name="not-pulled"))
    _wait_for(qtbot=qtbot, worker=worker, count=1)

    assert not_pulled == ["cpu"]
    assert _results(worker=worker) == [("error", "job", "not pulled for cpu")]


def test_submit_returns_while_a_job_runs(*, worker: OsamWorker, qtbot: QtBot) -> None:
    worker.submit(channel="x", job="slow", request=_request(model_name="hang"))
    worker.submit(channel="y", job="next", request=_request())
    qtbot.waitUntil(lambda: worker.stage == "generating", timeout=_WAIT_MS)
    assert _results(worker=worker) == []

    _client(worker=worker).release.set()
    _wait_for(qtbot=qtbot, worker=worker, count=2)
    assert [job for _, job, _ in _results(worker=worker)] == ["slow", "next"]


def test_holds_results_while_a_modal_dialog_is_open(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    # A label edit or a warning: its result would open a second dialog or
    # change the Shapes under it.
    dialog = QtWidgets.QDialog()
    dialog.setModal(True)
    dialog.show()
    worker.submit(channel="x", job="job", request=_request())
    qtbot.wait(500)
    assert _results(worker=worker) == []

    dialog.close()
    _wait_for(qtbot=qtbot, worker=worker, count=1)
    assert _results(worker=worker)[0][:2] == ("done", "job")


def test_set_device_starts_a_server_for_the_next_job(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="x", job="gpu", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=1)
    worker.set_device(device="cpu")
    worker.submit(channel="x", job="cpu", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=2)

    (_, _, on_gpu), (_, _, on_cpu) = _results(worker=worker)
    assert on_gpu.annotations["client"].closed
    assert on_cpu.annotations["client"].device == "cpu"


def test_reports_the_stages_and_device_of_its_own_request(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    seen: list[tuple[bool, str | None, str | None]] = []
    worker.activity_changed.connect(
        lambda: seen.append((worker.job is not None, worker.stage, worker.device))
    )
    worker.submit(channel="x", job="job", request=_request())
    assert worker.model_name == "ok"
    _wait_for(qtbot=qtbot, worker=worker, count=1)
    worker.submit(channel="x", job="warm", request=_request())
    _wait_for(qtbot=qtbot, worker=worker, count=2)

    assert seen == [
        (True, None, None),
        (True, "starting", None),
        (True, "loading", None),
        (True, "generating", "webgpu"),
        (False, None, None),
        (True, None, None),
        (True, "generating", "webgpu"),
        (False, None, None),
    ]
    assert worker.model_name is None


def test_reports_a_job_queued_behind_the_running_one(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="x", job="running", request=_request(model_name="hang"))
    seen: list[bool] = []
    worker.activity_changed.connect(lambda: seen.append(worker.job is not None))

    worker.submit(channel="y", job="queued", request=_request())

    assert seen == [True]
    qtbot.waitUntil(lambda: worker.stage == "generating", timeout=_WAIT_MS)
    _client(worker=worker).release.set()


def test_unload_waits_for_the_running_request_and_keeps_the_server(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="x", job="running", request=_request(model_name="hang"))
    qtbot.waitUntil(lambda: worker.stage == "generating", timeout=_WAIT_MS)
    worker.submit(channel="y", job="removed", request=_request(model_name="hang"))
    worker.submit(channel="z", job="other", request=_request())
    client = _client(worker=worker)
    unloaded: list[tuple[str, set[str]]] = []

    worker.unloaded.connect(lambda name: unloaded.append((name, set(client.loaded))))
    worker.unload(model_name="hang")
    # Until the files go, it can't load again.
    worker.submit(channel="y", job="reloaded", request=_request(model_name="hang"))

    assert _results(worker=worker) == [
        ("error", "removed", "AI model removed"),
        ("error", "reloaded", "AI model removed"),
    ]
    assert not unloaded
    client.release.set()
    qtbot.waitUntil(lambda: bool(unloaded), timeout=_WAIT_MS)
    ((name, loaded),) = unloaded
    assert name == "hang" and "hang" not in loaded
    worker.submit(channel="y", job="after", request=_request(model_name="hang"))
    _wait_for(qtbot=qtbot, worker=worker, count=5)
    assert [r[:2] for r in _results(worker=worker)[2:]] == [
        ("done", "running"),
        ("done", "other"),
        ("done", "after"),
    ]
    assert worker._client is not None and _client(worker=worker) is client


def test_shutdown_deletes_a_model_waiting_on_the_running_request(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="x", job="running", request=_request(model_name="hang"))
    qtbot.waitUntil(lambda: worker.stage == "generating", timeout=_WAIT_MS)
    unloaded: list[str] = []
    worker.unloaded.connect(unloaded.append)
    worker.unload(model_name="hang")

    worker.shutdown()

    assert unloaded == ["hang"]
    client = _client(worker=worker)
    client.release.set()
    qtbot.waitUntil(lambda: client.closed, timeout=_WAIT_MS)
    qtbot.wait(50)  # the thread's own report comes too late to delete again
    assert unloaded == ["hang"]


def test_shutdown_does_not_wait_for_a_running_request(
    *, worker: OsamWorker, qtbot: QtBot
) -> None:
    worker.submit(channel="x", job="running", request=_request(model_name="hang"))
    qtbot.waitUntil(lambda: worker.stage == "generating", timeout=_WAIT_MS)
    client = _client(worker=worker)

    start = time.monotonic()
    worker.shutdown()
    assert time.monotonic() - start < 1  # not held up by the request
    assert not client.closed

    client.release.set()  # the request ends; the thread then closes it
    qtbot.waitUntil(lambda: client.closed, timeout=_WAIT_MS)


def test_runs_on_a_private_server(
    *, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Even with OSAM_HOST set for the osam CLI; nothing listens there.
    monkeypatch.setenv("OSAM_HOST", "127.0.0.1:1")
    before = set(threading.enumerate())
    worker = OsamWorker()
    failed: list[tuple[object, str]] = []
    worker.failed.connect(lambda job, m: failed.append((job, m)))
    try:
        worker.submit(channel="x", job="job", request=_request(model_name="nope"))
        qtbot.waitUntil(lambda: bool(failed), timeout=_WAIT_MS)
    finally:
        worker.shutdown()
        for thread in set(threading.enumerate()) - before:
            if thread.name == "osam-worker":
                thread.join(timeout=5)
        gc.collect()  # fails on a ResourceWarning if the server leaked a pipe

    [(job, message)] = failed
    assert job == "job"
    assert "nope" in message


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
        image=_IMAGE,
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


class _StretchingClient:
    images: builtins.list[np.ndarray]
    kwargs: builtins.list[dict[str, object]]

    def __init__(self) -> None:
        self.images = []
        self.kwargs = []

    def ps(self) -> builtins.list[osam.types.RunningModel]:
        return [osam.types.RunningModel(name="m", device="cpu", expires_at=None)]

    def list(self) -> builtins.list[osam.types.ModelInfo]:
        return [
            osam.types.ModelInfo.model_construct(
                name="m", input_size=8, input_resize="stretch"
            )
        ]

    def segment(
        self, *args: object, **kwargs: object
    ) -> builtins.list[osam.types.Annotation]:
        _, image = cast(tuple[str, np.ndarray], args)
        self.images.append(image)
        self.kwargs.append(kwargs)
        return [
            osam.types.Annotation(
                bounding_box=osam.types.BoundingBox(xmin=0, ymin=0, xmax=7, ymax=7),
                mask=np.eye(8, dtype=bool),
                score=0.9,
            )
        ]


def test_run_sends_a_large_image_at_the_model_resolution() -> None:
    image = QtGui.QImage(32, 16, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtGui.QColor(10, 20, 30))
    client = _StretchingClient()
    request = InferenceRequest(
        model_name="m",
        image=image,
        points=np.array([[16.5, 8.5]]),
        point_labels=np.array([1]),
    )
    cache: dict[Any, np.ndarray] = {}

    results = [
        _osam_worker._run(
            client=cast(osam.Client, client),
            request=request,
            progress=lambda *_: None,
            cache=cache,
        )
        for _ in range(2)
    ]

    assert client.images[0].shape == (8, 8, 3)
    assert client.images[0][0, 0].tolist() == [10, 20, 30]
    assert client.images[1] is client.images[0]
    np.testing.assert_allclose(
        cast(np.ndarray, client.kwargs[0]["points"]), [[3.625, 3.75]]
    )
    (annotation,) = results[0].annotations
    assert annotation.mask is not None
    np.testing.assert_array_equal(annotation.mask, np.eye(8, dtype=bool))
    assert results[0].scale_to_image == (4.0, 2.0)
    assert results[0].sent_size == (8, 8)


@pytest.mark.parametrize(
    ("image_size", "asks"), [((32, 16), True), ((8, 8), False), ((6, 4), False)]
)
def test_run_asks_for_mask_logits_only_with_an_image_it_shrank(
    *, image_size: tuple[int, int], asks: bool
) -> None:
    client = _StretchingClient()
    request = InferenceRequest(
        model_name="m",
        image=QtGui.QImage(*image_size, QtGui.QImage.Format.Format_RGB32),
        points=np.array([[1.5, 1.5]]),
        point_labels=np.array([1]),
    )

    _osam_worker._run(
        client=cast(osam.Client, client),
        request=request,
        progress=lambda *_: None,
        cache={},
    )

    assert client.kwargs[0]["include_mask_logits"] is asks


def test_model_image_resizes_as_pillow_resizes_rgb() -> None:
    rng = np.random.default_rng(0)
    rgb = rng.integers(0, 256, size=(37, 53, 3), dtype=np.uint8)
    image = QtGui.QImage(
        np.ascontiguousarray(rgb).tobytes(),
        53,
        37,
        53 * 3,
        QtGui.QImage.Format.Format_RGB888,
    ).convertToFormat(QtGui.QImage.Format.Format_RGB32)

    actual = _osam_worker._model_image(image=image, size=(20, 14))

    expected = PIL.Image.fromarray(rgb).resize((20, 14), PIL.Image.Resampling.BILINEAR)
    np.testing.assert_array_equal(actual, np.asarray(expected))
