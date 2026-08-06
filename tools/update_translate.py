import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from loguru import logger

here: Path = Path(__file__).parent


def _setup_logging() -> None:
    logger.remove(0)
    logger.level("INFO", color="<dim><white>")
    logger.add(
        sys.stderr,
        level="INFO",
        colorize=True,
        format="<level>{message}</level>",
        backtrace=False,
        diagnose=False,
    )


def _log_tool_version(tool: str) -> None:
    version: str = (
        subprocess.check_output([tool, "-version"], stderr=subprocess.STDOUT)
        .decode()
        .split()[-1]
    )
    logger.info("using {} version: {}", tool, version)


def _build_catalogs(
    source_files: list[Path], ts_paths: list[Path], out_dir: Path, quiet: bool
) -> None:
    targets: list[Path] = []
    for ts_path in ts_paths:
        target: Path = out_dir / ts_path.name
        if target != ts_path:
            shutil.copyfile(ts_path, target)
        targets.append(target)

    # Batch all languages into a single pyside6-lupdate call (~10x faster).
    # -locations none keeps diffs stable across code edits by omitting source
    # file/line references that would otherwise churn on every change.
    subprocess.check_call(
        [
            "pyside6-lupdate",
            "-no-obsolete",
            "-locations",
            "none",
            *source_files,
            "-ts",
            *targets,
        ],
        stdout=subprocess.DEVNULL if quiet else None,
    )

    for target in targets:
        qm_path: Path = target.with_suffix(".qm")
        subprocess.check_call(
            ["pyside6-lrelease", target, "-qm", qm_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not qm_path.exists():
            raise RuntimeError(f"pyside6-lrelease did not produce {qm_path}")


def _find_problems(ts_paths: list[Path], rebuilt_dir: Path) -> list[str]:
    problems: list[str] = []
    for ts_path in ts_paths:
        rebuilt_ts: Path = rebuilt_dir / ts_path.name
        if 'type="unfinished"' in rebuilt_ts.read_text(encoding="utf-8"):
            problems.append(f"{ts_path.name} has unfinished translations")
        for committed in (ts_path, ts_path.with_suffix(".qm")):
            if not committed.exists():
                problems.append(f"{committed.name} is missing")
                continue
            rebuilt: Path = rebuilt_dir / committed.name
            if committed.read_bytes() != rebuilt.read_bytes():
                problems.append(f"{committed.name} is out of date")
    return problems


def main() -> None:
    _setup_logging()

    parser = argparse.ArgumentParser(
        description="Regenerate or verify the Qt translation catalogs."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed catalogs are stale or carry unfinished "
        "translations, without writing to them",
    )
    check: bool = parser.parse_args().check

    _log_tool_version("pyside6-lupdate")
    _log_tool_version("pyside6-lrelease")

    labelme_path: Path = here / ".." / "labelme"
    source_files: list[Path] = sorted(labelme_path.rglob("*.py"))
    translate_path: Path = labelme_path / "translate"
    ts_paths: list[Path] = sorted(translate_path.glob("*.ts"))

    if not check:
        _build_catalogs(
            source_files=source_files,
            ts_paths=ts_paths,
            out_dir=translate_path,
            quiet=False,
        )
        logger.info("updated {} languages", len(ts_paths))
        return

    with tempfile.TemporaryDirectory() as tmp_dir:
        rebuilt_dir = Path(tmp_dir)
        _build_catalogs(
            source_files=source_files,
            ts_paths=ts_paths,
            out_dir=rebuilt_dir,
            quiet=True,
        )
        problems: list[str] = _find_problems(ts_paths=ts_paths, rebuilt_dir=rebuilt_dir)

    if problems:
        for problem in problems:
            logger.error(problem)
        logger.error(
            "run `make update_translate`, translate any new strings, "
            "and commit the result"
        )
        sys.exit(1)

    logger.info("checked {} languages", len(ts_paths))


if __name__ == "__main__":
    main()
