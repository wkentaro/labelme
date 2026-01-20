import re
import subprocess
import sys
from pathlib import Path

from loguru import logger

here: Path = Path(__file__).parent


def main():
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

    languages: list[str] = sorted(
        [ts_file.stem for ts_file in labelme_translate_path.glob("*.ts")]
    )
    for lang in languages:
        ts_path: Path = labelme_translate_path / f"{lang}.ts"
        subprocess.check_call(
            [
                "pylupdate5",
                *labelme_files,
                "-ts",
                str(ts_path),
            ]
        )
        assert ts_path.exists()

        # Zero out line numbers to reduce unnecessary diffs in .ts file
        ts_content: str = ts_path.read_text()
        new_ts_content: str = re.sub(r'line="\d+"', 'line="0"', ts_content)
        assert ts_content.strip() != new_ts_content.strip()
        ts_path.write_text(new_ts_content)
        logger.info("updated .ts file: {}", ts_path)

        qm_path: Path = labelme_translate_path / f"{lang}.qm"
        subprocess.check_call(
            ["lrelease", ts_path, "-qm", qm_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert qm_path.exists()
        logger.info("updated .qm file: {}", qm_path)


if __name__ == "__main__":
    main()
