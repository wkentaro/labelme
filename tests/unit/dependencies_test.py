from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement


@pytest.mark.parametrize(
    ("platform", "machine", "release", "webgpu"),
    [
        ("darwin", "x86_64", "25.0.0", False),
        ("darwin", "arm64", "22.6.0", False),
        ("darwin", "arm64", "23.0.0", True),
        ("darwin", "arm64", "25.0.0", True),
        ("linux", "x86_64", "6.8.0", True),
        ("win32", "AMD64", "10", True),
    ],
)
def test_osam_dependency_keeps_cpu_installs_and_supported_gpus(
    *, platform: str, machine: str, release: str, webgpu: bool
) -> None:
    project = tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())[
        "project"
    ]
    environment = {
        "sys_platform": platform,
        "platform_machine": machine,
        "platform_release": release,
    }
    requirements = [
        requirement
        for value in project["dependencies"]
        if (requirement := Requirement(value)).name == "osam"
        and (requirement.marker is None or requirement.marker.evaluate(environment))
    ]
    assert requirements
    assert any("webgpu" in requirement.extras for requirement in requirements) is webgpu


def test_gdown_keeps_the_internals_the_model_downloader_patches() -> None:
    # labelme/_model_manager.py overwrites both; a rename must fail here, not
    # in a user's download.
    cached_download = importlib.import_module("gdown.cached_download")

    assert isinstance(cached_download.cache_root, str)
    assert cached_download.shutil.move is not None
