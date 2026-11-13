from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Final

import numpy as np
import onnxruntime  # noqa: F401  # load DLLs before PySide6 on Windows
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

import labelme
from labelme import __appname__
from labelme import _locale
from labelme._app import MainWindow
from labelme._automation import InferenceRequest
from labelme._automation import OsamWorker
from labelme._model_manager import ModelManager

_MODEL_NAME: Final = "efficientsam:10m"
_TIMEOUT_S: Final = 600


def _check_source_isolation(*, source_root: Path, package_path: Path) -> None:
    # Where labelme was imported from is the evidence. python -I and
    # `uv run --isolated --no-project` already keep the checkout off sys.path,
    # so scanning sys.path only restates the invocation.
    if package_path.is_relative_to(source_root):
        raise RuntimeError(f"labelme imported from source checkout: {package_path}")


def _check_packaged_resources() -> None:
    # Packaging mistakes drop whole directories, so one file per resource kind
    # proves the artifact carried it. Both are loaded rather than stat'ed: a
    # truncated icon or catalog exists yet fails to load, and Qt reports that
    # by returning null or False, never by raising. QImage rather than QPixmap
    # so this runs before there is a QApplication.
    icon_path = Path(labelme.__file__).parent / "icons" / "icon-256.png"
    if QtGui.QImage(str(icon_path)).isNull():
        raise RuntimeError(f"packaged icon failed to load: {icon_path}")

    locales = _locale.available_translation_locales()
    if not locales:
        raise RuntimeError("packaged artifact ships no translation catalogs")
    if not QtCore.QTranslator().load(locales[0], str(_locale.TRANSLATE_DIR)):
        raise RuntimeError(f"packaged {locales[0]} translation failed to load")


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


def _check_model_download(*, app: QtCore.QCoreApplication) -> None:
    manager = ModelManager()
    deadline = time.monotonic() + _TIMEOUT_S
    try:
        manager.enqueue(model_name=_MODEL_NAME)
        while manager.active is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.05)
        if manager.active is not None:
            raise RuntimeError(f"Model download timed out after {_TIMEOUT_S} s")
        error = manager.errors.get(_MODEL_NAME)
        if error is not None or not manager.is_ready(model_name=_MODEL_NAME):
            raise RuntimeError(f"Model download failed: {error or 'weights missing'}")
    finally:
        manager.shutdown()


def _check_ai_inference() -> None:
    # One real inference on osam's private server: the server must start from
    # the installed environment, and onnxruntime must load on the device osam
    # picks. The smallest model (~40MB) keeps the download short.
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _check_model_download(app=app)
    worker = OsamWorker()
    results: list[tuple[str, object]] = []
    worker.finished.connect(
        lambda _, annotations: results.append(("done", annotations))
    )
    worker.failed.connect(lambda _, message: results.append(("failed", message)))
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[16:48, 16:48] = 255
    worker.submit(
        channel="smoke",
        job="smoke",
        request=InferenceRequest(
            model_name=_MODEL_NAME,
            image=image,
            points=np.array([[32.0, 32.0]], dtype=np.float32),
            point_labels=np.array([1]),
        ),
    )
    deadline = time.monotonic() + _TIMEOUT_S
    try:
        while not results and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.05)
    finally:
        worker.shutdown()
    if not results:
        raise RuntimeError(f"AI inference gave no result in {_TIMEOUT_S} s")
    kind, payload = results[0]
    if kind != "done" or not payload:
        raise RuntimeError(f"AI inference {kind}: {payload!r}")


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
        if "--inference" in sys.argv[1:]:
            _check_ai_inference()


if __name__ == "__main__":
    main()
