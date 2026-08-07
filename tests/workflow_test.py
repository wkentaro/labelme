import re
import tomllib
from pathlib import Path

from ruamel.yaml import YAML

_REPO_ROOT = Path(__file__).parents[1]


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
