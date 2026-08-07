import argparse
from pathlib import Path

from packaging.version import InvalidVersion
from packaging.version import Version


def extract_release_notes(changelog: str, tag: str) -> tuple[str, bool]:
    version = tag.removeprefix("v")
    try:
        is_prerelease = Version(version).is_prerelease
    except InvalidVersion as error:
        raise ValueError(f"Invalid PEP 440 release tag: {tag}") from error

    section = "Unreleased" if is_prerelease else version
    heading = f"## [{section}]"
    lines = changelog.splitlines(keepends=True)
    try:
        start = next(
            index + 1 for index, line in enumerate(lines) if line.startswith(heading)
        )
    except StopIteration as error:
        raise ValueError(f"No CHANGELOG.md section found for {section}") from error

    end = next(
        (
            index
            for index in range(start, len(lines))
            if lines[index].startswith("## [")
        ),
        len(lines),
    )
    notes = "".join(lines[start:end])
    if not notes.strip():
        raise ValueError(f"CHANGELOG.md section for {section} is empty")
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
        )
    except ValueError as error:
        parser.error(str(error))

    args.output.write_text(notes, encoding="utf-8")
    print(f"prerelease={str(is_prerelease).lower()}")


if __name__ == "__main__":
    main()
