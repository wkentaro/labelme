from __future__ import annotations

import argparse
import codecs
import contextlib
import io
import os
import os.path as osp
import sys
import traceback
import types
import warnings
from pathlib import Path
from typing import AnyStr

import yaml
from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

from labelme import __appname__
from labelme import __version__
from labelme.app import MainWindow
from labelme.config import get_user_config_file
from labelme.config import load_config
from labelme.utils import newIcon


class _LoggerIO(io.StringIO):
    def write(self, s: AnyStr) -> int:
        assert isinstance(s, str)
        if stripped_s := s.strip():
            logger.debug(stripped_s)
        return len(s)

    def flush(self) -> None:
        pass

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False

    @property
    def closed(self) -> bool:
        return False


def _setup_loguru(logger_level: str) -> None:
    try:
        logger.remove(handler_id=0)
    except ValueError:
        pass

    if sys.stderr:
        logger.add(sys.stderr, level=logger_level)

    cache_dir: str
    if os.name == "nt":
        cache_dir = os.path.join(os.environ["LOCALAPPDATA"], "labelme")
    else:
        cache_dir = os.path.expanduser("~/.cache/labelme")

    os.makedirs(cache_dir, exist_ok=True)

    log_file = os.path.join(cache_dir, "labelme.log")
    logger.add(
        log_file,
        colorize=True,
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        compression="gz",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )


def _handle_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: types.TracebackType | None,
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        sys.exit(0)

    traceback_str: str = "".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)
    )
    logger.critical(traceback_str)

    traceback_html: str = traceback_str.replace("\n", "<br/>").replace(" ", "&nbsp;")
    QtWidgets.QMessageBox.critical(
        None,
        "Error",
        f"An unexpected error occurred. The application will close.<br/><br/>Please report issues following the <a href='https://labelme.io/docs/troubleshoot'>Troubleshoot</a>.<br/><br/>{traceback_html}",  # noqa: E501
    )

    if app := QtWidgets.QApplication.instance():
        app.quit()
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", "-V", action="store_true", help="show version")
    parser.add_argument("--reset-config", action="store_true", help="reset qt config")
    parser.add_argument(
        "--dark-mode",
        dest="dark_mode",
        action="store_true",
        help="enable dark mode",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--logger-level",
        default="debug",
        choices=["debug", "info", "warning", "fatal", "error"],
        help="logger level",
    )
    parser.add_argument("path", nargs="?", help="image file, label file, or directory")
    parser.add_argument(
        "--output",
        help="output directory for saving annotation JSON files",
    )
    default_config_file = get_user_config_file()
    parser.add_argument(
        "--config",
        dest="config",
        help=f"config file or yaml-format string (default: {default_config_file})",
        default=default_config_file,
    )
    # config for the gui
    parser.add_argument(
        "--nodata",
        dest="_deprecated_nodata",
        action="store_true",
        help=argparse.SUPPRESS,
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--with-image-data",
        dest="with_image_data",
        action="store_true",
        help="store image data in JSON file",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-auto-save",
        dest="auto_save",
        action="store_false",
        help="disable auto save",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--autosave",
        dest="_deprecated_autosave",
        action="store_true",
        help=argparse.SUPPRESS,
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-sort-labels",
        "--nosortlabels",  # deprecated
        dest="sort_labels",
        action="store_false",
        help="stop sorting labels",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--flags",
        help="comma separated list of flags OR file containing flags",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--label-flags",
        "--labelflags",  # deprecated
        dest="label_flags",
        help=r"yaml string of label specific flags OR file containing json "
        r"string of label specific flags (ex. {person-\d+: [male, tall], "
        r"dog-\d+: [black, brown, white], .*: [occluded]})",  # NOQA
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--labels",
        help="comma separated list of labels OR file containing labels",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--validate-label",
        "--validatelabel",  # deprecated
        dest="validate_label",
        choices=["exact"],
        help="label validation types",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--keep-prev",
        action="store_true",
        help="keep annotation of previous frame",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--epsilon",
        type=float,
        help="epsilon to find nearest vertex on canvas",
        default=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if hasattr(args, "_deprecated_nodata"):
        warnings.warn(
            "--nodata is deprecated and will be removed in a future version. "
            "Image data is no longer stored by default. "
            "Use --with-image-data to store it.",
            FutureWarning,
            stacklevel=1,
        )
        del args._deprecated_nodata

    if hasattr(args, "_deprecated_autosave"):
        warnings.warn(
            "--autosave is deprecated and will be removed in a future version. "
            "Auto save is now enabled by default. Use --no-autosave to disable it.",
            FutureWarning,
            stacklevel=1,
        )
        del args._deprecated_autosave

    if args.version:
        print(f"{__appname__} {__version__}")
        sys.exit(0)

    _setup_loguru(logger_level=args.logger_level.upper())
    logger.info("Starting {} {}", __appname__, __version__)

    sys.excepthook = _handle_exception

    if hasattr(args, "flags"):
        if os.path.isfile(args.flags):
            with codecs.open(args.flags, "r", encoding="utf-8") as f:
                args.flags = [line.strip() for line in f if line.strip()]
        else:
            args.flags = [line for line in args.flags.split(",") if line]

    if hasattr(args, "labels"):
        if os.path.isfile(args.labels):
            with codecs.open(args.labels, "r", encoding="utf-8") as f:
                args.labels = [line.strip() for line in f if line.strip()]
        else:
            args.labels = [line for line in args.labels.split(",") if line]

    if hasattr(args, "label_flags"):
        if os.path.isfile(args.label_flags):
            with codecs.open(args.label_flags, "r", encoding="utf-8") as f:
                args.label_flags = yaml.safe_load(f)
        else:
            args.label_flags = yaml.safe_load(args.label_flags)

    config_from_args = args.__dict__
    config_from_args.pop("version")
    reset_config = config_from_args.pop("reset_config")
    file_or_dir = config_from_args.pop("path")
    output = config_from_args.pop("output")

    config_overrides: dict
    config_file: Path | None
    config_str: str = config_from_args.pop("config")
    if isinstance(config_loaded := yaml.safe_load(config_str), dict):
        config_overrides = config_loaded
        config_file = None
    else:
        config_overrides = {}
        config_file = Path(config_str)
        if not config_file.is_file():
            logger.error(
                "Config file does not exist: {!r}", str(config_file.absolute())
            )
            sys.exit(1)
    del config_str
    config_overrides.update(config_from_args)

    output_dir = None
    if output is not None:
        if output.endswith(".json"):
            parser.error(
                f"--output expects a directory path, but '{output}' looks like a file."
                " Remove the .json extension or provide a directory path."
            )
        output_dir = output

    # Load full config to get dark_mode setting (before GUI starts)
    full_config = load_config(config_file, config_overrides)

    translator = QtCore.QTranslator()
    translator.load(
        QtCore.QLocale.system().name(),
        f"{osp.dirname(osp.abspath(__file__))}/translate",
    )
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")  # for consistent appearance across platforms

    # Check if dark mode is enabled in config
    dark_mode_enabled = full_config.get("dark_mode", False)
    logger.info(f"Dark mode enabled from config: {dark_mode_enabled}")

    if dark_mode_enabled:
        # Dark mode palette for eye comfort during long annotation sessions
        dark_palette = QtGui.QPalette()
        dark_palette.setColor(QtGui.QPalette.Window, QtGui.QColor(53, 53, 53))
        dark_palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
        dark_palette.setColor(QtGui.QPalette.Base, QtGui.QColor(35, 35, 35))
        dark_palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(53, 53, 53))
        dark_palette.setColor(QtGui.QPalette.ToolTipBase, QtCore.Qt.white)
        dark_palette.setColor(QtGui.QPalette.ToolTipText, QtCore.Qt.white)
        dark_palette.setColor(QtGui.QPalette.Text, QtCore.Qt.white)
        dark_palette.setColor(QtGui.QPalette.Button, QtGui.QColor(53, 53, 53))
        dark_palette.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.white)
        dark_palette.setColor(QtGui.QPalette.BrightText, QtCore.Qt.red)
        dark_palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(42, 130, 218))
        dark_palette.setColor(QtGui.QPalette.HighlightedText, QtCore.Qt.black)
        dark_palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(127, 127, 127))
        dark_palette.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(127, 127, 127))
        app.setPalette(dark_palette)

    # Dark mode stylesheet for all Qt widgets
    dark_stylesheet = """
    QWidget { background-color: #353535; color: #ffffff; }
    QMainWindow { background-color: #353535; }
    QMenuBar { background-color: #353535; color: #ffffff; }
    QMenuBar::item:selected { background-color: #2a82da; }
    QMenu { background-color: #353535; color: #ffffff; border: 1px solid #555555; }
    QMenu::item:selected { background-color: #2a82da; }
    QToolBar { background-color: #353535; border: none; }
    QToolButton { background-color: #353535; color: #ffffff; border: none; padding: 4px; }
    QToolButton:hover { background-color: #2a82da; }
    QToolButton:pressed { background-color: #1a62a8; }
    QToolButton:checked { background-color: #2a82da; }
    QPushButton { background-color: #454545; color: #ffffff; border: 1px solid #555555; padding: 4px 12px; border-radius: 3px; }
    QPushButton:hover { background-color: #555555; }
    QPushButton:pressed { background-color: #333333; }
    QPushButton:checked { background-color: #2a82da; color: #000000; }
    QPushButton:disabled { background-color: #404040; color: #777777; }
    QLineEdit, QTextEdit, QPlainTextEdit { background-color: #232323; color: #ffffff; border: 1px solid #555555; padding: 2px; }
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus { border: 1px solid #2a82da; }
    QComboBox { background-color: #454545; color: #ffffff; border: 1px solid #555555; padding: 4px; }
    QComboBox:hover { background-color: #555555; }
    QComboBox::drop-down { border: none; }
    QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 6px solid #ffffff; }
    QListWidget { background-color: #232323; color: #ffffff; border: 1px solid #555555; }
    QListWidget::item:selected { background-color: #2a82da; color: #000000; }
    QListWidget::item:hover { background-color: #454545; }
    QTreeWidget, QTreeView { background-color: #232323; color: #ffffff; border: 1px solid #555555; }
    QTreeWidget::item:selected { background-color: #2a82da; color: #000000; }
    QHeaderView::section { background-color: #454545; color: #ffffff; border: 1px solid #555555; padding: 4px; }
    QScrollBar:vertical { background: #353535; width: 12px; margin: 0px; }
    QScrollBar::handle:vertical { background: #555555; min-height: 20px; border-radius: 5px; }
    QScrollBar::handle:vertical:hover { background: #666666; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
    QScrollBar:horizontal { background: #353535; height: 12px; margin: 0px; }
    QScrollBar::handle:horizontal { background: #555555; min-width: 20px; border-radius: 5px; }
    QScrollBar::handle:horizontal:hover { background: #666666; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
    QLabel { color: #ffffff; background-color: transparent; }
    QCheckBox { color: #ffffff; spacing: 8px; }
    QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #555555; background-color: #232323; }
    QCheckBox::indicator:checked { background-color: #2a82da; border: 1px solid #2a82da; }
    QRadioButton { color: #ffffff; spacing: 8px; }
    QRadioButton::indicator { width: 16px; height: 16px; border: 1px solid #555555; border-radius: 7px; background-color: #232323; }
    QRadioButton::indicator:checked { background-color: #2a82da; border: 1px solid #2a82da; }
    QGroupBox { color: #ffffff; border: 1px solid #555555; border-radius: 3px; margin-top: 8px; padding-top: 16px; }
    QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 8px; }
    QTabWidget::pane { border: 1px solid #555555; background-color: #353535; }
    QTabBar::tab { background-color: #353535; color: #ffffff; border: 1px solid #555555; padding: 6px 12px; }
    QTabBar::tab:selected { background-color: #2a82da; color: #000000; }
    QTabBar::tab:hover { background-color: #454545; }
    QDockWidget { color: #ffffff; titlebar-close-icon: url(none); titlebar-normal-icon: url(none); }
    QDockWidget::title { background-color: #353535; color: #ffffff; padding: 4px; }
    QDockWidget::content { background-color: #353535; }
    QStatusBar { background-color: #353535; color: #ffffff; }
    QSpinBox, QDoubleSpinBox { background-color: #232323; color: #ffffff; border: 1px solid #555555; padding: 2px; }
    QSpinBox::up-button, QDoubleSpinBox::up-button { background-color: #454545; border-left: 1px solid #555555; }
    QSpinBox::down-button, QDoubleSpinBox::down-button { background-color: #454545; border-left: 1px solid #555555; border-right: none; }
    QSlider::groove:horizontal { background: #555555; height: 4px; }
    QSlider::handle:horizontal { background: #2a82da; width: 14px; margin: -5px 0; border-radius: 7px; }
    QSlider::add-page:horizontal { background: #2a82da; }
    QSlider::sub-page:horizontal { background: #555555; }
    QProgressBar { background-color: #232323; color: #ffffff; border: 1px solid #555555; text-align: center; }
    QProgressBar::chunk { background-color: #2a82da; }
    """
    if dark_mode_enabled:
        app.setStyleSheet(dark_stylesheet)
    app.setApplicationName(__appname__)
    app.setWindowIcon(newIcon("icon"))
    app.installTranslator(translator)
    win = MainWindow(
        config_file=config_file,
        config_overrides=config_overrides,
        file_or_dir=file_or_dir,
        output_dir=output_dir,
    )

    if reset_config:
        logger.info(f"Resetting Qt config: {win.settings.fileName()}")
        win.settings.clear()
        sys.exit(0)

    with contextlib.redirect_stderr(new_target=_LoggerIO()):
        win.show()
        win.raise_()
        sys.exit(app.exec_())


# this main block is required to generate executable by pyinstaller
if __name__ == "__main__":
    main()
