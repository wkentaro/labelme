from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


def _load_test_workflow() -> dict[str, Any]:
    workflow_path = Path(__file__).parents[1] / ".github/workflows/test.yml"
    workflow = YAML(typ="safe").load(workflow_path)
    assert isinstance(workflow, dict)
    return workflow


def _get_named_step(job: dict[str, Any], name: str) -> dict[str, Any]:
    matching_steps = [step for step in job["steps"] if step.get("name") == name]
    assert len(matching_steps) == 1
    return matching_steps[0]


def test_behavioral_test_matrix_covers_every_supported_environment() -> None:
    test_job = _load_test_workflow()["jobs"]["test"]
    matrix = test_job["strategy"]["matrix"]

    assert matrix == {
        "os": ["windows-latest", "macos-latest", "ubuntu-latest"],
        "python-version": ["3.12", "3.13", "3.14"],
    }
    assert test_job["strategy"]["fail-fast"] is False
    assert "if" not in test_job

    behavior_step = _get_named_step(job=test_job, name="Test behavior")
    assert "if" not in behavior_step
    assert "make test" in behavior_step["run"]
    assert "'" not in behavior_step["run"]
    assert behavior_step["env"]["PYTEST_ADDOPTS"] == '-m "not network and not snapshot"'


def test_pixel_snapshots_run_only_on_linux() -> None:
    test_job = _load_test_workflow()["jobs"]["test"]
    snapshot_step = _get_named_step(job=test_job, name="Test pixel snapshots")

    assert snapshot_step["if"] == "matrix.os == 'ubuntu-latest'"
    assert "make test" in snapshot_step["run"]
    assert snapshot_step["env"]["PYTEST_ADDOPTS"] == '-m "snapshot and not network"'


def test_network_tests_remain_in_an_isolated_job() -> None:
    jobs = _load_test_workflow()["jobs"]
    test_job = jobs["test"]
    network_job = jobs["network-test"]

    behavior_step = _get_named_step(job=test_job, name="Test behavior")
    assert "not network" in behavior_step["env"]["PYTEST_ADDOPTS"]

    snapshot_step = _get_named_step(job=test_job, name="Test pixel snapshots")
    assert "not network" in snapshot_step["env"]["PYTEST_ADDOPTS"]

    network_step = _get_named_step(job=network_job, name="Test real model download")
    assert "-m network" in network_step["run"]
