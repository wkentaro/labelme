import subprocess
import sys
from pathlib import Path

from loguru import logger

here: Path = Path(__file__).parent


def main() -> None:
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

    labelme_path: Path = here / ".." / "labelme"
    labelme_files: list[Path] = list(labelme_path.rglob("*.py"))

    labelme_translate_path: Path = labelme_path / "translate"

    lupdate_version: str = (
        subprocess.check_output(
            ["pyside6-lupdate", "-version"], stderr=subprocess.STDOUT
        )
        .decode()
        .split()[-1]
    )
    logger.info("using pyside6-lupdate version: {}", lupdate_version)

    lrelease_version: str = (
        subprocess.check_output(["pyside6-lrelease", "-version"]).decode().split()[-1]
    )
    logger.info("using pyside6-lrelease version: {}", lrelease_version)

    ts_paths: list[Path] = sorted(labelme_translate_path.glob("*.ts"))

    # Batch all languages into a single pyside6-lupdate call (~10x faster).
    # -locations none keeps diffs stable across code edits by omitting source
    # file/line references that would otherwise churn on every change.
    subprocess.check_call(
        [
            "pyside6-lupdate",
            "-no-obsolete",
            "-locations",
            "none",
            *labelme_files,
            "-ts",
            *ts_paths,
        ]
    )

    for ts_path in ts_paths:
        qm_path: Path = ts_path.with_suffix(".qm")
        subprocess.check_call(
            ["pyside6-lrelease", ts_path, "-qm", qm_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not qm_path.exists():
            raise RuntimeError(f"pyside6-lrelease did not produce {qm_path}")

    logger.info("updated {} languages", len(ts_paths))


if __name__ == "__main__":
    main()
