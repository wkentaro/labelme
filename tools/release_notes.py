import argparse
import subprocess
import sys
from pathlib import Path

from packaging.version import InvalidVersion
from packaging.version import Version


def extract_release_notes(
    changelog: str, tag: str, project_root: Path
) -> tuple[str, bool]:
    version = tag.removeprefix("v")
    try:
        is_prerelease = Version(version).is_prerelease
    except InvalidVersion as error:
        raise ValueError(f"Invalid PEP 440 release tag: {tag}") from error

    if is_prerelease:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "towncrier",
                "build",
                "--draft",
                "--version",
                version,
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=project_root,
        )
        changelog = result.stdout

    heading = f"## [{version}]"
    lines = changelog.splitlines(keepends=True)
    try:
        start = next(
            index + 1 for index, line in enumerate(lines) if line.startswith(heading)
        )
    except StopIteration as error:
        raise ValueError(f"No CHANGELOG.md section found for {version}") from error

    end = next(
        (
            index
            for index in range(start, len(lines))
            if lines[index].startswith("## [")
        ),
        len(lines),
    )
    notes = "".join(lines[start:end])
    if is_prerelease and notes.strip() == "No significant changes.":
        raise ValueError(f"No changelog fragments found for prerelease {version}")
    if not notes.strip():
        raise ValueError(f"CHANGELOG.md section for {version} is empty")
    return notes, is_prerelease


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag")
    parser.add_argument("changelog", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    try:
        notes, is_prerelease = extract_release_notes(
            changelog=args.changelog.read_text(encoding="utf-8"),
            tag=args.tag,
            project_root=Path(__file__).resolve().parent.parent,
        )
    except ValueError as error:
        parser.error(str(error))

    args.output.write_text(notes, encoding="utf-8")
    print(f"prerelease={str(is_prerelease).lower()}")


if __name__ == "__main__":
    main()
