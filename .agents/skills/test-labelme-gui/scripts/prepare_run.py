from __future__ import annotations

import argparse
import datetime
import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from labelme import __version__


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="labelme repository root (default: current directory)",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="new or empty run directory (default: an OS temporary directory)",
    )
    parser.add_argument(
        "--profile",
        choices=("smoke", "nightly", "weekly", "release"),
        default="smoke",
    )
    parser.add_argument(
        "--theme", choices=("system", "light", "dark"), default="system"
    )
    return parser.parse_args()


def create_run_directory(requested_path: Path | None) -> Path:
    if requested_path is None:
        return Path(tempfile.mkdtemp(prefix="labelme-gui-qa."))

    run_dir = requested_path.expanduser().resolve()
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError(f"run directory must be empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def copy_fixture(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_inputs(repo_root: Path, run_dir: Path) -> dict[str, str]:
    inputs_dir = run_dir / "inputs"
    outputs_dir = run_dir / "outputs"

    raw_dir = inputs_dir / "raw"
    copy_fixture(
        source=repo_root / "examples/primitives/primitives.jpg",
        destination=raw_dir / "primitives.jpg",
    )

    annotated_dir = outputs_dir / "annotated"
    for suffix in (".jpg", ".json"):
        copy_fixture(
            source=repo_root / f"examples/primitives/primitives{suffix}",
            destination=annotated_dir / f"primitives{suffix}",
        )

    sequence_dir = inputs_dir / "sequence"
    sequence_source = repo_root / "examples/video_annotation/data_annotated"
    for source in sorted(sequence_source.glob("0000010[0-4].*")):
        copy_fixture(source=source, destination=sequence_dir / source.name)

    corrupt_dir = inputs_dir / "corrupt"
    copy_fixture(
        source=repo_root / "examples/primitives/primitives.jpg",
        destination=corrupt_dir / "primitives.jpg",
    )
    (corrupt_dir / "primitives.json").write_text(
        "{ this is intentionally invalid JSON\n", encoding="utf-8"
    )

    missing_image_dir = inputs_dir / "missing-image"
    copy_fixture(
        source=repo_root / "examples/primitives/primitives.json",
        destination=missing_image_dir / "primitives.json",
    )

    return {
        "raw": str(raw_dir),
        "annotated": str(annotated_dir / "primitives.json"),
        "sequence": str(sequence_dir),
        "corrupt": str(corrupt_dir / "primitives.json"),
        "missing-image": str(missing_image_dir / "primitives.json"),
    }


def get_git_state(repo_root: Path) -> tuple[str, bool]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return revision, bool(status)


def write_config(run_dir: Path, theme: str) -> Path:
    config_path = run_dir / "config.yaml"
    config_path.write_text(f"color_theme: {theme}\nauto_save: true\n", encoding="utf-8")
    return config_path


def write_report(run_dir: Path, manifest: dict[str, object]) -> Path:
    report_path = run_dir / "report.md"
    report_path.write_text(
        "\n".join(
            [
                "# Labelme GUI QA report",
                "",
                "## Verdict and coverage",
                "",
                "In progress.",
                "",
                "## Run metadata",
                "",
                f"- Profile: {manifest['profile']}",
                f"- Theme: {manifest['theme']}",
                f"- App version: `{manifest['app_version']}`",
                f"- Git commit: `{manifest['git_commit']}`",
                f"- Dirty tree at preparation: {str(manifest['git_dirty']).lower()}",
                "- Lane: pending",
                f"- Host: {manifest['host']}",
                "- Display/locale: pending",
                "",
                "## Launch ledger",
                "",
                "<!-- launch-ledger:start -->",
                "| Mode | Input | Output | Config file | Window state | "
                "Application log | Process | Arguments |",
                "| -- | -- | -- | -- | -- | -- | -- | -- |",
                "<!-- launch-ledger:end -->",
                "",
                "## Findings",
                "",
                "None recorded.",
                "",
                "## Scenario ledger",
                "",
                "| ID | Status | Attempts | Checkpoints | Durable oracle "
                "| Finding IDs | Notes |",
                "| -- | -- | --: | -- | -- | -- | -- |",
                "",
                "## Positive observations",
                "",
                "None recorded.",
                "",
                "## Coverage gaps and next run",
                "",
                "Pending.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return report_path


def prepare_run(
    repo_root: Path, requested_run_dir: Path | None, profile: str, theme: str
) -> dict[str, object]:
    repo_root = repo_root.expanduser().resolve()
    if not (repo_root / "pyproject.toml").is_file():
        raise ValueError(f"not a labelme repository root: {repo_root}")

    run_dir = create_run_directory(requested_path=requested_run_dir)
    for relative_path in (
        "evidence/screenshots",
        "evidence/accessibility",
        "evidence/logs",
        "outputs",
        "window-state",
    ):
        (run_dir / relative_path).mkdir(parents=True, exist_ok=True)

    dataset_paths = copy_inputs(repo_root=repo_root, run_dir=run_dir)
    config_path = write_config(run_dir=run_dir, theme=theme)
    git_commit, git_dirty = get_git_state(repo_root=repo_root)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "repo_root": str(repo_root),
        "run_dir": str(run_dir),
        "profile": profile,
        "theme": theme,
        "app_version": __version__,
        "host": platform.platform(),
        "architecture": platform.machine(),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "config_path": str(config_path),
        "window_state_path": str(run_dir / "window-state/window-state.ini"),
        "outputs_path": str(run_dir / "outputs"),
        "evidence_path": str(run_dir / "evidence"),
        "application_log_path": str(run_dir / "evidence/logs/application.log"),
        "datasets": dataset_paths,
        "expected_shape_counts": {"annotated": 8},
        "launches": [],
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_report(run_dir=run_dir, manifest=manifest)
    return manifest


def main() -> None:
    args = parse_args()
    try:
        manifest = prepare_run(
            repo_root=args.repo_root,
            requested_run_dir=args.run_dir,
            profile=args.profile,
            theme=args.theme,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
