from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

import onnxruntime  # noqa: F401  # load DLLs before PySide6 on Windows
from PySide6 import QtCore
from PySide6 import QtWidgets

import labelme
from labelme import __appname__
from labelme import __version__
from labelme import _config
from labelme import _locale
from labelme._app import MainWindow
from labelme._utils import apply_color_theme
from labelme._utils import new_icon


def _check_source_isolation(*, source_root: Path) -> None:
    source_root = source_root.resolve()
    source_entries = [
        entry for entry in sys.path if Path(entry).resolve().is_relative_to(source_root)
    ]
    if source_entries:
        raise RuntimeError(f"source checkout is on sys.path: {source_entries}")

    package_path = Path(labelme.__file__).resolve()
    if package_path.is_relative_to(source_root):
        raise RuntimeError(f"labelme imported from source checkout: {package_path}")


def _run_cli(*, command: list[str], working_dir: Path) -> str:
    env = os.environ.copy()
    env["HOME"] = str(working_dir)
    env["USERPROFILE"] = str(working_dir)
    result = subprocess.run(
        command,
        cwd=working_dir,
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode:
        raise RuntimeError(
            f"command failed with exit code {result.returncode}: {command}"
        )
    return result.stdout


def _check_cli(*, working_dir: Path) -> None:
    executable = shutil.which("labelme")
    if executable is None:
        raise RuntimeError("labelme console script is not installed")

    help_output = _run_cli(command=[executable, "--help"], working_dir=working_dir)
    if "usage: labelme" not in help_output:
        raise RuntimeError("labelme --help did not print its usage")

    version_output = _run_cli(
        command=[executable, "--version"], working_dir=working_dir
    )
    expected_version = f"{__appname__} {__version__}"
    if version_output.strip() != expected_version:
        raise RuntimeError(
            f"labelme --version printed {version_output.strip()!r}, "
            f"expected {expected_version!r}"
        )


def _check_packaged_resources(*, source_root: Path) -> None:
    source_package_dir = source_root.resolve() / "labelme"
    package_dir = Path(labelme.__file__).resolve().parent
    REQUIRED_RESOURCES: Final = (
        Path("_config/default_config.yaml"),
        Path("icons/icon-256.png"),
        Path("translate/ja_JP.qm"),
        *(
            path.relative_to(source_package_dir)
            for path in (source_package_dir / "icons").rglob("*")
            if path.is_file()
        ),
        *(
            path.relative_to(source_package_dir)
            for path in (source_package_dir / "translate").glob("*.qm")
        ),
    )
    missing_resources = [
        relative_path
        for relative_path in REQUIRED_RESOURCES
        if not (package_dir / relative_path).is_file()
    ]
    if missing_resources:
        raise RuntimeError(f"packaged resources are missing: {missing_resources}")


def _start_application(*, working_dir: Path) -> None:
    config = _config.load_config(config_file=None, config_overrides={})

    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
    QtCore.QSettings.setPath(
        QtCore.QSettings.Format.IniFormat,
        QtCore.QSettings.Scope.UserScope,
        str(working_dir / "qt-settings"),
    )
    app = QtWidgets.QApplication([])
    app.setStyle("Fusion")
    apply_color_theme(theme=config.get("color_theme", "system"))
    app.setApplicationName(__appname__)

    package_dir = Path(labelme.__file__).resolve().parent
    icon_dir = package_dir / "icons"
    application_icon = new_icon("icon-256.png")
    if application_icon.isNull():
        raise RuntimeError("the application icon could not be loaded")
    for icon_path in icon_dir.rglob("*"):
        if icon_path.suffix not in {".ico", ".png", ".svg"}:
            continue
        icon = new_icon(str(icon_path.relative_to(icon_dir)))
        if icon.isNull():
            raise RuntimeError(f"application icon could not be loaded: {icon_path}")
    app.setWindowIcon(application_icon)

    for translation_path in _locale.TRANSLATE_DIR.glob("*.qm"):
        translation = QtCore.QTranslator()
        if not translation.load(str(translation_path)):
            raise RuntimeError(f"translation could not be loaded: {translation_path}")

    japanese_translator = QtCore.QTranslator()
    if not japanese_translator.load("ja_JP", str(_locale.TRANSLATE_DIR)):
        raise RuntimeError("the bundled Japanese translation could not be loaded")
    app.installTranslator(japanese_translator)
    source_text = "Brightness:"
    translated_text = QtCore.QCoreApplication.translate(
        "BrightnessContrastDialog", source_text
    )
    if translated_text == source_text:
        raise RuntimeError("the bundled Japanese translation was not applied")

    window = MainWindow(
        config_file=None,
        config_overrides={},
        file_or_dir=None,
        output_dir=None,
    )
    window.show()
    app.processEvents()
    if not window.isVisible():
        raise RuntimeError("the application window did not start")
    window.hide()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    args = parser.parse_args()

    _check_source_isolation(source_root=args.source_root)
    _check_packaged_resources(source_root=args.source_root)
    with tempfile.TemporaryDirectory() as working_dir:
        working_path = Path(working_dir)
        _check_cli(working_dir=working_path)
        _start_application(working_dir=working_path)


if __name__ == "__main__":
    main()
