from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import cast

from PySide6.QtCore import QSettings

from labelme import __main__ as labelme_main


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "dataset",
        choices=("raw", "annotated", "sequence", "corrupt", "missing-image"),
    )
    parser.add_argument(
        "--logger-level",
        choices=("debug", "info", "warning", "error", "critical"),
        default="warning",
    )
    return parser.parse_args()


def load_manifest(run_dir: Path) -> dict[str, object]:
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError(f"unsupported manifest: {manifest_path}")
    return manifest


def get_manifest_path(manifest: dict[str, object], key: str) -> Path:
    value = manifest.get(key)
    if not isinstance(value, str):
        raise ValueError(f"manifest field is not a path: {key}")
    return Path(value)


def get_dataset_path(manifest: dict[str, object], dataset: str) -> Path:
    datasets = manifest.get("datasets")
    if not isinstance(datasets, dict):
        raise ValueError("manifest datasets are missing")
    typed_datasets = cast(dict[str, object], datasets)
    value = typed_datasets.get(dataset)
    if not isinstance(value, str):
        raise ValueError(f"manifest dataset is missing: {dataset}")
    return Path(value)


def launch_labelme(run_dir: Path, dataset: str, logger_level: str) -> None:
    run_dir = run_dir.expanduser().resolve()
    manifest = load_manifest(run_dir=run_dir)
    settings_path = get_manifest_path(manifest=manifest, key="settings_path")
    config_path = get_manifest_path(manifest=manifest, key="config_path")
    outputs_path = get_manifest_path(manifest=manifest, key="outputs_path")
    dataset_path = get_dataset_path(manifest=manifest, dataset=dataset)

    output_path = outputs_path / dataset
    output_path.mkdir(parents=True, exist_ok=True)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(settings_path),
    )

    app_argv = [
        "labelme",
        str(dataset_path),
        "--config",
        str(config_path),
        "--output",
        str(output_path),
        "--logger-level",
        logger_level,
    ]
    print(
        json.dumps(
            {
                "pid": os.getpid(),
                "python_executable": sys.executable,
                "dataset": dataset,
                "app_argv": app_argv,
                "settings_path": str(settings_path),
            },
            sort_keys=True,
        ),
        flush=True,
    )

    def resolve_isolated_config_file(create_if_missing: bool = True) -> str:
        del create_if_missing
        return str(config_path)

    original_resolver = labelme_main._config.get_user_config_file
    setattr(
        labelme_main._config,
        "get_user_config_file",
        resolve_isolated_config_file,
    )
    sys.argv[:] = app_argv
    try:
        labelme_main.main()
    finally:
        setattr(labelme_main._config, "get_user_config_file", original_resolver)


def main() -> None:
    args = parse_args()
    launch_labelme(
        run_dir=args.run_dir,
        dataset=args.dataset,
        logger_level=args.logger_level,
    )


if __name__ == "__main__":
    main()
