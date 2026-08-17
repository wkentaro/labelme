import sys
from pathlib import Path

import pytest

from tools.release_notes import extract_release_notes
from tools.release_notes import main


@pytest.fixture
def changelog() -> str:
    return """# Changelog

## [Unreleased]

### Added

- Added the next feature.

## [7.1.0] - 2026-08-07

### Fixed

- Fixed the stable bug.

## [7.0.4] - 2026-07-12

- Older notes.
"""


@pytest.mark.parametrize(
    "tag",
    [
        "v7.1.0a1",
        "v7.1.0b2",
        "v7.1.0rc1",
        "v7.1.0-rc1",
        "v7.1.0.dev1",
    ],
)
def test_extract_release_notes_uses_unreleased_for_prerelease(
    changelog: str, tag: str
) -> None:
    notes, is_prerelease = extract_release_notes(changelog=changelog, tag=tag)

    assert is_prerelease is True
    assert notes.strip() == "### Added\n\n- Added the next feature."


def test_extract_release_notes_uses_exact_version_for_stable(
    changelog: str,
) -> None:
    notes, is_prerelease = extract_release_notes(changelog=changelog, tag="v7.1.0")

    assert is_prerelease is False
    assert notes.strip() == "### Fixed\n\n- Fixed the stable bug."


def test_extract_release_notes_rejects_missing_section(changelog: str) -> None:
    with pytest.raises(ValueError, match=r"No CHANGELOG\.md section found for 8\.0\.0"):
        extract_release_notes(changelog=changelog, tag="v8.0.0")


def test_extract_release_notes_matches_stable_version_exactly(changelog: str) -> None:
    changelog = changelog.replace("## [7.1.0]", "## [7x1x0]")

    with pytest.raises(ValueError, match=r"No CHANGELOG\.md section found for 7\.1\.0"):
        extract_release_notes(changelog=changelog, tag="v7.1.0")


def test_main_writes_prerelease_notes_without_changing_changelog(
    changelog: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    output_path = tmp_path / "release-notes.md"
    changelog_path.write_text(changelog, encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_notes.py",
            "v7.1.0rc1",
            str(changelog_path),
            str(output_path),
        ],
    )

    main()

    assert output_path.read_text(encoding="utf-8").strip() == (
        "### Added\n\n- Added the next feature."
    )
    assert changelog_path.read_text(encoding="utf-8") == changelog
    assert capsys.readouterr().out == "prerelease=true\n"


def test_release_workflow_builds_and_publishes_before_prerelease_creation() -> None:
    workflow = (
        Path(__file__).parents[3] / ".github" / "workflows" / "release.yml"
    ).read_text(encoding="utf-8")

    build = workflow.index("artifact-install-smoke")
    publish = workflow.index("pypa/gh-action-pypi-publish")
    create = workflow.index('gh release create "${args[@]}"')
    assert build < publish < create
    assert 'steps.release_notes.outputs.prerelease }}" == "true"' in workflow
    assert "args+=(--prerelease)" in workflow
