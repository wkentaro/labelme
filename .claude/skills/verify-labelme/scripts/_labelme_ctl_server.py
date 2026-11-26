from __future__ import annotations

import functools
import json
import math
import os
import re
import secrets
import sys
import tempfile
import traceback
import types
import unicodedata
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any
from typing import Final
from typing import NamedTuple

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtNetwork
from PySide6 import QtWidgets
from PySide6.QtCore import QPoint
from PySide6.QtCore import QPointF
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

import labelme
from labelme import __main__ as labelme_entry
from labelme import _app as labelme_app
from labelme.__main__ import main as labelme_main
from labelme._app import MainWindow
from labelme._widgets._canvas import Canvas

SETTLE_MS: Final = 300
ACTIVATE_POLL_MS: Final = 50
ACTIVATE_TIMEOUT_MS: Final = 1000
INPUT_TIMEOUT_MS: Final = 20_000
MAX_ROWS: Final = 200
DRAG_STEPS: Final = 8
WINDOW_SIZE: Final = QtCore.QSize(1280, 800)
BUTTONS: Final = {
    "left": Qt.MouseButton.LeftButton,
    "right": Qt.MouseButton.RightButton,
    "middle": Qt.MouseButton.MiddleButton,
}
MODIFIERS: Final = {
    None: Qt.KeyboardModifier.NoModifier,
    "shift": Qt.KeyboardModifier.ShiftModifier,
}
CLICKABLE: Final = (
    QtWidgets.QAbstractButton,
    QtWidgets.QLineEdit,
    QtWidgets.QPlainTextEdit,
    QtWidgets.QTextEdit,
)

RUN_FILE: Final = "run.json"
EXIT_FILE: Final = "exit_code"
MAX_REQUEST_BYTES: Final = 1 << 20
SEARCH_ROOT_KEEPALIVE: Final[list[QtWidgets.QWidget]] = []
BLOCKED: Final[list[str]] = []
UNCAUGHT: Final[list[str]] = []


class CtlError(Exception):
    pass


class Step(NamedTuple):
    delivers: str
    send: Callable[[], None]


def _app() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    assert isinstance(app, QtWidgets.QApplication)
    return app


def _norm(*, text: str) -> str:
    text = text.replace("&&", "\0").replace("&", "").replace("\0", "&")
    text = " ".join(text.split("\t")[0].split())
    return text.rstrip("…").rstrip(".").strip().casefold()


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


def _canvas() -> Canvas:
    canvases = _main_window().findChildren(Canvas)
    if not canvases:
        raise CtlError("no Canvas widget")
    return canvases[0]


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


class Clickable(NamedTuple):
    image: tuple[float, float, float, float]
    pixels: QtCore.QRect


def _clickable(*, canvas: Canvas) -> Clickable:
    width, height = canvas.pixmap.width(), canvas.pixmap.height()
    view = canvas.visibleRegion().boundingRect()
    origin = canvas.transform_image_point_to_widget(point=QPointF(0, 0))
    corner = canvas.transform_image_point_to_widget(point=QPointF(width, height))
    low = canvas.transform_widget_point_to_image(point=QPointF(view.topLeft()))
    high = canvas.transform_widget_point_to_image(point=QPointF(view.bottomRight()))
    image = (
        0 if origin.x() >= view.left() - 1 else low.x(),
        0 if origin.y() >= view.top() - 1 else low.y(),
        width if corner.x() <= view.right() + 1 else high.x(),
        height if corner.y() <= view.bottom() + 1 else high.y(),
    )
    inside_image = QtCore.QRect(
        QPoint(math.ceil(origin.x()), math.ceil(origin.y())),
        QPoint(math.floor(corner.x()), math.floor(corner.y())),
    )
    return Clickable(image=image, pixels=inside_image.intersected(view))


def _canvas_info(*, win: MainWindow) -> dict[str, Any] | None:
    if not _image_loaded(win=win):
        return None
    canvas = win.findChildren(Canvas)[0]
    return {"scale": canvas.scale, "visible": list(_clickable(canvas=canvas).image)}


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
        "canvas": _canvas_info(win=win) if win else None,
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


def _walk_menu(*, menu: QtWidgets.QMenu, prefix: str) -> list[dict[str, Any]]:
    menu.aboutToShow.emit()
    entries: list[dict[str, Any]] = []
    for action in menu.actions():
        if action.isSeparator() or not action.isVisible():
            continue
        path = f"{prefix} > {action.text().replace('&', '')}"
        submenu = action.menu()
        if isinstance(submenu, QtWidgets.QMenu):
            entries += _walk_menu(menu=submenu, prefix=path)
            continue
        entry: dict[str, Any] = {"path": path}
        if not action.isEnabled():
            entry["enabled"] = False
        if action.isCheckable():
            entry["checked"] = action.isChecked()
        if not action.shortcut().isEmpty():
            entry["shortcut"] = action.shortcut().toString()
        entries.append(entry)
    return entries


def _menu() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for action in _main_window().menuBar().actions():
        menu = action.menu()
        if isinstance(menu, QtWidgets.QMenu) and action.isVisible():
            entries += _walk_menu(menu=menu, prefix=action.text().replace("&", ""))
    return entries


def _find_action(*, path: str) -> QtGui.QAction:
    parts = [p for p in (s.strip() for s in path.split(">")) if p]
    actions = _main_window().menuBar().actions()
    for depth, part in enumerate(parts):
        items = [a for a in actions if not a.isSeparator()]
        matches = [a for a in items if _norm(text=a.text()) == _norm(text=part)]
        if not matches:
            available = [a.text().replace("&", "") for a in items]
            raise CtlError(f"no menu item {part!r} under {parts[:depth]}: {available}")
        action = matches[0]
        submenu = action.menu()
        if depth == len(parts) - 1:
            if submenu is not None:
                raise CtlError(f"{path!r} is a submenu, not an item")
            if not action.isVisible() or not action.isEnabled():
                raise CtlError(f"{path!r} is disabled")
            return action
        if not isinstance(submenu, QtWidgets.QMenu):
            raise CtlError(f"{part!r} is not a menu")
        submenu.aboutToShow.emit()
        actions = submenu.actions()
    raise CtlError(f"empty menu path {path!r}")


def _search_root() -> QtWidgets.QWidget:
    app = _app()
    root = app.activePopupWidget() or _top_dialog() or _main_window()
    SEARCH_ROOT_KEEPALIVE[:] = [root]
    return root


def _names(*, widget: QtWidgets.QWidget) -> set[str]:
    names = {_norm(text=widget.toolTip()), _norm(text=widget.accessibleName())}
    if isinstance(widget, QtWidgets.QAbstractButton):
        names.add(_norm(text=widget.text()))
    if isinstance(
        widget, QtWidgets.QLineEdit | QtWidgets.QPlainTextEdit | QtWidgets.QTextEdit
    ):
        names.add(_norm(text=widget.placeholderText()))
    return names - {""}


def _find_clickable(*, name: str) -> QtWidgets.QWidget:
    root = _search_root()
    matches = [
        w
        for w in root.findChildren(QtWidgets.QWidget)
        if isinstance(w, CLICKABLE)
        and _visible(widget=w)
        and _norm(text=name) in _names(widget=w)
    ]
    if not matches:
        raise CtlError(f"no button or field {name!r} in {root.windowTitle()!r}")
    if len(matches) > 1:
        raise CtlError(f"{len(matches)} widgets match {name!r}; use a menu or key")
    if not matches[0].isEnabled():
        raise CtlError(f"{name!r} is disabled")
    return matches[0]


def _find_view(*, name: str) -> QtWidgets.QAbstractItemView:
    for view in _search_root().findChildren(QtWidgets.QAbstractItemView):
        if _visible(widget=view) and _norm(text=view.accessibleName()) == _norm(
            text=name
        ):
            return view
    for dock in _docks():
        if _norm(text=dock.windowTitle()) != _norm(text=name):
            continue
        views = dock.findChildren(QtWidgets.QAbstractItemView)
        visible = [v for v in views if _visible(widget=v)]
        if visible:
            return visible[0]
    raise CtlError(f"no visible list {name!r}")


def _find_row(*, view: QtWidgets.QAbstractItemView, text: str) -> QtCore.QModelIndex:
    model = view.model()
    root = view.rootIndex()
    indexes = [model.index(r, 0, root) for r in range(model.rowCount(root))]
    rows = [(i, _row_text(view=view, index=i)) for i in indexes]
    exact = [(i, t) for i, t in rows if t == text]
    if len(exact) == 1:
        return exact[0][0]
    partial = [(i, t) for i, t in rows if text in t]
    if len(exact) > 1 or len(partial) != 1:
        matches = [t for _, t in (exact or partial)][:10]
        raise CtlError(f"{len(exact) or len(partial)} rows match {text!r}: {matches}")
    return partial[0][0]


def _focus_target() -> QtWidgets.QWidget:
    app = _app()
    return (
        app.activePopupWidget()
        or app.focusWidget()
        or _top_dialog()
        or app.activeWindow()
        or _main_window()
    )


def _canvas_pos(*, x: float, y: float) -> QPoint:
    canvas = _canvas()
    pixmap = canvas.pixmap
    if pixmap is None or pixmap.isNull():
        raise CtlError("no image is open on the canvas")
    width, height = pixmap.width(), pixmap.height()
    if not (0 <= x <= width and 0 <= y <= height):
        raise CtlError(f"({x}, {y}) is outside the {width}x{height} image")
    clickable = _clickable(canvas=canvas)
    left, top, right, bottom = clickable.image
    if not (left <= x <= right and top <= y <= bottom):
        raise CtlError(f"({x}, {y}) is not visible on the canvas; scroll or zoom")
    point = canvas.transform_image_point_to_widget(point=QPointF(x, y))
    pixels = clickable.pixels
    return QPoint(
        min(max(round(point.x()), pixels.left()), pixels.right()),
        min(max(round(point.y()), pixels.top()), pixels.bottom()),
    )


def _send_move(
    *,
    widget: QtWidgets.QWidget,
    pos: QPoint,
    buttons: Qt.MouseButton = Qt.MouseButton.NoButton,
    modifier: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    event = QtGui.QMouseEvent(
        QtGui.QMouseEvent.Type.MouseMove,
        QPointF(pos),
        QPointF(widget.mapToGlobal(pos)),
        Qt.MouseButton.NoButton,
        buttons,
        modifier,
    )
    QtWidgets.QApplication.sendEvent(widget, event)


def _release_held_buttons() -> None:
    for button in _held_buttons():
        QTest.mouseRelease(QtWidgets.QWidget(), button)


def _try_activate_top_window() -> bool:
    app = _app()
    top = _search_root().window()
    if app.activePopupWidget() is top or app.activeWindow() is top:
        return True
    top.activateWindow()
    return False


def _activate_top_window() -> None:
    deadline = QtCore.QDeadlineTimer(ACTIVATE_TIMEOUT_MS)
    while not _try_activate_top_window() and not deadline.hasExpired():
        _app().processEvents(
            QtCore.QEventLoop.ProcessEventsFlag.AllEvents, ACTIVATE_POLL_MS
        )


def _type_char(char: str) -> None:
    if char == "\n":
        QTest.keyClick(_focus_target(), Qt.Key.Key_Return)
    else:
        QTest.keyClicks(_focus_target(), char)


def _type_steps(*, text: str) -> list[Step]:
    return [
        Step(delivers=char, send=functools.partial(_type_char, char)) for char in text
    ]


def _plan_key(*, req: dict[str, Any]) -> tuple[str, Callable[[], None]]:
    sequence = QtGui.QKeySequence(req["sequence"])
    if sequence.count() != 1:
        raise CtlError(f"{req['sequence']!r} is not one key stroke; send one per key")
    combo = sequence[0]  # ty: ignore[not-subscriptable]
    if combo.key() == Qt.Key.Key_unknown or not sequence.toString():
        raise CtlError(f"{req['sequence']!r} is not a Qt key name")
    target = _focus_target()
    return (
        f"key {sequence.toString()} on {type(target).__name__}",
        lambda: QTest.keyClick(target, combo.key(), combo.keyboardModifiers()),
    )


def _plan_menu_click(
    *, menu: QtWidgets.QMenu, name: str
) -> tuple[str, Callable[[], None]]:
    matches = [
        a for a in _menu_actions(menu=menu) if _norm(text=a.text()) == _norm(text=name)
    ]
    if len(matches) != 1:
        raise CtlError(f"{len(matches)} items named {name!r} in the open menu")
    if not matches[0].isEnabled():
        raise CtlError(f"{name!r} is disabled")
    pos = menu.actionGeometry(matches[0]).center()
    return (
        f"click menu item {name!r}",
        lambda: QTest.mouseClick(
            menu, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pos
        ),
    )


def _plan_click(*, req: dict[str, Any]) -> tuple[str, Callable[[], None]]:
    root = _search_root()
    if isinstance(root, QtWidgets.QMenu):
        return _plan_menu_click(menu=root, name=req["name"])
    widget = _find_clickable(name=req["name"])
    target = (
        widget.viewport()
        if isinstance(widget, QtWidgets.QAbstractScrollArea)
        else widget
    )
    return (
        f"click {type(widget).__name__} {req['name']!r}",
        lambda: QTest.mouseClick(target, Qt.MouseButton.LeftButton),
    )


def _require_reachable(*, widget: QtWidgets.QWidget) -> None:
    root = _search_root()
    if widget.window() is not root.window():
        name = root.windowTitle() or type(root).__name__
        raise CtlError(f"{name!r} is open and blocks this input; close it first")


def _plan_pick(*, req: dict[str, Any]) -> tuple[str, Callable[[], None]]:
    view = _find_view(name=req["list"])
    _require_reachable(widget=view)
    index = _find_row(view=view, text=req["text"])
    usable = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
    if index.flags() & usable != usable:
        raise CtlError(f"row {req['text']!r} in {req['list']!r} is disabled")
    view.scrollTo(index)
    viewport = view.viewport()
    center = view.visualRect(index).center()
    left = Qt.MouseButton.LeftButton
    no_modifier = Qt.KeyboardModifier.NoModifier

    def pick() -> None:
        QTest.mouseClick(viewport, left, no_modifier, center)
        if req.get("double"):
            QTest.mouseDClick(viewport, left, no_modifier, center)

    return f"pick {_row_text(view=view, index=index)!r} in {req['list']!r}", pick


def _plan_click_canvas(*, req: dict[str, Any]) -> tuple[str, Callable[[], None]]:
    canvas = _canvas()
    _require_reachable(widget=canvas)
    pos = _canvas_pos(x=req["x"], y=req["y"])
    button = BUTTONS[req.get("button", "left")]
    modifier = MODIFIERS[req.get("modifier")]

    def click() -> None:
        _send_move(widget=canvas, pos=pos, modifier=modifier)
        QTest.mouseClick(canvas, button, modifier, pos)

    return f"click canvas at image ({req['x']}, {req['y']})", click


def _plan_drag_canvas(*, req: dict[str, Any]) -> tuple[str, Callable[[], None]]:
    canvas = _canvas()
    _require_reachable(widget=canvas)
    start = _canvas_pos(x=req["x1"], y=req["y1"])
    end = _canvas_pos(x=req["x2"], y=req["y2"])
    left = Qt.MouseButton.LeftButton
    no_modifier = Qt.KeyboardModifier.NoModifier

    def drag() -> None:
        _send_move(widget=canvas, pos=start)
        QTest.mousePress(canvas, left, no_modifier, start)
        for i in range(1, DRAG_STEPS + 1):
            pos = start + (end - start) * (i / DRAG_STEPS)
            _send_move(widget=canvas, pos=pos, buttons=left)
        QTest.mouseRelease(canvas, left, no_modifier, end)

    span = f"({req['x1']}, {req['y1']}) to ({req['x2']}, {req['y2']})"
    return f"drag canvas from image {span}", drag


def _plan_input(*, req: dict[str, Any]) -> tuple[str, list[Step]]:
    _release_held_buttons()
    _activate_top_window()
    cmd = req.get("cmd")
    if cmd == "action":
        if _search_root() is not _main_window():
            raise CtlError("a dialog or popup blocks the menu bar; close it first")
        description = f"menu {req['path']}"
        action = _find_action(path=req["path"])
        return description, [Step(delivers=description, send=action.trigger)]
    if cmd == "type":
        controls = {
            c for c in req["text"] if c != "\n" and unicodedata.category(c) == "Cc"
        }
        if controls:
            raise CtlError(
                f"cannot type control characters {sorted(controls)}; use key"
            )
        if not req["text"].isascii():
            raise CtlError("cannot type non-ASCII text")
        target = _focus_target()
        return f"type into {type(target).__name__}", _type_steps(text=req["text"])
    planners = {
        "key": _plan_key,
        "click": _plan_click,
        "pick": _plan_pick,
        "click-canvas": _plan_click_canvas,
        "drag-canvas": _plan_drag_canvas,
    }
    if cmd not in planners:
        raise CtlError(f"unknown command {cmd!r}")
    description, run = planners[cmd](req=req)
    return description, [Step(delivers=description, send=run)]


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
        tmp.unlink(missing_ok=True)
        with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "w") as f:
            f.write(json.dumps(instance))
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
            "menu": _menu,
            "doctor": lambda: _doctor(run_dir=self._run_dir),
            "screenshot": lambda: _screenshot(req=req),
        }
        if req.get("cmd") in observers:
            result = observers[req["cmd"]]()
            self._reply(sock=sock, payload={"ok": True, "result": result})
            return
        description, steps = _plan_input(req=req)
        settle = QtCore.QTimer(sock)
        settle.setSingleShot(True)
        limit = QtCore.QTimer(sock)
        limit.setSingleShot(True)
        activation = QtCore.QDeadlineTimer(ACTIVATE_TIMEOUT_MS)
        answered = False

        def answer(*, error: str | None) -> None:
            nonlocal answered
            if answered:
                return
            answered = True
            limit.stop()
            settle.stop()
            result = {"did": description, "state": _state()}
            if steps:
                result["undelivered"] = "".join(step.delivers for step in steps)
                steps.clear()
            payload = {"ok": error is None, "result": result, "error": error}
            self._reply(sock=sock, payload=payload)

        def run_next() -> None:
            if not steps:
                return
            if not _try_activate_top_window() and not activation.hasExpired():
                QtCore.QTimer.singleShot(ACTIVATE_POLL_MS, settle, run_next)
                return
            activation.setRemainingTime(ACTIVATE_TIMEOUT_MS)
            step = steps.pop(0)
            settle.start(SETTLE_MS)
            QtCore.QTimer.singleShot(0, settle, run_next)
            try:
                step.send()
            except Exception:
                steps.insert(0, step)
                answer(error=traceback.format_exc())

        def settled() -> None:
            if not steps:
                answer(error=None)

        def timed_out() -> None:
            if steps:
                seconds = INPUT_TIMEOUT_MS // 1000
                answer(error=f"input not delivered within {seconds}s")

        settle.timeout.connect(settled)
        limit.timeout.connect(timed_out)
        limit.start(INPUT_TIMEOUT_MS)
        QtCore.QTimer.singleShot(0, settle, run_next)


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
