#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from typing import Final

RUN_ENV: Final = "LABELME_VERIFY_RUN"
SERVE_MARKER: Final = "labelme_ctl.py"
RUN_FILE: Final = "run.json"
EXIT_FILE: Final = "exit_code"
RUN_TOOL: Final = "verify-labelme"
RUN_FILE_MODE: Final = 0o600
FRESH_SUBDIRS: Final = ("home", "data", "tmp")
EXIT_GRACE_S: Final = 5
WAIT_POLL_S: Final = 0.1
VALUED_OPTIONS: Final = frozenset(
    {
        "--logger-level",
        "--output",
        "--config",
        "--flags",
        "--label-flags",
        "--labelflags",
        "--labels",
        "--validate-label",
        "--validatelabel",
        "--epsilon",
    }
)
SANDBOX_PROFILE: Final = """(version 1)
(allow default)
(deny file-write* (require-not (require-any (subpath {run_dir}) (literal "/dev/null"))))
(deny user-preference-write)
"""
LANGUAGE: Final = "en_US"
SEEDS: Final = {
    "raw": "tests/data/raw",
    "annotated": "tests/data/annotated",
    "tutorial": "examples/tutorial",
}


class CtlFailure(Exception):
    details: dict[str, Any]

    def __init__(
        self, message: str, /, *, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.details = details or {}


def _load_instance(*, run_dir: Path) -> dict[str, Any]:
    path = run_dir / "instance.json"
    if not path.exists():
        raise CtlFailure(f"no instance at {run_dir}: run `launch` first")
    return json.loads(path.read_text())


def _load_pid(*, run_dir: Path) -> int:
    path = run_dir / "pid"
    if not path.exists():
        raise CtlFailure(f"no instance at {run_dir}: run `launch` first")
    return int(path.read_text())


def _run_dir(*, args: argparse.Namespace) -> Path:
    value = args.run_dir or os.environ.get(RUN_ENV)
    if not value:
        raise CtlFailure(f"pass --run-dir or set {RUN_ENV}")
    run_dir = Path(value).resolve()
    if not _made_by_launch(run_dir=run_dir):
        raise CtlFailure(
            f"{run_dir} has no private {RUN_FILE} from `launch`; leaving it alone"
        )
    return run_dir


def _made_by_launch(*, run_dir: Path) -> bool:
    run_file = run_dir / RUN_FILE
    if not run_file.is_file():
        return False
    info = run_file.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != RUN_FILE_MODE:
        return False
    try:
        marker = json.loads(run_file.read_text())
    except (OSError, ValueError):
        return False
    return isinstance(marker, dict) and marker.get("tool") == RUN_TOOL


def _claim_run_dir(*, requested: str | None) -> Path:
    if requested is None:
        run_dir = Path(tempfile.mkdtemp(prefix="verify-labelme-")).resolve()
    else:
        run_dir = Path(requested).resolve()
        if run_dir.exists() and any(run_dir.iterdir()):
            if not _made_by_launch(run_dir=run_dir):
                raise CtlFailure(f"{run_dir} is not empty and `launch` did not make it")
        run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "instance.json").exists():
        raise CtlFailure(
            f"{run_dir} already holds an instance; clean it up or pick another"
        )
    leftover = [name for name in FRESH_SUBDIRS if os.path.lexists(run_dir / name)]
    if leftover:
        raise CtlFailure(
            f"{run_dir} still holds {', '.join(leftover)}; clean it up or pick another"
        )
    if (run_dir / "evidence").is_symlink():
        raise CtlFailure(f"{run_dir}/evidence is a symlink; pick another")
    (run_dir / EXIT_FILE).unlink(missing_ok=True)
    marker = {"tool": RUN_TOOL, "token": secrets.token_hex(16)}
    run_file = run_dir / RUN_FILE
    _write_new(path=run_file, text=json.dumps(marker), mode=RUN_FILE_MODE)
    run_file.chmod(RUN_FILE_MODE)
    return run_dir


def _create_new(*, path: Path, mode: int = 0o644) -> int:
    path.unlink(missing_ok=True)
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)


def _write_new(*, path: Path, text: str, mode: int = 0o644) -> None:
    with os.fdopen(_create_new(path=path, mode=mode), "w") as file:
        file.write(text)


def _names_option(*, arg: str, options: frozenset[str]) -> bool:
    name = arg.partition("=")[0]
    return (
        name.startswith("--")
        and len(name) > len("--")
        and any(option.startswith(name) for option in options)
    )


def _opened_path(*, checkout: Path, labelme_args: list[str]) -> Path | None:
    if not labelme_args or not (checkout / labelme_args[-1]).exists():
        return None
    previous = labelme_args[-2:-1]
    if previous and _names_option(arg=previous[0], options=VALUED_OPTIONS):
        return None
    return checkout / labelme_args[-1]


def _pid_alive(*, pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _pid_is_ours(*, pid: int, run_dir: Path) -> bool:
    if not _pid_alive(pid=pid):
        return False
    command = subprocess.run(
        ["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True
    ).stdout
    return SERVE_MARKER in command and str(run_dir) in command


def _print(*, result: object) -> None:
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _remaining(*, deadline: float) -> float:
    return max(deadline - time.monotonic(), 0.01)


def _request(
    *, run_dir: Path, payload: dict[str, Any], timeout: float = 30
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    port = _load_instance(run_dir=run_dir)["port"]
    token = json.loads((run_dir / RUN_FILE).read_text())["token"]
    buf = b""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            s.sendall(json.dumps({**payload, "token": token}).encode() + b"\n")
            while not buf.endswith(b"\n"):
                s.settimeout(_remaining(deadline=deadline))
                chunk = s.recv(1 << 20)
                if not chunk:
                    break
                buf += chunk
    except OSError as e:
        unreachable = f"control port unreachable: {e}"
    else:
        unreachable = "labelme closed the connection without a reply"
    if not buf:
        pid = _load_pid(run_dir=run_dir)
        grace_end = min(deadline, time.monotonic() + EXIT_GRACE_S)
        while _pid_alive(pid=pid):
            if time.monotonic() >= grace_end:
                log = run_dir / "evidence" / "labelme.log"
                raise CtlFailure(f"{unreachable}; see {log}")
            time.sleep(0.1)
        return _exited(run_dir=run_dir, cmd=payload["cmd"])
    reply = json.loads(buf)
    if not reply.get("ok"):
        _print(result=reply)
        sys.exit(1)
    return reply["result"]


def _exited(*, run_dir: Path, cmd: str) -> dict[str, Any]:
    exit_file = run_dir / EXIT_FILE
    if not exit_file.exists():
        log = run_dir / "evidence" / "labelme.log"
        raise CtlFailure(f"labelme crashed without exiting; see {log}")
    return {"did": cmd, "exited": True, "exit_code": int(exit_file.read_text())}


def _image_list_rows(*, state: dict[str, Any]) -> int:
    return sum(
        len(view["rows"])
        for dock in state["docks"]
        if dock["title"] == "Image List"
        for view in dock.get("lists", [])
    )


def _settled(*, state: dict[str, Any], opened: Path | None) -> bool:
    if state["dialog"] is not None:
        return True
    if not state["main_window"]["visible"]:
        return False
    if opened is None or state["image_loaded"]:
        return True
    return opened.is_dir() and _image_list_rows(state=state) == 0


def _wait_until_ready(
    *, proc: subprocess.Popen, run_dir: Path, opened: Path | None, timeout: float
) -> dict[str, Any]:
    log = run_dir / "evidence" / "labelme.log"
    cleanup = f"run `labelme_ctl.py cleanup --run-dir {run_dir}`"
    deadline = time.monotonic() + timeout
    while not (run_dir / "instance.json").exists():
        if proc.poll() is not None:
            raise CtlFailure(
                f"labelme exited with {proc.returncode}; see {log}",
                details={"exited": True, "exit_code": proc.returncode},
            )
        if time.monotonic() > deadline:
            raise CtlFailure(
                f"no control port after {timeout}s; see {log}, then {cleanup}"
            )
        time.sleep(0.1)
    while True:
        state = _request(
            run_dir=run_dir,
            payload={"cmd": "state"},
            timeout=_remaining(deadline=deadline),
        )
        if _settled(state=state, opened=opened):
            return state
        if time.monotonic() > deadline:
            raise CtlFailure(
                f"not ready after {timeout}s, {cleanup}: {json.dumps(state)}"
            )
        time.sleep(0.2)


def cmd_launch(*, args: argparse.Namespace) -> None:
    if sys.platform != "darwin":
        raise CtlFailure(
            "labelme_ctl.py needs macOS sandbox-exec to keep writes in the run dir"
        )
    checkout = Path(args.checkout).resolve()
    if not (checkout / "labelme" / "__main__.py").exists():
        raise CtlFailure(f"not a labelme checkout: {checkout}")
    python = checkout / ".venv" / "bin" / "python"
    if not python.exists():
        raise CtlFailure(f"no {python}: run `uv sync --frozen` in {checkout} first")
    run_dir = _claim_run_dir(requested=args.run_dir)
    home, data, evidence = run_dir / "home", run_dir / "data", run_dir / "evidence"
    home.mkdir()
    evidence.mkdir(exist_ok=True)
    _write_new(path=home / ".labelmerc", text=f"language: {LANGUAGE}\n")
    if args.seed == "none":
        data.mkdir()
    else:
        shutil.copytree(checkout / SEEDS[args.seed], data)

    labelme_args = [a.replace("{data}", str(data)) for a in args.labelme_args]
    if labelme_args[:1] == ["--"]:
        labelme_args = labelme_args[1:]
    profile = run_dir / "sandbox.sb"
    _write_new(
        path=profile,
        text=SANDBOX_PROFILE.format(
            run_dir=json.dumps(str(run_dir), ensure_ascii=False)
        ),
    )
    (run_dir / "tmp").mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "TMPDIR": str(run_dir / "tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "QT_QPA_PLATFORM": "offscreen",
    }
    env.pop("QT_QPA_PLATFORMTHEME", None)
    with os.fdopen(_create_new(path=evidence / "labelme.log"), "w") as log:
        proc = subprocess.Popen(
            [
                "/usr/bin/sandbox-exec",
                "-f",
                str(profile),
                str(python),
                str(Path(__file__).resolve()),
                "serve",
                "--run-dir",
                str(run_dir),
                "--",
                *labelme_args,
            ],
            cwd=checkout,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    _write_new(path=run_dir / "pid", text=str(proc.pid))

    state = _wait_until_ready(
        proc=proc,
        run_dir=run_dir,
        opened=_opened_path(checkout=checkout, labelme_args=labelme_args),
        timeout=args.timeout,
    )
    _print(
        result={
            "run_dir": str(run_dir),
            "export": f"export {RUN_ENV}={shlex.quote(str(run_dir))}",
            "pid": proc.pid,
            "data": str(data),
            "evidence": str(evidence),
            "title": state["main_window"]["title"],
            "image_loaded": state["image_loaded"],
            "dialog": state["dialog"],
        }
    )


def _git(*, checkout: Path, args: list[str]) -> str:
    return subprocess.run(
        ["git", "--no-optional-locks", *args],
        cwd=checkout,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _problems(*, info: dict[str, Any], run_dir: Path, pid: int) -> list[str]:
    checkout = _load_instance(run_dir=run_dir)["checkout"]
    home = str(run_dir / "home")
    checks = [
        (info["pid"] == pid, "control port answered from a different process"),
        (
            info["labelme_file"].startswith(checkout),
            "labelme imported from outside the checkout",
        ),
        (info["home"] == home, "HOME is not the run's scratch home"),
        (
            info["window_state_file"].startswith(home),
            "window state is not stored in the scratch home",
        ),
        (
            not info["uncaught_exception"],
            f"labelme hit an uncaught exception: {info['uncaught_exception']}",
        ),
        (info["platform"] == "offscreen", "not running offscreen"),
        (info["writes_confined"], "labelme can write outside the run dir"),
    ]
    return [message for ok, message in checks if not ok]


def cmd_doctor(*, args: argparse.Namespace) -> None:
    run_dir = _run_dir(args=args)
    report: dict[str, Any] = {"run_dir": str(run_dir), "healthy": False}
    try:
        pid = _load_pid(run_dir=run_dir)
        report["pid"] = pid
        report["pid_alive"] = _pid_alive(pid=pid)
        report["pid_is_ours"] = _pid_is_ours(pid=pid, run_dir=run_dir)
        info = _request(run_dir=run_dir, payload={"cmd": "doctor"}, timeout=5)
    except CtlFailure as e:
        raise CtlFailure(str(e), details=report) from e
    if info.get("exited"):
        report["exit_code"] = info["exit_code"]
        raise CtlFailure(f"labelme exited with {info['exit_code']}", details=report)
    checkout = Path(_load_instance(run_dir=run_dir)["checkout"])
    status = ["status", "--porcelain", "--untracked-files=normal"]
    report.update(info)
    report["checkout_head"] = _git(checkout=checkout, args=["rev-parse", "HEAD"])
    report["checkout_dirty"] = bool(_git(checkout=checkout, args=status))
    report["problems"] = _problems(info=info, run_dir=run_dir, pid=pid)
    if not report["pid_is_ours"]:
        report["problems"].insert(0, "the PID is not the process this run started")
    if report["problems"]:
        raise CtlFailure("; ".join(report["problems"]), details=report)
    report["healthy"] = True
    _print(result=report)


def cmd_forward(*, args: argparse.Namespace) -> None:
    payload = {k: v for k, v in vars(args).items() if k not in ("func", "run_dir")}
    _print(result=_request(run_dir=_run_dir(args=args), payload=payload))


def cmd_screenshot(*, args: argparse.Namespace) -> None:
    run_dir = _run_dir(args=args)
    evidence = run_dir / "evidence"
    path = (evidence / args.name).resolve()
    if not path.is_relative_to(evidence.resolve()):
        raise CtlFailure(f"screenshots go under {evidence}; pass a relative name")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cmd": "screenshot", "path": str(path), "window": args.window}
    _print(result=_request(run_dir=run_dir, payload=payload))


def _conditions_hold(*, args: argparse.Namespace, state: dict[str, Any]) -> bool:
    checks = []
    if args.status:
        checks.append(args.status in " ".join(state["status_bar"]))
    if args.no_dialog:
        checks.append(state["dialog"] is None)
    if args.file:
        checks.append(Path(args.file).exists())
    return all(checks)


def _poll_state(*, run_dir: Path, deadline: float) -> dict[str, Any]:
    state = _request(
        run_dir=run_dir,
        payload={"cmd": "state"},
        timeout=_remaining(deadline=deadline),
    )
    if state.get("exited"):
        raise CtlFailure(
            "labelme exited before the conditions held",
            details={"exited": True, "exit_code": state["exit_code"]},
        )
    return state


def cmd_wait(*, args: argparse.Namespace) -> None:
    run_dir = _run_dir(args=args)
    deadline = time.monotonic() + args.timeout
    state = _poll_state(run_dir=run_dir, deadline=deadline)
    while not _conditions_hold(args=args, state=state):
        time.sleep(min(WAIT_POLL_S, max(deadline - time.monotonic(), 0)))
        if time.monotonic() >= deadline:
            raise CtlFailure(
                f"wait timed out after {args.timeout}s: {json.dumps(state)}"
            )
        state = _poll_state(run_dir=run_dir, deadline=deadline)
    _print(result=state)


def _stop(*, pid: int, run_dir: Path) -> None:
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if not _pid_is_ours(pid=pid, run_dir=run_dir):
            return
        time.sleep(0.1)
    os.kill(pid, signal.SIGKILL)


def cmd_cleanup(*, args: argparse.Namespace) -> None:
    run_dir = _run_dir(args=args)
    pid_file = run_dir / "pid"
    killed = False
    if pid_file.exists():
        pid = int(pid_file.read_text())
        if _pid_is_ours(pid=pid, run_dir=run_dir):
            _stop(pid=pid, run_dir=run_dir)
            killed = True
        pid_file.unlink()
    for name in ("home", "data", "tmp", "sandbox.sb", "instance.json", EXIT_FILE):
        target = run_dir / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    _print(result={"killed": killed, "evidence_kept": str(run_dir / "evidence")})


def cmd_serve(*, args: argparse.Namespace) -> None:
    from _labelme_ctl_server import serve  # noqa: PLC0415 -- needs labelme's venv

    serve(run_dir=Path(args.run_dir), labelme_args=args.labelme_args)


def _add_launch(*, p: argparse.ArgumentParser) -> None:
    p.add_argument("--checkout", default=".", help="labelme tree to run")
    p.add_argument("--seed", choices=[*SEEDS, "none"], default="raw")
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("labelme_args", nargs=argparse.REMAINDER)


def _add_wait(*, p: argparse.ArgumentParser) -> None:
    p.add_argument("--status")
    p.add_argument("--no-dialog", action="store_true")
    p.add_argument("--file")
    p.add_argument("--timeout", type=float, default=10)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="labelme_ctl.py")
    sub = parser.add_subparsers(required=True)

    def add(
        *,
        name: str,
        about: str,
        run: Callable[..., None] = cmd_forward,
        run_dir_help: str = f"defaults to ${RUN_ENV}",
    ) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=about)
        p.add_argument("--run-dir", help=run_dir_help)
        p.set_defaults(func=run, cmd=name)
        return p

    about = "start labelme offscreen with a scratch HOME"
    fresh = "a new, empty, or cleaned-up run dir; defaults to a fresh mktemp directory"
    _add_launch(p=add(name="launch", about=about, run=cmd_launch, run_dir_help=fresh))
    about = "check the instance is ours, alive, and from the checkout"
    add(name="doctor", about=about, run=cmd_doctor)
    add(name="state", about="visible state of every window as JSON")

    p = add(name="screenshot", about="save a PNG under evidence/", run=cmd_screenshot)
    p.add_argument("name")
    p.add_argument("--window", choices=["active", "main"], default="active")

    about = "poll state until every given condition holds"
    _add_wait(p=add(name="wait", about=about, run=cmd_wait))
    about = "kill our labelme, delete home/ and data/, keep evidence/"
    add(name="cleanup", about=about, run=cmd_cleanup)

    p = sub.add_parser("serve", help=argparse.SUPPRESS)
    p.add_argument("--run-dir", required=True)
    p.add_argument("labelme_args", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_serve)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    try:
        args.func(args=args)
    except CtlFailure as e:
        _print(result={"ok": False, "error": str(e), **e.details})
        sys.exit(1)


if __name__ == "__main__":
    main()
