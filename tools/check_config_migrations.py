from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from loguru import logger

from labelme._config import load_config


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    tags = subprocess.check_output(
        ["git", "tag", "--list", "v*", "--sort=version:refname"], cwd=repo, text=True
    ).splitlines()
    if not tags:
        raise RuntimeError("No release tags found; fetch the release tags first")
    logger.disable("labelme._config")
    failures: list[str] = []
    checked = 0
    without_yaml = 0
    with tempfile.TemporaryDirectory() as tmp:
        config_file = Path(tmp) / "labelmerc"
        for tag in tags:
            files = subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", tag], cwd=repo, text=True
            ).splitlines()
            configs = [path for path in files if path.endswith("/default_config.yaml")]
            if not configs:
                without_yaml += 1
                continue
            for path in configs:
                config_file.write_bytes(
                    subprocess.check_output(["git", "show", f"{tag}:{path}"], cwd=repo)
                )
                checked += 1
                try:
                    load_config(config_file=config_file, config_overrides={})
                except Exception as error:
                    failures.append(f"{tag}: {error}")
    print(
        f"Checked {checked} released YAML configs; "
        f"{without_yaml} tags predate YAML config."
    )
    if failures:
        raise SystemExit("\n".join(failures))
    print("All released configs load successfully.")


if __name__ == "__main__":
    main()
