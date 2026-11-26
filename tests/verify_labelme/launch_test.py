from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

from .conftest import Ctl
from .conftest import Run

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="labelme_ctl.py needs macOS sandbox-exec"
)

OVERSIZED_REQUEST: Final = b"x" * (2 << 20)


def _assert_healthy(*, ctl: Ctl, run: Run) -> None:
    reply = ctl("doctor", run=run)
    assert reply.code == 0, reply.body
    assert reply.body["healthy"] is True


def _sandboxed_touch(*, run: Run, path: Path) -> int:
    profile = run.run_dir / "sandbox.sb"
    return subprocess.run(
        ["/usr/bin/sandbox-exec", "-f", str(profile), "/usr/bin/touch", str(path)],
        capture_output=True,
    ).returncode


def _send_until_closed(*, port: int, request: bytes) -> bytes:
    received = b""
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        try:
            sock.sendall(request)
            while chunk := sock.recv(1 << 16):
                received += chunk
        except (BrokenPipeError, ConnectionResetError):
            pass
    return received


def test_sandbox_confines_writes_to_the_run_dir(*, ctl: Ctl, tmp_path: Path) -> None:
    run = ctl.launch("{data}")
    outside = tmp_path / "outside"
    outside.mkdir()
    (run.data / "link").symlink_to(outside)

    assert _sandboxed_touch(run=run, path=outside / "direct.txt") != 0
    assert _sandboxed_touch(run=run, path=run.data / "link" / "linked.txt") != 0
    assert _sandboxed_touch(run=run, path=run.data / "inside.txt") == 0

    assert list(outside.iterdir()) == []
    assert (run.data / "inside.txt").exists()
    _assert_healthy(ctl=ctl, run=run)


def test_control_port_drops_bad_requests_and_stays_healthy(*, ctl: Ctl) -> None:
    run = ctl.launch("{data}")
    port = json.loads((run.run_dir / "instance.json").read_text())["port"]
    token = json.loads((run.run_dir / "run.json").read_text())["token"]
    requests = {
        "bad token": json.dumps({"cmd": "state", "token": "0" * len(token)}),
        "garbage": "not json",
        "non-string token": json.dumps({"cmd": "state", "token": 7}),
        "lone surrogate token": '{"cmd": "state", "token": "\\ud800"}',
    }

    for name, request in requests.items():
        received = _send_until_closed(port=port, request=request.encode() + b"\n")
        assert b'"ok": true' not in received, name
    assert _send_until_closed(port=port, request=OVERSIZED_REQUEST) == b""

    _assert_healthy(ctl=ctl, run=run)


def test_launch_on_unreadable_image_returns_its_error_dialog(
    *, ctl: Ctl, tmp_path: Path
) -> None:
    image = tmp_path / "unreadable.jpg"
    image.write_bytes(b"not an image")

    run = ctl.launch(str(image), seed="none")

    assert run.launch["image_loaded"] is False
    assert run.launch["dialog"] is not None
    assert ctl("state", run=run).body["dialog"] == run.launch["dialog"]
    _assert_healthy(ctl=ctl, run=run)


def test_launch_with_inline_config_is_healthy(*, ctl: Ctl) -> None:
    run = ctl.launch("--config", "{auto_save: false}")

    assert run.launch["dialog"] is None
    _assert_healthy(ctl=ctl, run=run)


def test_launch_without_venv_exits_1_and_makes_no_run_dir(
    *, ctl: Ctl, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "labelme").mkdir(parents=True)
    (checkout / "labelme" / "__main__.py").touch()

    reply = ctl.launch_reply("{data}", checkout=checkout)

    assert reply.code == 1
    assert reply.body["ok"] is False
    assert list((tmp_path / "tmp").iterdir()) == []
    assert not (checkout / ".venv").exists()


def test_launch_makes_a_fresh_run_dir_despite_an_exported_one(*, ctl: Ctl) -> None:
    old = ctl.launch("{data}")

    new = ctl.launch("{data}", env={"LABELME_VERIFY_RUN": str(old.run_dir)})

    assert new.run_dir != old.run_dir
    _assert_healthy(ctl=ctl, run=old)
    _assert_healthy(ctl=ctl, run=new)


def test_launch_in_a_non_ascii_run_dir_with_spaces(*, ctl: Ctl, tmp_path: Path) -> None:
    run_dir = (tmp_path / "探索 dir" / "run 1").resolve()

    run = ctl.launch("{data}", run_dir=run_dir)

    _assert_healthy(ctl=ctl, run=run)
    exported = subprocess.run(
        ["bash", "-c", 'eval "$line"; printf %s "$LABELME_VERIFY_RUN"'],
        env={**os.environ, "line": run.launch["export"]},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert exported == str(run_dir)


def test_commands_after_a_crash_report_it_as_json(*, ctl: Ctl) -> None:
    run = ctl.launch("{data}")

    os.kill(run.launch["pid"], signal.SIGABRT)

    state = ctl("state", run=run)
    assert state.code == 1
    assert "crashed" in state.body["error"]
    doctor = ctl("doctor", run=run)
    assert doctor.code == 1
    assert doctor.body["healthy"] is False
    assert "crashed" in doctor.body["error"]


def test_doctor_after_cleanup_prints_json_and_exits_1(*, ctl: Ctl) -> None:
    run = ctl.launch("{data}")
    assert ctl("cleanup", run=run).code == 0

    reply = ctl("doctor", run=run)

    assert reply.code == 1
    assert reply.body["ok"] is False


def test_doctor_on_an_unresponsive_instance_prints_json_and_exits_1(
    *, ctl: Ctl
) -> None:
    run = ctl.launch("{data}")
    pid = run.launch["pid"]

    os.kill(pid, signal.SIGSTOP)
    try:
        reply = ctl("doctor", run=run)
    finally:
        os.kill(pid, signal.SIGCONT)

    assert reply.code == 1
    assert reply.body["healthy"] is False
    assert reply.body["error"]
