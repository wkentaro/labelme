from __future__ import annotations

import sys
from collections.abc import Callable
from collections.abc import Generator
from pathlib import Path

import pytest
import yaml
from PyQt5 import QtGui
from PyQt5.QtCore import QPoint
from PyQt5.QtCore import QPointF
from PyQt5.QtCore import QSettings
from PyQt5.QtCore import Qt
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

import labelme.app
from labelme.__main__ import main
from labelme.app import MainWindow
from labelme.widgets.canvas import Canvas
from labelme.widgets.label_dialog import LabelDialog


@pytest.fixture(scope="session")
def session_home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("home")


def image_to_widget_pos(canvas: Canvas, image_pos: QPointF) -> QPoint:
    widget_pos = (image_pos + canvas._compute_image_origin_offset()) * canvas.scale
    return QPoint(int(widget_pos.x()), int(widget_pos.y()))


@pytest.fixture(autouse=True)
def _isolated_qtsettings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    settings_file = tmp_path / "qtsettings.ini"
    settings: QSettings = QSettings(str(settings_file), QSettings.IniFormat)
    monkeypatch.setattr(
        labelme.app.QtCore, "QSettings", lambda *args, **kwargs: settings
    )
    yield


MainWinFactory = Callable[..., MainWindow]


class _QAppProxy:
    """Proxy that returns the existing QApplication from constructor calls
    and forwards static/class method access to the real QApplication class."""

    def __init__(self, existing_app: QApplication) -> None:
        self._app = existing_app

    def __call__(self, argv: list[str]) -> QApplication:
        return self._app

    def __getattr__(self, name: str) -> object:
        return getattr(QApplication, name)


@pytest.fixture()
def main_win(
    qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, session_home: Path
) -> Generator[MainWinFactory, None, None]:
    created: list[MainWindow] = []

    # Preserve original excepthook so main()'s override is undone after test
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)

    def create(
        *,
        file_or_dir: str | Path | None = None,
        config_file: str | Path | None = None,
        config_overrides: dict | None = None,
        output_dir: str | Path | None = None,
    ) -> MainWindow:
        argv = ["labelme"]

        if config_file is not None:
            argv.extend(["--config", str(config_file)])
            if config_overrides:
                unhandled = set(config_overrides) - {"labels"}
                if unhandled:
                    raise ValueError(
                        f"Cannot pass {unhandled} with config_file via CLI"
                    )
                if "labels" in config_overrides:
                    argv.extend(["--labels", ",".join(config_overrides["labels"])])
        elif config_overrides:
            argv.extend(["--config", yaml.dump(config_overrides)])

        if output_dir is not None:
            argv.extend(["--output", str(output_dir)])

        if file_or_dir is not None:
            argv.append(str(file_or_dir))

        monkeypatch.setattr(sys, "argv", argv)
        monkeypatch.setenv("HOME", str(session_home))

        app = QApplication.instance()
        assert isinstance(app, QApplication)

        monkeypatch.setattr("labelme.__main__.QtWidgets.QApplication", _QAppProxy(app))
        monkeypatch.setattr(app, "exec_", lambda: 0)

        existing = set(w for w in app.topLevelWidgets() if isinstance(w, MainWindow))

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        for widget in app.topLevelWidgets():
            if isinstance(widget, MainWindow) and widget not in existing:
                created.append(widget)
                qtbot.addWidget(widget)
                return widget

        raise RuntimeError("main() did not create a MainWindow")

    yield create

    for win in created:
        try:
            win.close()
        except RuntimeError:
            pass


def click_canvas_fraction(
    qtbot: QtBot,
    canvas: Canvas,
    xy: tuple[float, float],
    modifier: Qt.KeyboardModifier = Qt.NoModifier,
) -> None:
    canvas_size = canvas.size()
    pos = QPoint(
        int(canvas_size.width() * xy[0]),
        int(canvas_size.height() * xy[1]),
    )
    qtbot.mouseMove(canvas, pos=pos)
    qtbot.wait(50)
    qtbot.mouseClick(canvas, Qt.LeftButton, modifier=modifier, pos=pos)
    qtbot.wait(50)


def drag_canvas(
    qtbot: QtBot,
    canvas: Canvas,
    button: Qt.MouseButton,
    start: QPoint,
    end: QPoint,
) -> None:
    qtbot.mousePress(canvas, button, pos=start)
    qtbot.wait(50)
    # qtbot.mouseMove does not carry button state, so send a raw event
    move_event = QtGui.QMouseEvent(
        QtGui.QMouseEvent.MouseMove,
        QPointF(end),
        Qt.NoButton,
        button,
        Qt.NoModifier,
    )
    QApplication.sendEvent(canvas, move_event)
    qtbot.wait(50)
    qtbot.mouseRelease(canvas, button, pos=end)
    qtbot.wait(50)


def submit_label_dialog(
    qtbot: QtBot,
    label_dialog: LabelDialog,
    label: str,
) -> None:
    def _poll() -> None:
        if not label_dialog.isVisible():
            QTimer.singleShot(50, _poll)
            return
        label_dialog.edit.clear()
        qtbot.keyClicks(label_dialog.edit, label)
        qtbot.wait(50)
        qtbot.keyClick(label_dialog.edit, Qt.Key_Enter)

    QTimer.singleShot(0, _poll)


def select_shape(qtbot: QtBot, canvas: Canvas, shape_index: int = 0) -> None:
    shape_center = canvas.shapes[shape_index].bounding_rect().center()
    pos = image_to_widget_pos(canvas=canvas, image_pos=shape_center)
    qtbot.mouseMove(canvas, pos=pos)
    qtbot.wait(50)
    qtbot.mouseClick(canvas, Qt.LeftButton, pos=pos)
    qtbot.wait(50)
    assert len(canvas.selected_shapes) == 1


def show_window_and_wait_for_imagedata(qtbot: QtBot, win: MainWindow) -> None:
    win.show()

    def check_image_data() -> None:
        assert hasattr(win, "_image_data")
        assert win._image_data is not None

    qtbot.waitUntil(check_image_data)


@pytest.fixture()
def annotated_win(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> MainWindow:
    win = main_win(
        file_or_dir=str(data_path / "annotated/2011_000003.json"),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win


@pytest.fixture()
def raw_win(
    main_win: MainWinFactory,
    qtbot: QtBot,
    data_path: Path,
    tmp_path: Path,
) -> MainWindow:
    win = main_win(
        file_or_dir=str(data_path / "raw/2011_000003.jpg"),
        output_dir=str(tmp_path),
    )
    show_window_and_wait_for_imagedata(qtbot=qtbot, win=win)
    return win
