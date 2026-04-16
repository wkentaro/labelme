import re
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

    pylupdate_version: str = (
        subprocess.check_output(["pylupdate5", "-version"], stderr=subprocess.STDOUT)
        .decode()
        .split()[-1]
        .lstrip("v")
    )
    logger.info("using pylupdate5 version: {}", pylupdate_version)
    if pylupdate_version.split(".")[:2] != ["5", "15"]:
        logger.warning("pylupdate5 version is not 5.15.x, skipping .ts generation")
        return

    lrelease_version: str = (
        subprocess.check_output(["lrelease", "-version"]).decode().split()[-1]
    )
    logger.info("using lrelease version: {}", lrelease_version)
    if lrelease_version.split(".")[:2] != ["5", "15"]:
        logger.warning("lrelease version is not 5.15.x, skipping .qm generation")
        return

    ts_paths: list[Path] = sorted(labelme_translate_path.glob("*.ts"))

    # Batch all languages into a single pylupdate5 call (~10x faster)
    subprocess.check_call(
        [
            "pylupdate5",
            "-noobsolete",
            *labelme_files,
            "-ts",
            *ts_paths,
        ]
    )

    for ts_path in ts_paths:
        # Zero out line numbers to reduce unnecessary diffs in .ts file
        ts_content: str = ts_path.read_text()
        new_ts_content: str = re.sub(r'line="\d+"', 'line="0"', ts_content)
        assert ts_content.strip() != new_ts_content.strip()
        ts_path.write_text(new_ts_content)

        qm_path: Path = ts_path.with_suffix(".qm")
        subprocess.check_call(
            ["lrelease", ts_path, "-qm", qm_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert qm_path.exists()

    logger.info("updated {} languages", len(ts_paths))


if __name__ == "__main__":
    main()
