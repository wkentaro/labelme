#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import socket
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
WRITTEN_OPTIONS: Final = frozenset({"--output", "--config"})
SEEDS: Final = {
    "raw": "tests/data/raw",
    "annotated": "tests/data/annotated",
    "tutorial": "examples/tutorial",
}


def _load_instance(*, run_dir: Path) -> dict[str, Any]:
    path = run_dir / "instance.json"
    if not path.exists():
        sys.exit(f"no instance at {run_dir}: run `launch` first")
    return json.loads(path.read_text())


def _run_dir(*, args: argparse.Namespace) -> Path:
    value = args.run_dir or os.environ.get(RUN_ENV)
    if not value:
        sys.exit(f"pass --run-dir or set {RUN_ENV}")
    run_dir = Path(value).resolve()
    if not (run_dir / RUN_FILE).exists():
        sys.exit(f"{run_dir} has no {RUN_FILE}, so `launch` did not make it")
    return run_dir


def _claim_run_dir(*, requested: str | None) -> Path:
    if requested is None:
        run_dir = Path(tempfile.mkdtemp(prefix="verify-labelme-")).resolve()
    else:
        run_dir = Path(requested).resolve()
        if run_dir.exists() and any(run_dir.iterdir()):
            if not (run_dir / RUN_FILE).exists():
                sys.exit(f"{run_dir} is not empty and `launch` did not make it")
        run_dir.mkdir(parents=True, exist_ok=True)
    if (run_dir / "instance.json").exists():
        sys.exit(f"{run_dir} already holds an instance; clean it up or pick another")
    run_file = run_dir / RUN_FILE
    run_file.touch(mode=0o600)
    run_file.write_text(json.dumps({"token": secrets.token_hex(16)}))
    return run_dir


def _paths_outside(
    *, run_dir: Path, checkout: Path, labelme_args: list[str]
) -> list[str]:
    outside = []
    previous = ""
    for arg in labelme_args:
        option, _, value = arg.partition("=")
        if value and option in WRITTEN_OPTIONS:
            previous, arg = option, value
        path = (checkout / arg).resolve()
        if (path.exists() or previous in WRITTEN_OPTIONS) and not path.is_relative_to(
            run_dir
        ):
            outside.append(arg)
        previous = arg
    return outside


def _opens_a_path(*, checkout: Path, labelme_args: list[str]) -> bool:
    if not labelme_args or not (checkout / labelme_args[-1]).exists():
        return False
    previous = labelme_args[-2:-1]
    return not previous or previous[0] not in VALUED_OPTIONS


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


def _request(
    *, run_dir: Path, payload: dict[str, Any], timeout: float = 30
) -> dict[str, Any]:
    port = _load_instance(run_dir=run_dir)["port"]
    token = json.loads((run_dir / RUN_FILE).read_text())["token"]
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall(json.dumps({**payload, "token": token}).encode() + b"\n")
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            buf += chunk
    if not buf:
        pid = int((run_dir / "pid").read_text())
        for _ in range(50):
            if not _pid_alive(pid=pid):
                return {"did": payload["cmd"], "exited": True}
            time.sleep(0.1)
        sys.exit("labelme closed the connection without a reply; see labelme.log")
    reply = json.loads(buf)
    if not reply.get("ok"):
        _print(result=reply)
        sys.exit(1)
    return reply["result"]


def _wait_until_ready(
    *, proc: subprocess.Popen, run_dir: Path, want_image: bool, timeout: float
) -> dict[str, Any]:
    log = run_dir / "evidence" / "labelme.log"
    cleanup = f"run `labelme_ctl.py cleanup --run-dir {run_dir}`"
    deadline = time.monotonic() + timeout
    while not (run_dir / "instance.json").exists():
        if proc.poll() is not None:
            sys.exit(f"labelme exited with {proc.returncode}; see {log}")
        if time.monotonic() > deadline:
            sys.exit(f"no control port after {timeout}s; see {log}, then {cleanup}")
        time.sleep(0.1)
    while True:
        state = _request(run_dir=run_dir, payload={"cmd": "state"})
        if state["main_window"]["visible"] and (
            state["image_loaded"] or not want_image
        ):
            return state
        if time.monotonic() > deadline:
            sys.exit(f"not ready after {timeout}s, {cleanup}: {json.dumps(state)}")
        time.sleep(0.2)


def cmd_launch(*, args: argparse.Namespace) -> None:
    if os.name == "nt":
        sys.exit("labelme_ctl.py supports macOS and Linux")
    checkout = Path(args.checkout).resolve()
    if not (checkout / "labelme" / "__main__.py").exists():
        sys.exit(f"not a labelme checkout: {checkout}")
    run_dir = _claim_run_dir(requested=args.run_dir)
    home, data, evidence = run_dir / "home", run_dir / "data", run_dir / "evidence"
    for directory in (home, data, evidence):
        directory.mkdir(parents=True, exist_ok=True)
    (home / ".labelmerc").write_text(f"language: {args.language}\n")
    if args.seed != "none":
        shutil.copytree(checkout / SEEDS[args.seed], data, dirs_exist_ok=True)

    subprocess.run(["uv", "sync", "--frozen", "--quiet"], cwd=checkout, check=True)

    labelme_args = [a.replace("{data}", str(data)) for a in args.labelme_args]
    if labelme_args[:1] == ["--"]:
        labelme_args = labelme_args[1:]
    outside = _paths_outside(
        run_dir=run_dir, checkout=checkout, labelme_args=labelme_args
    )
    if outside:
        sys.exit(f"labelme may write these, so copy them into {data}: {outside}")
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "QT_QPA_PLATFORM": "offscreen",
    }
    env.pop("QT_QPA_PLATFORMTHEME", None)
    with open(evidence / "labelme.log", "w") as log:
        proc = subprocess.Popen(
            [
                str(checkout / ".venv" / "bin" / "python"),
                str(Path(__file__).resolve()),
                "serve",
                "--run-dir",
                str(run_dir),
                "--size",
                args.size,
                "--",
                *labelme_args,
            ],
            cwd=checkout,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    (run_dir / "pid").write_text(str(proc.pid))

    state = _wait_until_ready(
        proc=proc,
        run_dir=run_dir,
        want_image=_opens_a_path(checkout=checkout, labelme_args=labelme_args),
        timeout=args.timeout,
    )
    _print(
        result={
            "run_dir": str(run_dir),
            "export": f"export {RUN_ENV}={run_dir}",
            "pid": proc.pid,
            "data": str(data),
            "evidence": str(evidence),
            "title": state["main_window"]["title"],
        }
    )


def _git(*, checkout: Path, args: list[str]) -> str:
    return subprocess.run(
        ["git", *args], cwd=checkout, capture_output=True, text=True
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
        (not info["crash_dialog"], f"crash dialog is open: {info['crash_dialog']}"),
        (info["platform"] == "offscreen", "not running offscreen"),
    ]
    return [message for ok, message in checks if not ok]


def cmd_doctor(*, args: argparse.Namespace) -> None:
    run_dir = _run_dir(args=args)
    pid = int((run_dir / "pid").read_text())
    report: dict[str, Any] = {
        "run_dir": str(run_dir),
        "pid": pid,
        "pid_alive": _pid_alive(pid=pid),
        "pid_is_ours": _pid_is_ours(pid=pid, run_dir=run_dir),
        "healthy": False,
    }
    try:
        info = _request(run_dir=run_dir, payload={"cmd": "doctor"}, timeout=5)
    except OSError as e:
        report["control_port"] = f"unreachable: {e}"
        _print(result=report)
        sys.exit(1)
    checkout = Path(_load_instance(run_dir=run_dir)["checkout"])
    status = ["status", "--porcelain", "--untracked-files=no"]
    report.update(info)
    report["checkout_head"] = _git(checkout=checkout, args=["rev-parse", "HEAD"])
    report["checkout_dirty"] = bool(_git(checkout=checkout, args=status))
    report["problems"] = _problems(info=info, run_dir=run_dir, pid=pid)
    report["healthy"] = report["pid_is_ours"] and not report["problems"]
    _print(result=report)
    sys.exit(0 if report["healthy"] else 1)


def cmd_forward(*, args: argparse.Namespace) -> None:
    payload = {k: v for k, v in vars(args).items() if k not in ("func", "run_dir")}
    _print(result=_request(run_dir=_run_dir(args=args), payload=payload))


def cmd_screenshot(*, args: argparse.Namespace) -> None:
    run_dir = _run_dir(args=args)
    path = Path(args.name)
    if not path.is_absolute():
        path = run_dir / "evidence" / path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cmd": "screenshot", "path": str(path), "window": args.window}
    _print(result=_request(run_dir=run_dir, payload=payload))


def _conditions_hold(*, args: argparse.Namespace, state: dict[str, Any]) -> bool:
    modal = state["modal"]
    checks = []
    if args.title:
        checks.append(args.title in state["main_window"]["title"])
    if args.status:
        checks.append(args.status in " ".join(state["status_bar"]))
    if args.dialog:
        checks.append(modal is not None and args.dialog in modal["title"])
    if args.no_dialog:
        checks.append(modal is None)
    if args.file:
        checks.append(Path(args.file).exists())
    if args.image_loaded:
        checks.append(state["image_loaded"])
    return all(checks)


def cmd_wait(*, args: argparse.Namespace) -> None:
    run_dir = _run_dir(args=args)
    deadline = time.monotonic() + args.timeout
    while True:
        state = _request(run_dir=run_dir, payload={"cmd": "state"})
        if _conditions_hold(args=args, state=state):
            _print(result=state)
            return
        if time.monotonic() > deadline:
            _print(result=state)
            sys.exit(f"wait timed out after {args.timeout}s")
        time.sleep(0.1)


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
    for name in ("home", "data", "instance.json"):
        target = run_dir / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    _print(result={"killed": killed, "evidence_kept": str(run_dir / "evidence")})


def cmd_serve(*, args: argparse.Namespace) -> None:
    from _labelme_ctl_server import serve  # noqa: PLC0415 -- needs labelme's venv

    serve(run_dir=Path(args.run_dir), size=args.size, labelme_args=args.labelme_args)


def _add_launch(*, p: argparse.ArgumentParser) -> None:
    p.add_argument("--checkout", default=".", help="labelme tree to run")
    p.add_argument("--seed", choices=[*SEEDS, "none"], default="raw")
    p.add_argument("--language", default="en_US", help="UI language code")
    p.add_argument("--size", default="1280x800")
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("labelme_args", nargs=argparse.REMAINDER)


def _add_canvas(*, p: argparse.ArgumentParser, coordinates: tuple[str, ...]) -> None:
    for coordinate in coordinates:
        p.add_argument(coordinate, type=float)
    p.add_argument("--button", choices=["left", "right", "middle"], default="left")


def _add_wait(*, p: argparse.ArgumentParser) -> None:
    p.add_argument("--title")
    p.add_argument("--status")
    p.add_argument("--dialog")
    p.add_argument("--no-dialog", action="store_true")
    p.add_argument("--file")
    p.add_argument("--image-loaded", action="store_true")
    p.add_argument("--timeout", type=float, default=10)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="labelme_ctl.py")
    sub = parser.add_subparsers(required=True)

    def add(
        *, name: str, about: str, run: Callable[..., None] = cmd_forward
    ) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=about)
        p.add_argument("--run-dir", help=f"defaults to ${RUN_ENV}")
        p.set_defaults(func=run, cmd=name)
        return p

    about = "start labelme offscreen with a scratch HOME"
    _add_launch(p=add(name="launch", about=about, run=cmd_launch))
    about = "check the instance is ours, alive, and from the checkout"
    add(name="doctor", about=about, run=cmd_doctor)
    add(name="state", about="visible state of every window as JSON")
    add(name="menu", about="menu items with enabled and checked state")
    add(name="action", about="choose a menu item, e.g. 'File > Save'").add_argument(
        "path"
    )
    add(name="key", about="press a key sequence on the focused widget").add_argument(
        "sequence", help="QKeySequence text, e.g. Ctrl+S, Return"
    )
    add(name="type", about="type text into the focused widget").add_argument("text")
    about = "click a button or text field by text, tooltip, or placeholder"
    add(name="click", about=about).add_argument("name")

    p = add(name="pick", about="click a row in a list by its text")
    p.add_argument("list", help="dock title or accessible name, e.g. 'Image List'")
    p.add_argument("text")
    p.add_argument("--double", action="store_true")
    p.add_argument("--modifier", choices=["ctrl", "shift"])

    p = add(name="click-canvas", about="click the canvas at image pixel X Y")
    _add_canvas(p=p, coordinates=("x", "y"))
    p.add_argument("--double", action="store_true")
    p.add_argument("--modifier", choices=["ctrl", "shift"])
    p = add(name="drag-canvas", about="drag on the canvas between image pixels")
    _add_canvas(p=p, coordinates=("x1", "y1", "x2", "y2"))

    p = add(name="screenshot", about="save a PNG under evidence/", run=cmd_screenshot)
    p.add_argument("name")
    p.add_argument("--window", choices=["active", "main"], default="active")

    about = "poll state until every given condition holds"
    _add_wait(p=add(name="wait", about=about, run=cmd_wait))
    about = "kill our labelme, delete home/ and data/, keep evidence/"
    add(name="cleanup", about=about, run=cmd_cleanup)

    p = sub.add_parser("serve", help=argparse.SUPPRESS)
    p.add_argument("--run-dir", required=True)
    p.add_argument("--size", required=True)
    p.add_argument("labelme_args", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_serve)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    args.func(args=args)


if __name__ == "__main__":
    main()
