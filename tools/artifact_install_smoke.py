from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import onnxruntime  # noqa: F401  # load DLLs before PySide6 on Windows
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

import labelme
from labelme import __appname__
from labelme import __version__
from labelme import _locale
from labelme._app import MainWindow


def _check_source_isolation(*, source_root: Path, package_path: Path) -> None:
    source_entries = [
        entry for entry in sys.path if Path(entry).resolve().is_relative_to(source_root)
    ]
    if source_entries:
        raise RuntimeError(f"source checkout is on sys.path: {source_entries}")

    if package_path.is_relative_to(source_root):
        raise RuntimeError(f"labelme imported from source checkout: {package_path}")


def _check_packaged_resources(*, package_path: Path) -> None:
    # Packaging mistakes drop whole directories, so one file per resource kind
    # is enough to prove the artifact carried the config and icons.
    package_dir = package_path.parent
    missing_resources = [
        relative_path
        for relative_path in (
            "_config/default_config.yaml",
            "icons/icon-256.png",
        )
        if not (package_dir / relative_path).is_file()
    ]
    if missing_resources:
        raise RuntimeError(f"packaged resources are missing: {missing_resources}")

    # A translation .qm can exist yet fail to load (wrong Qt version, a
    # truncated file); QTranslator.load() fails silently, so assert it here
    # rather than only stat'ing the file. Ask the package itself which
    # catalogs it ships, rather than hardcoding one, so renaming or retiring
    # a language doesn't fail this check for an unrelated reason.
    translate_dir = package_dir / "translate"
    available_locales = sorted(
        path.stem
        for path in translate_dir.glob("*.qm")
        if path.stem != _locale.SOURCE_LOCALE
    )
    if not available_locales:
        raise RuntimeError("packaged artifact ships no translation catalogs")
    if not QtCore.QTranslator().load(available_locales[0], str(translate_dir)):
        raise RuntimeError(
            f"packaged {available_locales[0]} translation failed to load"
        )


def _run_cli(executable: str, *args: str) -> str:
    # -I only isolates this process, not a subprocess: PYTHONPATH/PYTHONHOME
    # would otherwise ride along and could shadow the artifact under test with
    # the source checkout, the same failure mode this script guards against
    # for its own in-process import.
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("PYTHONPATH", "PYTHONHOME")
    }
    # check=True's CalledProcessError drops stdout/stderr from its message, so
    # the actual failure text this smoke test exists to surface never reaches
    # the CI log without reproducing locally. Surface it explicitly instead.
    result = subprocess.run(
        [executable, *args], capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{executable} {' '.join(args)} exited {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result.stdout


def _check_cli() -> None:
    executable = shutil.which("labelme")
    if executable is None:
        raise RuntimeError("labelme console script is not installed")

    help_output = _run_cli(executable, "--help")
    if "usage: labelme" not in help_output:
        raise RuntimeError("labelme --help did not print its usage")

    version_output = _run_cli(executable, "--version").strip()
    expected_version = f"{__appname__} {__version__}"
    if version_output != expected_version:
        raise RuntimeError(
            f"labelme --version printed {version_output!r}, "
            f"expected {expected_version!r}"
        )


def _check_application_starts() -> None:
    app = QtWidgets.QApplication([])
    try:
        # Constructing the window loads the default config, icons, and dock layout
        # from the installed package, which is the startup coverage this smoke
        # test is after.
        window = MainWindow(
            config_file=None,
            config_overrides={},
            file_or_dir=None,
            output_dir=None,
        )
        window.show()
        app.processEvents()
        if window.windowTitle() != __appname__:
            raise RuntimeError(
                f"the application window title is {window.windowTitle()!r}, "
                f"expected {__appname__!r}"
            )
        if not window.findChildren(QtGui.QAction):
            raise RuntimeError("the application window has no wired-up actions")
        window.close()
    finally:
        app.quit()


def main() -> None:
    source_root = Path(__file__).resolve().parent.parent
    package_path = Path(labelme.__file__).resolve()

    _check_source_isolation(source_root=source_root, package_path=package_path)
    _check_packaged_resources(package_path=package_path)

    # A QSettings ini handle can still be open when this block exits, which
    # trips a bare TemporaryDirectory's cleanup on Windows.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as home_dir:
        # Keep the run from writing into the invoking user's real home
        # directory: QSettings falls back to it unless explicitly redirected
        # (belt-and-suspenders with the setPath() call below).
        os.environ["HOME"] = home_dir
        os.environ["USERPROFILE"] = home_dir
        os.environ["LOCALAPPDATA"] = home_dir
        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
        QtCore.QSettings.setPath(
            QtCore.QSettings.Format.IniFormat,
            QtCore.QSettings.Scope.UserScope,
            home_dir,
        )
        _check_cli()
        _check_application_starts()


if __name__ == "__main__":
    main()
