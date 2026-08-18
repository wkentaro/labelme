from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path
from typing import Final
from typing import cast

from loguru import logger
from PySide6.QtCore import QSettings

from labelme import __main__ as labelme_main
from labelme import _app as labelme_app

LAUNCH_MODES: Final = (
    "none",
    "raw",
    "annotated",
    "sequence",
    "corrupt",
    "missing-image",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "mode",
        choices=LAUNCH_MODES,
        help="prepared startup precondition",
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


def get_mode_input_path(
    *, manifest: dict[str, object], mode: str, run_dir: Path
) -> Path | None:
    if mode not in LAUNCH_MODES:
        choices = ", ".join(LAUNCH_MODES)
        raise ValueError(f"unknown launch mode {mode!r}; choose one of: {choices}")
    if mode == "none":
        return None

    datasets = manifest.get("datasets")
    if not isinstance(datasets, dict):
        raise ValueError("manifest datasets are missing")
    typed_datasets = cast(dict[str, object], datasets)
    value = typed_datasets.get(mode)
    if not isinstance(value, str):
        raise ValueError(f"manifest dataset is missing for {mode} mode")
    input_path = Path(value).expanduser().resolve()
    if not input_path.is_relative_to(run_dir):
        raise ValueError(f"{mode} mode input must stay inside the run directory")
    EXPECTED_RELATIVE_PATHS: Final = {
        "raw": "inputs/raw",
        "annotated": "outputs/annotated/primitives.json",
        "sequence": "inputs/sequence",
        "corrupt": "inputs/corrupt/primitives.json",
        "missing-image": "inputs/missing-image/primitives.json",
    }
    expected_path = (run_dir / EXPECTED_RELATIVE_PATHS[mode]).resolve()
    if input_path != expected_path:
        raise ValueError(
            f"{mode} mode requires prepared input {expected_path}, got {input_path}"
        )
    if mode in {"raw", "sequence"} and not input_path.is_dir():
        raise ValueError(f"{mode} mode requires an input directory: {input_path}")
    if mode == "annotated" and (
        input_path.suffix.lower() != ".json" or not input_path.is_file()
    ):
        raise ValueError(
            f"annotated mode requires an Annotation File ending in .json: {input_path}"
        )
    if mode in {"corrupt", "missing-image"} and not input_path.is_file():
        raise ValueError(f"{mode} mode requires an Annotation File: {input_path}")

    if mode == "annotated":
        try:
            annotation = json.loads(input_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"annotated mode requires a valid Annotation File: {input_path}"
            ) from error
        if not isinstance(annotation, dict):
            raise ValueError(f"annotated mode requires a JSON object: {input_path}")
        shapes = annotation.get("shapes")
        image_path_value = annotation.get("imagePath")
        expected_shape_counts = manifest.get("expected_shape_counts")
        expected_shape_count: object | None = None
        if isinstance(expected_shape_counts, dict):
            expected_shape_count = cast(dict[str, object], expected_shape_counts).get(
                mode
            )
        if not isinstance(shapes, list) or len(shapes) != expected_shape_count:
            raise ValueError(
                f"annotated mode expected {expected_shape_count} Shapes: {input_path}"
            )
        if not isinstance(image_path_value, str):
            raise ValueError(
                f"annotated mode Annotation File has no image path: {input_path}"
            )
        image_path = (input_path.parent / image_path_value).resolve()
        if not image_path.is_relative_to(run_dir) or not image_path.is_file():
            raise ValueError(
                f"annotated mode image must exist inside the run: {image_path}"
            )

    if mode == "corrupt":
        try:
            json.loads(input_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
        else:
            raise ValueError(
                f"corrupt mode requires intentionally invalid JSON: {input_path}"
            )

    if mode == "missing-image":
        try:
            annotation = json.loads(input_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"missing-image mode requires a valid Annotation File: {input_path}"
            ) from error
        if not isinstance(annotation, dict):
            raise ValueError(f"missing-image mode requires a JSON object: {input_path}")
        image_path_value = annotation.get("imagePath")
        if not isinstance(image_path_value, str):
            raise ValueError(
                f"missing-image mode Annotation File has no image path: {input_path}"
            )
        image_path = (input_path.parent / image_path_value).resolve()
        if not image_path.is_relative_to(run_dir):
            raise ValueError(
                f"missing-image mode image path must stay inside the run: {image_path}"
            )
        if image_path.exists():
            raise ValueError(
                f"missing-image mode requires an absent image: {image_path}"
            )
    return input_path


def _format_report_code_cell(value: str | list[str]) -> str:
    escaped_value = html.escape(json.dumps(value), quote=False)
    escaped_value = escaped_value.replace("|", "&#124;").replace("`", "&#96;")
    return f"<code>{escaped_value}</code>"


def _write_text_atomically(path: Path, text: str) -> None:
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temp_path.write_text(text, encoding="utf-8")
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def _format_report_launch_row(launch: object) -> str:
    if not isinstance(launch, dict):
        raise ValueError("manifest launch record is invalid")
    typed_launch = cast(dict[str, object], launch)
    input_path = typed_launch.get("input_path")
    input_value = (
        _format_report_code_cell(str(input_path)) if input_path is not None else "none"
    )
    app_argv = typed_launch.get("app_argv")
    if not isinstance(app_argv, list) or not all(
        isinstance(argument, str) for argument in app_argv
    ):
        raise ValueError("manifest launch arguments are invalid")
    typed_app_argv = cast(list[str], app_argv)
    process = (
        f"PID {typed_launch.get('pid')} via {typed_launch.get('python_executable')}"
    )
    return (
        f"| {_format_report_code_cell(str(typed_launch.get('mode')))} | {input_value} "
        f"| {_format_report_code_cell(str(typed_launch.get('output_path')))} "
        f"| {_format_report_code_cell(str(typed_launch.get('config_path')))} "
        f"| {_format_report_code_cell(str(typed_launch.get('window_state_path')))} "
        f"| {_format_report_code_cell(str(typed_launch.get('application_log_path')))} "
        f"| {_format_report_code_cell(process)} "
        f"| {_format_report_code_cell(typed_app_argv)} |"
    )


def _derive_report_launch_ledger(*, report_path: Path, launches: list[object]) -> None:
    START_MARKER: Final = "<!-- launch-ledger:start -->"
    END_MARKER: Final = "<!-- launch-ledger:end -->"
    LEDGER_HEADER: Final = (
        "| Mode | Input | Output | Config file | Window state | "
        "Application log | Process | Arguments |\n"
        "| -- | -- | -- | -- | -- | -- | -- | -- |"
    )
    report = report_path.read_text(encoding="utf-8")
    before, start_marker, remainder = report.partition(START_MARKER)
    _, end_marker, after = remainder.partition(END_MARKER)
    if not start_marker or not end_marker:
        raise ValueError("report launch ledger markers are missing")
    rows = "\n".join(_format_report_launch_row(launch) for launch in launches)
    ledger = f"{START_MARKER}\n{LEDGER_HEADER}"
    if rows:
        ledger = f"{ledger}\n{rows}"
    updated_report = f"{before}{ledger}\n{END_MARKER}{after}"
    _write_text_atomically(path=report_path, text=updated_report)


def _write_launch_record(
    *,
    run_dir: Path,
    manifest: dict[str, object],
    mode: str,
    input_path: Path | None,
    output_path: Path,
    window_state_path: Path,
    config_path: Path,
    application_log_path: Path,
    app_argv: list[str],
) -> dict[str, object]:
    expected_shape_counts = manifest.get("expected_shape_counts")
    expected_shape_count: object | None = None
    if isinstance(expected_shape_counts, dict):
        expected_shape_count = cast(dict[str, object], expected_shape_counts).get(mode)
    launch: dict[str, object] = {
        "mode": mode,
        "input_path": str(input_path) if input_path is not None else None,
        "output_path": str(output_path),
        "window_state_path": str(window_state_path),
        "config_path": str(config_path),
        "application_log_path": str(application_log_path),
        "pid": os.getpid(),
        "python_executable": sys.executable,
        "app_argv": app_argv,
        "expected_shape_count": expected_shape_count,
    }
    launches = manifest.get("launches")
    if not isinstance(launches, list):
        raise ValueError("manifest launches are missing")
    typed_launches = cast(list[object], launches)

    typed_launches.append(launch)
    try:
        _write_text_atomically(
            path=run_dir / "manifest.json",
            text=json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
    except Exception:
        typed_launches.pop()
        raise
    try:
        _derive_report_launch_ledger(
            report_path=run_dir / "report.md", launches=typed_launches
        )
    except (OSError, ValueError) as error:
        logger.warning(
            "Could not derive report launch ledger from the canonical manifest: {}",
            error,
        )
    return launch


def launch_labelme(run_dir: Path, mode: str, logger_level: str) -> None:
    run_dir = run_dir.expanduser().resolve()
    manifest = load_manifest(run_dir=run_dir)
    window_state_path = get_manifest_path(manifest=manifest, key="window_state_path")
    config_path = get_manifest_path(manifest=manifest, key="config_path")
    outputs_path = get_manifest_path(manifest=manifest, key="outputs_path")
    application_log_path = get_manifest_path(
        manifest=manifest, key="application_log_path"
    )
    input_path = get_mode_input_path(manifest=manifest, mode=mode, run_dir=run_dir)
    if (
        not window_state_path.resolve().is_relative_to(run_dir)
        or not window_state_path.parent.is_dir()
    ):
        raise ValueError(
            f"Window State path must use an existing run directory: {window_state_path}"
        )
    if not config_path.resolve().is_relative_to(run_dir) or not config_path.is_file():
        raise ValueError(f"config path must be an existing run file: {config_path}")
    if not outputs_path.resolve().is_relative_to(run_dir) or not outputs_path.is_dir():
        raise ValueError(
            f"outputs path must be an existing run directory: {outputs_path}"
        )
    if (
        not application_log_path.resolve().is_relative_to(run_dir / "evidence/logs")
        or not application_log_path.parent.is_dir()
    ):
        raise ValueError(
            "application log path must use the run evidence directory: "
            f"{application_log_path}"
        )

    output_path = outputs_path / mode
    if not output_path.resolve().is_relative_to(outputs_path.resolve()):
        raise ValueError(f"output path must stay inside the run: {output_path}")
    output_path.mkdir(parents=True, exist_ok=True)
    window_settings = QSettings(str(window_state_path), QSettings.Format.IniFormat)

    app_argv = ["labelme"]
    if input_path is not None:
        app_argv.append(str(input_path))
    app_argv.extend(
        [
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--logger-level",
            logger_level,
        ]
    )
    launch = _write_launch_record(
        run_dir=run_dir,
        manifest=manifest,
        mode=mode,
        input_path=input_path,
        output_path=output_path,
        window_state_path=window_state_path,
        config_path=config_path,
        application_log_path=application_log_path,
        app_argv=app_argv,
    )
    print(
        json.dumps(launch, sort_keys=True),
        flush=True,
    )

    # Argument parsing resolves the default before honoring the explicit config,
    # so isolate that lookup to keep the developer's persistent profile untouched.
    def _resolve_isolated_config_file(create_if_missing: bool = True) -> str:
        del create_if_missing
        return str(config_path)

    def _configure_isolated_logging(logger_level: str) -> None:
        logger.remove()
        logger.add(sys.stderr, level=logger_level)
        logger.add(
            application_log_path,
            colorize=False,
            level="DEBUG",
            backtrace=True,
            diagnose=True,
        )

    # Native settings ignore custom storage paths on macOS, so provide the app
    # with one explicit INI store inside the run instead of changing defaults.
    def _resolve_isolated_window_settings(*args: object, **kwargs: object) -> QSettings:
        del args, kwargs
        return window_settings

    original_resolver = labelme_main._config.get_user_config_file
    original_log_setup = labelme_main._setup_loguru
    original_qsettings = labelme_app.QtCore.QSettings
    original_argv = sys.argv[:]
    setattr(
        labelme_main._config,
        "get_user_config_file",
        _resolve_isolated_config_file,
    )
    setattr(labelme_main, "_setup_loguru", _configure_isolated_logging)
    setattr(labelme_app.QtCore, "QSettings", _resolve_isolated_window_settings)
    sys.argv[:] = app_argv
    try:
        labelme_main.main()
    finally:
        window_settings.sync()
        sys.argv[:] = original_argv
        setattr(labelme_app.QtCore, "QSettings", original_qsettings)
        setattr(labelme_main, "_setup_loguru", original_log_setup)
        setattr(labelme_main._config, "get_user_config_file", original_resolver)


def main() -> None:
    args = parse_args()
    launch_labelme(
        run_dir=args.run_dir,
        mode=args.mode,
        logger_level=args.logger_level,
    )


if __name__ == "__main__":
    main()
