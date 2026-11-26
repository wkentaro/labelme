from __future__ import annotations

import json
import os
import re
import secrets
import sys
import tempfile
import traceback
import types
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any
from typing import Final

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtNetwork
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

import labelme
from labelme import __main__ as labelme_entry
from labelme import _app as labelme_app
from labelme.__main__ import main as labelme_main
from labelme._app import MainWindow
from labelme._widgets._canvas import Canvas

MAX_ROWS: Final = 200
WINDOW_SIZE: Final = QtCore.QSize(1280, 800)
BUTTONS: Final = {
    "left": Qt.MouseButton.LeftButton,
    "right": Qt.MouseButton.RightButton,
    "middle": Qt.MouseButton.MiddleButton,
}

RUN_FILE: Final = "run.json"
EXIT_FILE: Final = "exit_code"
MAX_REQUEST_BYTES: Final = 1 << 20
BLOCKED: Final[list[str]] = []
UNCAUGHT: Final[list[str]] = []


class CtlError(Exception):
    pass


def _app() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    assert isinstance(app, QtWidgets.QApplication)
    return app


def _plain(*, value: object) -> str:
    return re.sub(r"<[^>]+>", "", str(value)).replace("&nbsp;", " ").strip()


def _visible(*, widget: QtWidgets.QWidget) -> bool:
    return widget.isVisible() and widget.width() > 0 and widget.height() > 0


def _find_main_window() -> MainWindow | None:
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(widget, MainWindow):
            return widget
    return None


def _main_window() -> MainWindow:
    win = _find_main_window()
    if win is None:
        raise CtlError("no labelme MainWindow")
    return win


def _image_loaded(*, win: MainWindow) -> bool:
    canvases = win.findChildren(Canvas)
    pixmap = canvases[0].pixmap if canvases else None
    return pixmap is not None and not pixmap.isNull()


def _top_dialog() -> QtWidgets.QWidget | None:
    app = _app()
    if modal := app.activeModalWidget():
        return modal
    active = app.activeWindow()
    if isinstance(active, QtWidgets.QDialog) and _visible(widget=active):
        return active
    dialogs = [
        w
        for w in app.topLevelWidgets()
        if isinstance(w, QtWidgets.QDialog) and _visible(widget=w)
    ]
    return dialogs[-1] if dialogs else None


def _row_text(*, view: QtWidgets.QAbstractItemView, index: QtCore.QModelIndex) -> str:
    text = index.data(Qt.ItemDataRole.DisplayRole)
    if text is not None:
        return str(text)
    widget = view.indexWidget(index)
    if widget is None:
        return ""
    labels = [widget] if isinstance(widget, QtWidgets.QLabel) else []
    labels += widget.findChildren(QtWidgets.QLabel)
    return " ".join(_plain(value=label.text()) for label in labels if label.text())


def _rows(*, view: QtWidgets.QAbstractItemView) -> list[dict[str, Any]]:
    model = view.model()
    if model is None:
        return []
    root = view.rootIndex()
    count = model.rowCount(root)
    selection = view.selectionModel()
    rows: list[dict[str, Any]] = []
    for row in range(min(count, MAX_ROWS)):
        index = model.index(row, 0, root)
        entry: dict[str, Any] = {"text": _row_text(view=view, index=index)}
        check = index.data(Qt.ItemDataRole.CheckStateRole)
        if check is not None:
            entry["checked"] = Qt.CheckState(check) == Qt.CheckState.Checked
        if selection is not None and selection.isSelected(index):
            entry["selected"] = True
        if isinstance(view, QtWidgets.QListView) and view.isRowHidden(row):
            entry["hidden"] = True
        rows.append(entry)
    if count > MAX_ROWS:
        rows.append({"truncated": count - MAX_ROWS})
    return rows


def _button_text(*, button: QtWidgets.QAbstractButton) -> str:
    text = " ".join(button.text().replace("&", "").split())
    return text or button.toolTip() or button.accessibleName()


def _button_info(*, button: QtWidgets.QAbstractButton) -> dict[str, Any]:
    entry: dict[str, Any] = {"text": _button_text(button=button)}
    if not button.isEnabled():
        entry["enabled"] = False
    if button.isCheckable():
        entry["checked"] = button.isChecked()
    return entry


def _field_info(*, widget: QtWidgets.QWidget) -> dict[str, Any] | None:
    if isinstance(widget, QtWidgets.QLineEdit):
        if isinstance(
            widget.parent(), QtWidgets.QAbstractSpinBox | QtWidgets.QComboBox
        ):
            return None
        name, text = widget.accessibleName() or widget.placeholderText(), widget.text()
    elif isinstance(widget, QtWidgets.QPlainTextEdit | QtWidgets.QTextEdit):
        name = widget.accessibleName() or widget.placeholderText()
        text = widget.toPlainText()
    elif isinstance(widget, QtWidgets.QAbstractSpinBox):
        name, text = widget.accessibleName(), widget.text()
    else:
        return None
    return {"name": name, "text": text, "focused": widget.hasFocus()}


def _menu_item(*, action: QtGui.QAction) -> dict[str, Any]:
    item: dict[str, Any] = {"text": action.text().replace("&", "")}
    if not action.isEnabled():
        item["enabled"] = False
    if action.isCheckable():
        item["checked"] = action.isChecked()
    return item


def _menu_actions(*, menu: QtWidgets.QMenu) -> list[QtGui.QAction]:
    return [a for a in menu.actions() if not a.isSeparator() and a.isVisible()]


def _describe(*, root: QtWidgets.QWidget) -> dict[str, Any]:
    info: dict[str, Any] = {"title": root.windowTitle(), "class": type(root).__name__}
    if isinstance(root, QtWidgets.QMenu):
        info["items"] = [_menu_item(action=a) for a in _menu_actions(menu=root)]
    if isinstance(root, QtWidgets.QMessageBox):
        info["text"] = _plain(value=root.text())
        if root.informativeText():
            info["informative_text"] = _plain(value=root.informativeText())
    found: dict[str, list[Any]] = {
        "labels": [],
        "fields": [],
        "combos": [],
        "buttons": [],
        "lists": [],
    }
    for w in root.findChildren(QtWidgets.QWidget):
        if not _visible(widget=w) or w.window() is not root:
            continue
        field = _field_info(widget=w)
        if field is not None:
            found["fields"].append(field)
        elif isinstance(w, QtWidgets.QLabel) and w.text().strip():
            found["labels"].append(_plain(value=w.text()))
        elif isinstance(w, QtWidgets.QComboBox):
            found["combos"].append(
                {"name": w.accessibleName(), "text": w.currentText()}
            )
        elif isinstance(w, QtWidgets.QAbstractButton):
            found["buttons"].append(_button_info(button=w))
        elif isinstance(w, QtWidgets.QAbstractItemView):
            found["lists"].append({"name": w.accessibleName(), "rows": _rows(view=w)})
    info.update({key: value for key, value in found.items() if value})
    return info


def _docks() -> list[QtWidgets.QDockWidget]:
    docks = _main_window().findChildren(QtWidgets.QDockWidget)
    return [d for d in docks if _visible(widget=d)]


def _dock_info(*, dock: QtWidgets.QDockWidget) -> dict[str, Any]:
    info: dict[str, Any] = {"title": dock.windowTitle()}
    widgets = [w for w in dock.findChildren(QtWidgets.QWidget) if _visible(widget=w)]
    lists = [
        {"name": w.accessibleName(), "rows": _rows(view=w)}
        for w in widgets
        if isinstance(w, QtWidgets.QAbstractItemView)
    ]
    fields = [
        {"name": w.accessibleName() or w.placeholderText(), "text": w.text()}
        for w in widgets
        if isinstance(w, QtWidgets.QLineEdit)
    ]
    if lists:
        info["lists"] = lists
    if fields:
        info["fields"] = fields
    return info


def _toolbar(*, win: MainWindow) -> list[dict[str, Any]]:
    return [
        _button_info(button=button)
        for bar in win.findChildren(QtWidgets.QToolBar)
        if _visible(widget=bar)
        for button in bar.findChildren(QtWidgets.QToolButton)
        if _visible(widget=button)
    ]


def _status_bar(*, win: MainWindow) -> list[str]:
    status = win.statusBar()
    texts = [status.currentMessage()] if status.currentMessage() else []
    texts += [
        _plain(value=w.text())
        for w in status.findChildren(QtWidgets.QLabel)
        if _visible(widget=w) and w.text().strip()
    ]
    return texts


def _focus_info() -> dict[str, Any] | None:
    focus = _app().focusWidget()
    if focus is None:
        return None
    return {
        "class": type(focus).__name__,
        "name": focus.accessibleName(),
        "window": focus.window().windowTitle(),
    }


def _held_buttons() -> list[Qt.MouseButton]:
    held = QtGui.QGuiApplication.mouseButtons()
    return [b for b in BUTTONS.values() if held & b]


def _dialog_info(*, dialog: QtWidgets.QWidget) -> dict[str, Any]:
    return {**_describe(root=dialog), "modal": dialog.isModal()}


def _state() -> dict[str, Any]:
    app = _app()
    win = _find_main_window()
    dialog = _top_dialog()
    popup = app.activePopupWidget()
    others = [
        {"title": w.windowTitle(), "class": type(w).__name__}
        for w in app.topLevelWidgets()
        if _visible(widget=w)
        and w not in (win, dialog, popup)
        and not isinstance(w, QtWidgets.QMenu)
    ]
    return {
        "main_window": {
            "title": win.windowTitle() if win else "",
            "visible": win is not None and win.isVisible(),
            "size": [win.width(), win.height()] if win else [0, 0],
        },
        "image_loaded": win is not None and _image_loaded(win=win),
        "mouse_buttons_held": [b.name for b in _held_buttons()],
        "blocked": list(BLOCKED),
        "dialog": _dialog_info(dialog=dialog) if dialog else None,
        "popup": _describe(root=popup) if popup else None,
        "focus": _focus_info(),
        "status_bar": _status_bar(win=win) if win else [],
        "toolbar": _toolbar(win=win) if win else [],
        "docks": [_dock_info(dock=d) for d in _docks()] if win else [],
        "other_windows": others,
    }


def _screenshot(*, req: dict[str, Any]) -> dict[str, Any]:
    app = _app()
    target: QtWidgets.QWidget = _main_window()
    if req.get("window") == "active":
        target = app.activePopupWidget() or _top_dialog() or target
    path = Path(req["path"])
    _save_replacing(pixmap=target.grab(), path=path)
    return {
        "path": str(path),
        "window": target.windowTitle(),
        "size": [target.width(), target.height()],
    }


def _save_replacing(*, pixmap: QtGui.QPixmap, path: Path) -> None:
    fd, scratch = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=path.suffix
    )
    os.close(fd)
    try:
        if not pixmap.save(scratch):
            raise CtlError(f"could not write {path}")
        os.replace(scratch, path)
    finally:
        Path(scratch).unlink(missing_ok=True)


def _writes_confined(*, run_dir: Path) -> bool:
    probe = run_dir.parent / f".{run_dir.name}.sandbox-probe"
    try:
        os.close(os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL))
    except PermissionError:
        return True
    except OSError:
        return False
    probe.unlink()
    return False


def _doctor(*, run_dir: Path) -> dict[str, Any]:
    return {
        "writes_confined": _writes_confined(run_dir=run_dir),
        "uncaught_exception": UNCAUGHT[-1] if UNCAUGHT else None,
        "pid": os.getpid(),
        "labelme_version": labelme.__version__,
        "labelme_file": labelme.__file__,
        "python": sys.executable,
        "qt": QtCore.qVersion(),
        "platform": QtGui.QGuiApplication.platformName(),
        "home": os.environ.get("HOME"),
        "window_state_file": QtCore.QSettings("labelme", "labelme").fileName(),
    }


def _parse_request(*, line: bytes) -> dict[str, Any] | None:
    try:
        req = json.loads(line)
    except (ValueError, RecursionError):
        return None
    return req if isinstance(req, dict) else None


def _drop(*, sock: QtNetwork.QTcpSocket) -> None:
    sock.abort()
    sock.deleteLater()


class Controller(QtCore.QObject):
    _server: QtNetwork.QTcpServer
    _token: str
    _run_dir: Path
    _sized: bool

    def __init__(self, *, run_dir: Path) -> None:
        super().__init__()
        self._run_dir = run_dir
        self._token = json.loads((run_dir / RUN_FILE).read_text())["token"]
        self._server = QtNetwork.QTcpServer(self)
        localhost = QtNetwork.QHostAddress.SpecialAddress.LocalHost
        if not self._server.listen(QtNetwork.QHostAddress(localhost), 0):
            raise RuntimeError(self._server.errorString())
        self._server.newConnection.connect(self._on_connection)
        self._sized = False
        instance = {
            "port": self._server.serverPort(),
            "pid": os.getpid(),
            "checkout": os.getcwd(),
        }
        tmp = run_dir / "instance.json.tmp"
        tmp.write_text(json.dumps(instance))
        tmp.replace(run_dir / "instance.json")

    def _on_connection(self) -> None:
        sock = self._server.nextPendingConnection()
        sock.disconnected.connect(sock.deleteLater)
        sock.readyRead.connect(lambda: self._on_ready(sock=sock))

    def _on_ready(self, *, sock: QtNetwork.QTcpSocket) -> None:
        try:
            self._serve(sock=sock)
        except Exception:
            _drop(sock=sock)

    def _serve(self, *, sock: QtNetwork.QTcpSocket) -> None:
        if sock.bytesAvailable() > MAX_REQUEST_BYTES:
            _drop(sock=sock)
            return
        if not sock.canReadLine():
            return
        req = _parse_request(line=bytes(sock.readLine().data()))
        token = req.pop("token", None) if req else None
        if not (
            isinstance(token, str)
            and token.isascii()
            and secrets.compare_digest(token, self._token)
        ):
            self._reply(sock=sock, payload={"ok": False, "error": "rejected request"})
            return
        assert req is not None
        try:
            self._size_main_window()
            self._handle(sock=sock, req=req)
        except CtlError as e:
            self._reply(sock=sock, payload={"ok": False, "error": str(e)})
        except Exception:
            self._reply(
                sock=sock, payload={"ok": False, "error": traceback.format_exc()}
            )

    def _size_main_window(self) -> None:
        win = _find_main_window()
        if self._sized or win is None or not win.isVisible():
            return
        win.resize(WINDOW_SIZE)
        win.activateWindow()
        self._sized = True

    def _reply(self, *, sock: QtNetwork.QTcpSocket, payload: dict[str, Any]) -> None:
        sock.write(json.dumps(payload, ensure_ascii=False).encode() + b"\n")
        sock.flush()
        sock.disconnectFromHost()

    def _handle(self, *, sock: QtNetwork.QTcpSocket, req: dict[str, Any]) -> None:
        observers: dict[str, Callable[[], object]] = {
            "state": _state,
            "doctor": lambda: _doctor(run_dir=self._run_dir),
            "screenshot": lambda: _screenshot(req=req),
        }
        if req.get("cmd") not in observers:
            raise CtlError(f"unknown command {req.get('cmd')!r}")
        result = observers[req["cmd"]]()
        self._reply(sock=sock, payload={"ok": True, "result": result})


def _isolate_window_state(*, home: Path) -> None:
    native = QtCore.QSettings

    class ScratchSettings(native):
        def __init__(self, organization: str, application: str) -> None:  # noqa: GR013 -- labelme calls QSettings(organization, application)
            path = home / "qtsettings" / f"{organization}-{application}.ini"
            super().__init__(str(path), native.Format.IniFormat)

    setattr(QtCore, "QSettings", ScratchSettings)


def _block_external_launches() -> None:
    def record_url(url: str, *_: object, **__: object) -> bool:  # noqa: GR013 -- labelme calls webbrowser.open(url)
        BLOCKED.append(f"open {url}")
        return True

    def record_launch(args: list[object], *_: object, **__: object) -> None:  # noqa: GR013 -- labelme calls subprocess.Popen([...])
        BLOCKED.append(" ".join(str(arg) for arg in args))

    launcher = types.ModuleType("subprocess")
    setattr(launcher, "Popen", record_launch)

    setattr(webbrowser, "open", record_url)
    setattr(labelme_app, "subprocess", launcher)


def _record_uncaught_exceptions() -> None:
    handle_exception = labelme_entry._handle_exception

    def record(  # noqa: GR013 -- sys.excepthook passes three positional arguments
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: types.TracebackType | None,
        /,
    ) -> None:
        UNCAUGHT.append(f"{exc_type.__name__}: {exc_value}")
        handle_exception(exc_type, exc_value, exc_traceback)

    setattr(labelme_entry, "_handle_exception", record)


def serve(*, run_dir: Path, labelme_args: list[str]) -> None:
    if labelme_args[:1] == ["--"]:
        labelme_args = labelme_args[1:]
    _isolate_window_state(home=run_dir / "home")
    _block_external_launches()
    _record_uncaught_exceptions()
    controllers: list[Controller] = []

    class ControlledApplication(QtWidgets.QApplication):
        def __init__(self, argv: list[str]) -> None:  # noqa: GR013 -- labelme calls QApplication(sys.argv)
            super().__init__(argv)
            QtCore.QTimer.singleShot(
                0, lambda: controllers.append(Controller(run_dir=run_dir))
            )

    setattr(QtWidgets, "QApplication", ControlledApplication)
    sys.argv = ["labelme", *labelme_args]
    try:
        labelme_main()
    except SystemExit as error:
        (run_dir / EXIT_FILE).write_text(str(error.code or 0))
        raise
