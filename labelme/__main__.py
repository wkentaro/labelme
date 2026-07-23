from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import traceback
import types
import warnings
from pathlib import Path
from typing import AnyStr
from typing import Final

from loguru import logger
from PySide6 import QtCore
from PySide6 import QtWidgets

from labelme import __appname__
from labelme import __version__

from . import _config
from . import _locale
from . import _yaml
from ._app import MainWindow
from ._label_file import is_label_file_path
from ._utils import apply_color_theme
from ._utils import new_icon

_LOGGER_LEVELS: Final = ("debug", "info", "warning", "error", "critical")


class _LoggerIO(io.StringIO):
    def write(self, s: AnyStr) -> int:
        assert isinstance(s, str)
        if stripped_s := s.strip():
            logger.debug(stripped_s)
        return len(s)

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False


def _setup_loguru(logger_level: str) -> None:
    logger.remove()

    if sys.stderr:
        logger.add(sys.stderr, level=logger_level)

    if os.name == "nt":
        cache_dir = Path(os.environ["LOCALAPPDATA"]) / "labelme"
    else:
        cache_dir = Path("~/.cache/labelme").expanduser()

    cache_dir.mkdir(parents=True, exist_ok=True)

    log_file = cache_dir / "labelme.log"
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


def _route_qt_logging_to_loguru() -> None:
    # Qt logs through its own handler straight to the C stderr, bypassing loguru
    # and the log file. Route it through loguru instead, dropping two harmless
    # noise sources so genuine Qt warnings still surface. The macOS keymapper
    # flood ("Mismatch between Cocoa and Carbon", one line per keypress) is
    # dropped by category, since qt.qpa.keymapper carries only low-value keyboard
    # diagnostics. The font-alias timing chatter is dropped by message text
    # within its category, since qt.qpa.fonts also reports real font-loading
    # failures worth keeping.
    LEVELS: Final = {
        QtCore.QtMsgType.QtDebugMsg: "DEBUG",
        QtCore.QtMsgType.QtInfoMsg: "INFO",
        QtCore.QtMsgType.QtWarningMsg: "WARNING",
        QtCore.QtMsgType.QtCriticalMsg: "ERROR",
        QtCore.QtMsgType.QtFatalMsg: "CRITICAL",
    }

    def handler(
        mode: QtCore.QtMsgType, context: QtCore.QMessageLogContext, message: str
    ) -> None:
        if context.category == "qt.qpa.keymapper":
            return
        if (
            context.category == "qt.qpa.fonts"
            and "Populating font family alias" in message
        ):
            return
        if context.category != "default":
            # Keep the category prefix Qt's default handler would have printed.
            message = f"{context.category}: {message}"
        logger.log(LEVELS.get(mode, "INFO"), message)
        if mode == QtCore.QtMsgType.QtFatalMsg:
            # Qt calls abort() as soon as this handler returns, which skips the
            # atexit drain of the enqueue=True file sink; flush it now so the
            # line explaining the crash reaches the log file.
            logger.complete()

    QtCore.qInstallMessageHandler(handler)


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


class _DeprecatedAlias(argparse.Action):
    """Store the value, but FutureWarning when a deprecated alias spelling is used.

    The canonical option string is the first one registered; any other spelling
    argparse matched (including abbreviations) warns and points back to it.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        canonical = self.option_strings[0]
        if option_string is not None and option_string != canonical:
            warnings.warn(
                f"{option_string} is deprecated and will be removed in a future "
                f"version. Use {canonical} instead.",
                FutureWarning,
                stacklevel=1,
            )
        setattr(namespace, self.dest, self.const if self.nargs == 0 else values)


def _parse_list_arg(value: str) -> list[str]:
    if os.path.isfile(value):
        with open(value, encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return [line.strip() for line in value.split(",") if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", "-V", action="store_true", help="show version")
    parser.add_argument(
        "--reset-config",
        action="store_true",
        help="reset window geometry and dock layout",
    )
    parser.add_argument(
        "--logger-level",
        default="debug",
        choices=_LOGGER_LEVELS,
        help="logger level",
    )
    parser.add_argument("path", nargs="?", help="image file, label file, or directory")
    parser.add_argument(
        "--output",
        help="output directory for saving annotation JSON files",
    )
    default_config_file = _config.get_user_config_file()
    parser.add_argument(
        "--config",
        dest="config",
        help=f"config file or yaml-format string (default: {default_config_file})",
        default=default_config_file,
    )
    # config for the gui
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
        "--no-sort-labels",
        "--nosortlabels",  # deprecated
        dest="sort_labels",
        action=_DeprecatedAlias,
        nargs=0,
        const=False,
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
        action=_DeprecatedAlias,
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
        action=_DeprecatedAlias,
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

    if args.version:
        print(f"{__appname__} {__version__}")
        sys.exit(0)

    _setup_loguru(logger_level=args.logger_level.upper())
    _route_qt_logging_to_loguru()
    logger.info("Starting {} {}", __appname__, __version__)

    sys.excepthook = _handle_exception

    if hasattr(args, "flags"):
        args.flags = _parse_list_arg(args.flags)

    if hasattr(args, "labels"):
        args.labels = _parse_list_arg(args.labels)

    if hasattr(args, "label_flags"):
        if os.path.isfile(args.label_flags):
            with open(args.label_flags, encoding="utf-8") as f:
                args.label_flags = _yaml.safe_load(f)
        else:
            args.label_flags = _yaml.safe_load(args.label_flags)

    config_from_args = args.__dict__
    config_from_args.pop("version")
    reset_config = config_from_args.pop("reset_config")
    file_or_dir = config_from_args.pop("path")
    output = config_from_args.pop("output")
    # logger_level configures loguru, not user config; excluding it keeps the
    # Settings dialog enabled (any override disables it).
    config_from_args.pop("logger_level")

    config_overrides: dict
    config_file: Path | None
    config_str: str = config_from_args.pop("config")
    if isinstance(config_loaded := _yaml.safe_load(config_str), dict):
        config_overrides = config_loaded
        config_file = None
    else:
        config_overrides = {}
        config_file = Path(config_str)
        if not os.path.isfile(config_str):
            logger.error(
                "Config file does not exist: {!r}", str(config_file.absolute())
            )
            sys.exit(1)
    del config_str
    config_overrides.update(config_from_args)

    output_dir = None
    if output is not None:
        if is_label_file_path(filename=output):
            parser.error(
                f"--output expects a directory path, but '{output}' looks like a file."
                " Remove the .json extension or provide a directory path."
            )
        output_dir = output

    # Read the language and color theme before QApplication exists so the
    # translator and palette are set before any widget is built. MainWindow
    # re-reads the same config; both reads are pure (load_config never writes), so
    # the duplicate parse is harmless.
    try:
        loaded_config = _config.load_config(
            config_file=config_file, config_overrides=config_overrides
        )
        language = loaded_config.get("language")
        color_theme = loaded_config.get("color_theme", "system")
    except Exception as e:
        logger.debug("Could not read config: {}", e)
        language = None
        color_theme = "system"
    # A stale or hand-edited language code with no bundled translation follows the
    # system locale, matching the Settings dialog.
    if not _locale.is_valid_language(language):
        language = None
    translator = QtCore.QTranslator()
    translator.load(
        language or QtCore.QLocale.system().name(),
        str(_locale.TRANSLATE_DIR),
    )
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")  # for consistent appearance across platforms
    apply_color_theme(theme=color_theme)
    app.setApplicationName(__appname__)
    app.setWindowIcon(new_icon("icon-256.png"))
    app.installTranslator(translator)
    win = MainWindow(
        config_file=config_file,
        config_overrides=config_overrides,
        file_or_dir=file_or_dir,
        output_dir=output_dir,
    )

    if reset_config:
        logger.info(f"Resetting window state: {win._window_state.fileName()}")
        win._window_state.clear()
        sys.exit(0)

    with contextlib.redirect_stderr(new_target=_LoggerIO()):
        win.show()
        win.raise_()
        sys.exit(app.exec())


# this main block is required to generate executable by pyinstaller
if __name__ == "__main__":
    main()
