from __future__ import annotations

import os
import tempfile
from pathlib import Path

import onnxruntime  # noqa: F401  # load DLLs before PySide6 on Windows
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

import labelme
from labelme import __appname__
from labelme import _locale
from labelme.__main__ import _set_application_icon
from labelme._app import MainWindow


def _check_source_isolation(*, source_root: Path, package_path: Path) -> None:
    # Where labelme was imported from is the evidence. python -I and
    # `uv run --isolated --no-project` already keep the checkout off sys.path,
    # so scanning sys.path only restates the invocation.
    if package_path.is_relative_to(source_root):
        raise RuntimeError(f"labelme imported from source checkout: {package_path}")


def _check_packaged_resources() -> None:
    # Loading the image catches truncated resources that a file existence check
    # would accept. QImage works before there is a QApplication.
    icon_path = Path(labelme.__file__).parent / "icons" / "phosphor" / "info.svg"
    if QtGui.QImage(str(icon_path)).isNull():
        raise RuntimeError(f"packaged icon failed to load: {icon_path}")

    locales = _locale.available_translation_locales()
    if not locales:
        raise RuntimeError("packaged artifact ships no translation catalogs")
    for locale in locales:
        if not QtCore.QTranslator().load(locale, str(_locale.TRANSLATE_DIR)):
            raise RuntimeError(f"packaged {locale} translation failed to load")


def _check_application_starts() -> None:
    app = QtWidgets.QApplication([])
    _set_application_icon(app)
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
        if window.windowIcon().isNull():
            raise RuntimeError("the application window has no icon")
        if not window.findChildren(QtGui.QAction):
            raise RuntimeError("the application window has no wired-up actions")
        window.close()
    finally:
        app.quit()


def main() -> None:
    source_root = Path(__file__).resolve().parent.parent
    package_path = Path(labelme.__file__).resolve()

    _check_source_isolation(source_root=source_root, package_path=package_path)
    _check_packaged_resources()

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
        _check_application_starts()


if __name__ == "__main__":
    main()
