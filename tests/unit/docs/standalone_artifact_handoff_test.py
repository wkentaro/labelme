from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest


@pytest.fixture
def handoff() -> str:
    REPOSITORY_ROOT: Final = Path(__file__).parents[3]
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    heading: Final = "## Standalone artifact release handoff"
    _, separator, remainder = readme.partition(heading)
    assert separator
    section = remainder.partition("\n## ")[0]
    return " ".join(section.split())


def test_names_the_external_owner_and_platforms(handoff: str) -> None:
    assert "labelme.io release pipeline" in handoff
    assert "repository does not build or launch-test" in handoff
    for platform in ("Windows", "macOS", "Linux"):
        assert platform in handoff


def test_requires_exact_release_candidate_artifacts(handoff: str) -> None:
    assert "exact release candidate artifacts" in handoff
    for identity in (
        "release candidate tag",
        "source commit",
        "unambiguous identity for each artifact",
    ):
        assert identity in handoff


def test_requires_each_artifact_to_launch(handoff: str) -> None:
    assert "Launch each recorded artifact on its target operating system" in handoff
    assert "main window is ready" in handoff


def test_requires_all_bundled_runtime_resources(handoff: str) -> None:
    for check in (
        "clean user profile and verify that the bundled Default Config at "
        "`labelme/_config/default_config.yaml` loads",
        "application icon and the visible interface icons load from the bundled "
        "`labelme/icons/` directory",
        "all expected bundled `labelme/translate/*.qm` catalogs are present and "
        "readable",
        "select one non-English translation and verify that the interface uses it",
        "required bundled AI runtime data can be read from the artifact, including "
        "`osam/_models/yoloworld/clip/bpe_simple_vocab_16e6.txt.gz`",
    ):
        assert check in handoff


def test_defines_the_release_gate_signal(handoff: str) -> None:
    assert "[#2461](https://github.com/wkentaro/labelme/issues/2461)" in handoff
    assert "one successful labelme.io release pipeline run" in handoff
    assert "Record all results before the final release is promoted" in handoff
    assert "unambiguous identity of each tested artifact" in handoff
    assert "all checks above passed on Windows, macOS, and Linux" in handoff
    assert "Without this linked signal, the release must not be promoted" in handoff
