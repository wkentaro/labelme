import argparse
import codecs
import contextlib
import io
import os
import os.path as osp
import sys
import traceback

import yaml
from loguru import logger
from PyQt5 import QtCore
from PyQt5 import QtWidgets

from labelme import __appname__
from labelme import __version__
from labelme.app import MainWindow
from labelme.config import get_config
from labelme.utils import newIcon


class _LoggerIO(io.StringIO):
    def write(self, message: str) -> int:
        if stripped_message := message.strip():
            logger.debug(stripped_message)
        return len(message)

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


def _handle_exception(exc_type, exc_value, exc_traceback):
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", "-V", action="store_true", help="show version")
    parser.add_argument("--reset-config", action="store_true", help="reset qt config")
    parser.add_argument(
        "--logger-level",
        default="debug",
        choices=["debug", "info", "warning", "fatal", "error"],
        help="logger level",
    )
    parser.add_argument("filename", nargs="?", help="image or label filename")
    parser.add_argument(
        "--output",
        "-O",
        "-o",
        help="output file or directory (if it ends with .json it is "
        "recognized as file, else as directory)",
    )
    default_config_file = os.path.join(os.path.expanduser("~"), ".labelmerc")
    parser.add_argument(
        "--config",
        dest="config",
        help=f"config file or yaml-format string (default: {default_config_file})",
        default=default_config_file,
    )
    # config for the gui
    parser.add_argument(
        "--nodata",
        dest="store_data",
        action="store_false",
        help="stop storing image data to JSON file",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--autosave",
        dest="auto_save",
        action="store_true",
        help="auto save",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--nosortlabels",
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
        "--labelflags",
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
        "--validatelabel",
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
    filename = config_from_args.pop("filename")
    output = config_from_args.pop("output")
    config_file_or_yaml = config_from_args.pop("config")
    config = get_config(config_file_or_yaml, config_from_args)

    if not config["labels"] and config["validate_label"]:
        logger.error(
            "--labels must be specified with --validatelabel or "
            "validate_label: true in the config file "
            "(ex. ~/.labelmerc)."
        )
        sys.exit(1)

    output_file = None
    output_dir = None
    if output is not None:
        if output.endswith(".json"):
            output_file = output
        else:
            output_dir = output

    translator = QtCore.QTranslator()
    translator.load(
        QtCore.QLocale.system().name(),
        f"{osp.dirname(osp.abspath(__file__))}/translate",
    )
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(__appname__)
    app.setWindowIcon(newIcon("icon"))
    app.installTranslator(translator)
    win = MainWindow(
        config=config,
        filename=filename,
        output_file=output_file,
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
