import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Final

import pytest
from ruamel.yaml import YAML

_REPO_ROOT: Final = Path(__file__).parents[1]


@pytest.mark.skipif(sys.platform != "darwin", reason="requires BSD sed")
def test_release_without_version_suggests_next_version(tmp_path: Path) -> None:
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "changelog.d" / "1.fixed.md").write_text("Fixed a bug.\n")
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "--quiet",
            "-m",
            "base",
        ],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "tag", "v1.2.3"], cwd=tmp_path, check=True)

    result = subprocess.run(
        [
            shutil.which("just") or "just",
            "--justfile",
            _REPO_ROOT / "justfile",
            "--working-directory",
            tmp_path,
            "release",
        ],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin"},
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "suggested: just release 1.2.4" in result.stderr
    assert "recent releases:\n  v1.2.3" in result.stderr


def test_test_matrix_covers_every_supported_python_version() -> None:
    # The only silent coverage gap: a new version classifier without a matrix
    # update keeps CI green while the new version ships untested.
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    supported_versions = {
        match.group(1)
        for classifier in pyproject["project"]["classifiers"]
        if (
            match := re.fullmatch(
                r"Programming Language :: Python :: (3\.\d+)", classifier
            )
        )
    }
    assert supported_versions

    workflow = YAML(typ="safe").load(_REPO_ROOT / ".github/workflows/test.yml")
    matrix = workflow["jobs"]["test"]["strategy"]["matrix"]
    assert set(matrix["python-version"]) == supported_versions
    assert set(matrix["os"]) == {"windows-latest", "macos-latest", "ubuntu-latest"}
