import shutil
from pathlib import Path
from typing import Final

import pytest

from tools.release_notes import extract_release_notes

PROJECT_ROOT: Final = Path(__file__).parents[3]


@pytest.fixture
def changelog() -> str:
    return """# Changelog

<!-- towncrier release notes start -->

## [7.1.0] - 2026-08-07

### Fixed

- Fixed the stable bug.

## [7.0.4] - 2026-07-12

- Older notes.
"""


@pytest.fixture
def towncrier_project(tmp_path: Path) -> Path:
    shutil.copyfile(
        src=PROJECT_ROOT / "pyproject.toml", dst=tmp_path / "pyproject.toml"
    )
    fragments = tmp_path / "changelog.d"
    fragments.mkdir()
    return tmp_path


def test_extract_release_notes_uses_exact_version_for_stable(
    changelog: str,
) -> None:
    notes, is_prerelease = extract_release_notes(
        changelog=changelog, tag="v7.1.0", project_root=PROJECT_ROOT
    )

    assert is_prerelease is False
    assert notes.strip() == "### Fixed\n\n- Fixed the stable bug."


def test_extract_release_notes_rejects_missing_section(
    changelog: str,
) -> None:
    with pytest.raises(ValueError, match=r"No CHANGELOG\.md section found for 8\.0\.0"):
        extract_release_notes(
            changelog=changelog, tag="v8.0.0", project_root=PROJECT_ROOT
        )


def test_extract_release_notes_matches_stable_version_exactly(
    changelog: str,
) -> None:
    changelog = changelog.replace("## [7.1.0]", "## [7x1x0]")

    with pytest.raises(ValueError, match=r"No CHANGELOG\.md section found for 7\.1\.0"):
        extract_release_notes(
            changelog=changelog, tag="v7.1.0", project_root=PROJECT_ROOT
        )


def test_extract_release_notes_rejects_invalid_tag(
    changelog: str,
) -> None:
    with pytest.raises(ValueError, match=r"Invalid PEP 440 release tag: v7\.x"):
        extract_release_notes(
            changelog=changelog, tag="v7.x", project_root=PROJECT_ROOT
        )


def test_extract_release_notes_rejects_prerelease_without_fragments(
    changelog: str,
    towncrier_project: Path,
) -> None:
    with pytest.raises(
        ValueError, match=r"No changelog fragments found for prerelease 7\.1\.0rc1"
    ):
        extract_release_notes(
            changelog=changelog,
            tag="v7.1.0rc1",
            project_root=towncrier_project,
        )


def test_extract_release_notes_uses_fragments_for_prerelease(
    changelog: str,
    towncrier_project: Path,
) -> None:
    (towncrier_project / "changelog.d" / "1234.added.md").write_text(
        "Added the next feature.\n", encoding="utf-8"
    )
    notes, is_prerelease = extract_release_notes(
        changelog=changelog,
        tag="v7.1.0rc1",
        project_root=towncrier_project,
    )

    assert notes.strip() == (
        "### Added\n\n"
        "- Added the next feature. "
        "([#1234](https://github.com/wkentaro/labelme/pull/1234))"
    )
    assert is_prerelease is True


def test_release_workflow_builds_and_publishes_before_prerelease_creation() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    build = workflow.index("artifact-install-smoke")
    publish = workflow.index("pypa/gh-action-pypi-publish")
    create = workflow.index('gh release create "${args[@]}"')
    assert build < publish < create
    assert 'steps.release_notes.outputs.prerelease }}" == "true"' in workflow
    assert "args+=(--prerelease)" in workflow
