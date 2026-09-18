from __future__ import annotations

import hashlib
import socketserver
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


@pytest.fixture
def stalled_tls_server() -> Iterator[tuple[str, threading.Event, threading.Event]]:
    accepted = threading.Event()
    release = threading.Event()

    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            accepted.set()
            release.wait(timeout=10)

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield f"https://127.0.0.1:{server.server_address[1]}", accepted, release
    release.set()
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)
    assert not thread.is_alive()


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
    qtbot.waitUntil(
        lambda: manager.active is None and not manager.queue, timeout=20_000
    )
    assert manager.is_ready(waiting)
    # Both variants share the same digest in this fixture; retry reuses the file.
    assert manager.is_ready(failed)
    assert failed not in manager.errors
    assert requests.count("/slow") == 1


def test_cache_setup_failure_marks_model_as_failed(
    *, manager: ModelManager, tmp_path: Path
) -> None:
    model_root = tmp_path / ".cache" / "osam" / "models"
    model_root.parent.mkdir(parents=True)
    model_root.write_text("not a directory")
    name = "efficientsam:10m"

    manager.enqueue(name)

    assert manager.get_state(name) == "failed"
    assert manager.active is None
    assert not manager.queue


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
    assert manager.shutdown()
    release.set()
    assert manager.active is None and not manager.queue
    assert not Path(blob.path).exists()
    reopened = ModelManager()
    try:
        assert reopened.get_state(name) == "missing"
        assert reopened.active is None and not reopened.queue
        assert requests == ["/slow", "/slow"]
    finally:
        reopened.shutdown()


def test_cancel_preserves_blob_completed_before_active_download(
    *,
    manager: ModelManager,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    download_server: tuple[str, list[str], threading.Event],
) -> None:
    origin, requests, release = download_server
    name = "efficientsam:10m"
    completed = _make_blob(url=origin + "/weights")
    active = osam.types.Blob(
        url=origin + "/slow",
        hash="sha256:" + hashlib.sha256(b"later").hexdigest(),
    )
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(name),
        "_blobs",
        {"completed": completed, "active": active},
    )
    manager.enqueue(name)
    qtbot.waitUntil(lambda: requests == ["/weights", "/slow"])

    manager.cancel(name)

    assert Path(completed.path).exists()
    assert not Path(active.path).exists()
    release.set()
    qtbot.wait(100)
    assert Path(completed.path).exists()
    assert not Path(active.path).exists()


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
    assert manager.shutdown()
    # The server gives up on its own after a few seconds, which would also end
    # the transfer; only a prompt return proves cancellation interrupted it.
    assert time.monotonic() - started_at < 2
    assert not release.is_set()


def test_shutdown_terminates_download_stalled_during_tls(
    *,
    manager: ModelManager,
    monkeypatch: pytest.MonkeyPatch,
    stalled_tls_server: tuple[str, threading.Event, threading.Event],
) -> None:
    origin, accepted, release = stalled_tls_server
    name = "efficientsam:10m"
    blob = _make_blob(url=origin + "/weights")
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(name), "_blobs", {"model": blob}
    )
    manager.enqueue(name)
    assert accepted.wait(timeout=5)
    blob_root = Path(blob.path).parent

    failsafe = threading.Timer(3, release.set)
    failsafe.start()
    started_at = time.monotonic()
    assert manager.shutdown()
    elapsed = time.monotonic() - started_at
    handshake_was_stalled = not release.is_set()
    release.set()
    failsafe.cancel()
    time.sleep(0.1)

    assert elapsed < 2
    assert handshake_was_stalled
    assert not Path(blob.path).exists()
    assert not list(blob_root.glob(".labelme-pull-*"))


def test_failed_shutdown_keeps_active_download_and_queue(
    *,
    manager: ModelManager,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    download_server: tuple[str, list[str], threading.Event],
) -> None:
    origin, requests, release = download_server
    active = "efficientsam:10m"
    queued = "efficientsam:latest"
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(active),
        "_blobs",
        {"model": _make_blob(url=origin + "/slow")},
    )
    manager.enqueue(active)
    manager.enqueue(queued)
    qtbot.waitUntil(lambda: requests == ["/slow"])
    assert manager._pull is not None
    pull = manager._pull

    def fail_stop() -> bool:
        pull.error = "could not stop"
        return False

    with monkeypatch.context() as patch:
        patch.setattr(pull, "stop", fail_stop)
        assert not manager.shutdown()

    assert manager.active == active
    assert manager.queue == [queued]
    assert manager.errors[active] == "could not stop"
    manager.cancel(queued)
    release.set()
    assert manager.shutdown()


def test_remove_stops_download_before_deleting_files(
    *,
    manager: ModelManager,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    download_server: tuple[str, list[str], threading.Event],
) -> None:
    origin, requests, download_release = download_server
    name = "efficientsam:10m"
    blob = _make_blob(url=origin + "/slow")
    monkeypatch.setattr(
        osam.apis.get_model_type_by_name(name), "_blobs", {"model": blob}
    )
    notifications: list[str] = []
    manager.changed.connect(lambda: notifications.append("changed"))
    manager.progress_changed.connect(lambda: notifications.append("progress"))
    manager.enqueue(name)
    qtbot.waitUntil(lambda: requests == ["/slow"])
    notifications.clear()

    manager.remove(name)
    assert not Path(blob.path).exists()
    assert notifications == ["changed"]
    download_release.set()
    qtbot.wait(100)

    assert not Path(blob.path).exists()
    assert notifications == ["changed"]


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
