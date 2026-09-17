from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import osam
import pytest
from pytestqt.qtbot import QtBot

from labelme._model_manager import ModelManager


@pytest.fixture
def manager(
    *,
    qtbot: QtBot,  # noqa: ARG001 -- a fixture cannot use usefixtures
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[ModelManager]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("OSAM_BLOB_ENDPOINT", "direct")
    instance = ModelManager()
    yield instance
    instance.shutdown()


def _make_blob(*, url: str) -> osam.types.Blob:
    return osam.types.Blob(
        url=url, hash="sha256:" + hashlib.sha256(b"weights").hexdigest()
    )


def test_queue_continues_after_failure_and_retry_goes_last(
    *,
    manager: ModelManager,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    download_server: tuple[str, list[str], threading.Event],
) -> None:
    origin, requests, release = download_server
    failed = "efficientsam:10m"
    waiting = "efficientsam:latest"
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(failed),
        "_blobs",
        {"model": _make_blob(url=origin + "/bad")},
    )
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(waiting),
        "_blobs",
        {"model": _make_blob(url=origin + "/slow")},
    )
    manager.enqueue(failed)
    manager.enqueue(waiting)
    qtbot.waitUntil(
        lambda: manager.get_state(failed) == "failed" and manager.active == waiting,
        timeout=20_000,
    )
    assert manager.errors[failed]
    manager.enqueue(failed)
    assert manager.queue == [failed]
    release.set()
    qtbot.waitUntil(lambda: manager.active is None and not manager.queue)
    assert manager.is_ready(waiting)
    # Both variants share the same digest in this fixture; retry reuses the file.
    assert manager.is_ready(failed)
    assert failed not in manager.errors
    assert requests.count("/slow") == 1


def test_cancel_keeps_completed_files_and_quit_discards_queue(
    *,
    manager: ModelManager,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    download_server: tuple[str, list[str], threading.Event],
) -> None:
    origin, requests, release = download_server
    name = "efficientsam:10m"
    blob = _make_blob(url=origin + "/slow")
    completed = osam.types.Blob(
        url=origin + "/done", hash="sha256:" + hashlib.sha256(b"done").hexdigest()
    )
    Path(completed.path).parent.mkdir(parents=True, exist_ok=True)
    Path(completed.path).write_bytes(b"done")
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(name),
        "_blobs",
        {"done": completed, "model": blob},
    )
    manager.enqueue(name)
    manager.enqueue("sam:100m")
    qtbot.waitUntil(lambda: requests == ["/slow"])
    manager.cancel("sam:100m")
    manager.cancel(name)
    assert manager.active is None and not manager.queue
    assert manager.get_state(name) == "missing"
    release.set()
    qtbot.waitUntil(lambda: manager._pull is None)
    assert Path(completed.path).read_bytes() == b"done"
    assert not Path(blob.path).exists()

    release.clear()
    manager.enqueue(name)
    manager.enqueue("sam:100m")
    qtbot.waitUntil(lambda: requests == ["/slow", "/slow"])
    manager.cancel(name)
    release.set()
    manager.shutdown()
    assert manager.active is None and not manager.queue
    assert not Path(blob.path).exists()
    reopened = ModelManager()
    try:
        assert reopened.get_state(name) == "missing"
        assert reopened.active is None and not reopened.queue
        assert requests == ["/slow", "/slow"]
    finally:
        reopened.shutdown()


def test_shutdown_interrupts_stalled_download(
    *,
    manager: ModelManager,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    download_server: tuple[str, list[str], threading.Event],
) -> None:
    origin, _, release = download_server
    name = "efficientsam:10m"
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(name),
        "_blobs",
        {"model": _make_blob(url=origin + "/large")},
    )
    manager.enqueue(name)
    # Consume the entire initial body so the worker is left waiting on a server
    # that sends nothing more.
    qtbot.waitUntil(lambda: manager.progress[1] == 2**20)
    started_at = time.monotonic()
    manager.shutdown()
    # The server gives up on its own after a few seconds, which would also end
    # the transfer; only a prompt return proves cancellation interrupted it.
    assert time.monotonic() - started_at < 2
    assert not release.is_set()


def test_existing_files_count_as_downloaded_until_deleted(
    *, manager: ModelManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = "efficientsam:10m"
    blob = _make_blob(url="https://example.invalid/weights")
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(name), "_blobs", {"model": blob}
    )
    path = Path(blob.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"weights")
    manager.refresh()
    assert manager.get_state(name) == "downloaded"
    manager.enqueue(name)
    assert manager.active is None
    manager.remove(name)
    assert not path.exists()
    assert manager.get_state(name) == "missing"
    assert not manager.is_ready(name)


def test_progress_supports_files_larger_than_two_gibibytes(
    *,
    manager: ModelManager,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    download_server: tuple[str, list[str], threading.Event],
) -> None:
    origin, _, release = download_server
    name = "efficientsam:10m"
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(name),
        "_blobs",
        {"model": _make_blob(url=origin + "/large")},
    )
    manager.enqueue(name)
    qtbot.waitUntil(lambda: manager.progress[1] > 0)
    # The first report may cover a partial chunk; the total is the point.
    assert manager.progress[0] == "large"
    assert manager.progress[2] == 2**33
    manager.cancel(name)
    release.set()
