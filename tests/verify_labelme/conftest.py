from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Final

import pytest

REPO: Final = Path(__file__).resolve().parents[2]
CTL: Final = (
    REPO / ".claude" / "skills" / "verify-labelme" / "scripts" / "labelme_ctl.py"
)
CTL_TIMEOUT: Final = 180


@dataclass(frozen=True)
class Reply:
    code: int
    body: dict[str, Any]


@dataclass(frozen=True)
class Run:
    run_dir: Path
    launch: dict[str, Any]

    @property
    def data(self) -> Path:
        return self.run_dir / "data"


class Ctl:
    _tmp_path: Path
    _run_dirs: list[Path]

    def __init__(self, *, tmp_path: Path) -> None:
        self._tmp_path = tmp_path
        self._run_dirs = []
        (tmp_path / "tmp").mkdir()

    def __call__(
        self,
        command: str,
        /,
        *args: str,
        run: Run | None = None,
        env: dict[str, str] | None = None,
    ) -> Reply:
        run_dir = [] if run is None else ["--run-dir", str(run.run_dir)]
        proc = subprocess.run(
            [sys.executable, str(CTL), command, *run_dir, *args],
            capture_output=True,
            text=True,
            timeout=CTL_TIMEOUT,
            env={
                **os.environ,
                "TMPDIR": str(self._tmp_path / "tmp"),
                **(env or {}),
            },
        )
        return Reply(code=proc.returncode, body=json.loads(proc.stdout))

    def ok(self, command: str, /, *args: str, run: Run) -> dict[str, Any]:
        reply = self(command, *args, run=run)
        assert reply.code == 0, reply.body
        return reply.body

    def launch_reply(
        self,
        *labelme_args: str,
        seed: str = "raw",
        run_dir: Path | None = None,
        checkout: Path = REPO,
        env: dict[str, str] | None = None,
    ) -> Reply:
        args = ["--checkout", str(checkout), "--seed", seed]
        if run_dir is not None:
            args += ["--run-dir", str(run_dir)]
            self._run_dirs.append(run_dir)
        return self("launch", *args, "--", *labelme_args, env=env)

    def launch(
        self,
        *labelme_args: str,
        seed: str = "raw",
        run_dir: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> Run:
        reply = self.launch_reply(*labelme_args, seed=seed, run_dir=run_dir, env=env)
        assert reply.code == 0, reply.body
        return Run(run_dir=Path(reply.body["run_dir"]), launch=reply.body)

    def cleanup_all(self) -> None:
        made_by_mktemp = (self._tmp_path / "tmp").glob("verify-labelme-*")
        for run_dir in {*self._run_dirs, *made_by_mktemp}:
            subprocess.run(
                [sys.executable, str(CTL), "cleanup", "--run-dir", str(run_dir)],
                capture_output=True,
                timeout=CTL_TIMEOUT,
            )


@pytest.fixture()
def ctl(*, tmp_path: Path) -> Iterator[Ctl]:
    controller = Ctl(tmp_path=tmp_path)
    try:
        yield controller
    finally:
        controller.cleanup_all()
