from __future__ import annotations

import sys
import types
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from loguru import logger
from PySide6 import QtCore

from labelme.__main__ import _LOGGER_LEVELS
from labelme.__main__ import _LoggerIO
from labelme.__main__ import _parse_list_arg
from labelme.__main__ import _route_qt_logging_to_loguru
from labelme.__main__ import main


@pytest.mark.parametrize("flag", ["--nodata", "--autosave"])
def test_removed_flag_errors_as_unknown(
    flag: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["labelme", flag])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


@pytest.mark.parametrize("level", _LOGGER_LEVELS)
def test_logger_level_choice_is_a_valid_loguru_level(level: str) -> None:
    assert logger.level(level.upper()).name == level.upper()


def test_logger_level_rejects_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["labelme", "--logger-level", "fatal"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


@pytest.mark.parametrize("output", ["notes.json", "notes.JSON"])
def test_output_rejects_json_file_path_case_insensitively(
    output: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["labelme", "--output", output])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


@pytest.mark.parametrize(
    ("argv", "canonical"),
    [
        (["--nosortlabels"], "--no-sort-labels"),
        (["--nosort"], "--no-sort-labels"),  # argparse abbreviation
        (["--labelflags", "{}"], "--label-flags"),
        (["--validatelabel", "exact"], "--validate-label"),
    ],
)
def test_deprecated_alias_warns_pointing_to_canonical(
    argv: list[str], canonical: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["labelme", *argv, "--version"])
    with pytest.warns(FutureWarning, match=canonical):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0


@pytest.mark.parametrize(
    "argv",
    [
        ["--no-sort-labels"],
        ["--label-flags", "{}"],
        ["--validate-label", "exact"],
        ["--with-image-data"],
        ["--no-auto-save"],
    ],
)
def test_canonical_flag_does_not_warn(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["labelme", *argv, "--version"])
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("cat,dog,person", ["cat", "dog", "person"]),
        ("cat, dog, person", ["cat", "dog", "person"]),
        ("cat,,dog,", ["cat", "dog"]),
        ("cat, , dog", ["cat", "dog"]),
        ("cat", ["cat"]),
        ("", []),
    ],
)
def test_parse_list_arg_splits_comma_separated_value(
    value: str, expected: list[str]
) -> None:
    assert _parse_list_arg(value) == expected


def test_parse_list_arg_reads_and_strips_file_lines(tmp_path: Path) -> None:
    labels_file = tmp_path / "labels.txt"
    labels_file.write_text("  cat  \n\ndog\n  \nperson\n", encoding="utf-8")

    assert _parse_list_arg(str(labels_file)) == ["cat", "dog", "person"]


def test_parse_list_arg_splits_value_too_long_to_be_a_path() -> None:
    labels = [f"label{i}" for i in range(60)]
    value = ",".join(labels)

    assert _parse_list_arg(value) == labels


def test_logger_io_forwards_stripped_writes_to_debug() -> None:
    forwarded: list[tuple[str, str]] = []
    sink_id = logger.add(
        lambda m: forwarded.append((m.record["level"].name, m.record["message"])),
        level="DEBUG",
    )
    try:
        stream = _LoggerIO()
        assert stream.write("  qt noise  \n") == len("  qt noise  \n")
        assert stream.write("   \n") == len("   \n")
    finally:
        logger.remove(sink_id)

    assert forwarded == [("DEBUG", "qt noise")]


def test_logger_io_is_a_write_only_non_seekable_sink() -> None:
    stream = _LoggerIO()
    assert stream.writable() is True
    assert stream.readable() is False
    assert stream.seekable() is False
    assert stream.closed is False
    assert stream.flush() is None


def test_route_qt_logging_drops_noise_and_forwards_the_rest() -> None:
    _route_qt_logging_to_loguru()
    handler = cast(
        "Callable[[QtCore.QtMsgType, object, str], None]",
        QtCore.qInstallMessageHandler(None),
    )

    forwarded: list[tuple[str, str]] = []
    sink_id = logger.add(
        lambda m: forwarded.append((m.record["level"].name, m.record["message"])),
        level="DEBUG",
    )
    try:
        keymapper = types.SimpleNamespace(category="qt.qpa.keymapper")
        fonts = types.SimpleNamespace(category="qt.qpa.fonts")
        default = types.SimpleNamespace(category="default")

        handler(
            QtCore.QtMsgType.QtWarningMsg,
            keymapper,
            "Mismatch between Cocoa and Carbon",
        )
        handler(
            QtCore.QtMsgType.QtWarningMsg,
            fonts,
            "Populating font family aliases took 42 ms",
        )
        assert forwarded == []

        handler(
            QtCore.QtMsgType.QtWarningMsg, fonts, "Found no matching fonts for family"
        )
        handler(
            QtCore.QtMsgType.QtWarningMsg,
            default,
            "Populating font family alias mentioned outside qt.qpa.fonts",
        )
        handler(QtCore.QtMsgType.QtCriticalMsg, default, "genuine failure")
    finally:
        logger.remove(sink_id)

    assert forwarded == [
        ("WARNING", "qt.qpa.fonts: Found no matching fonts for family"),
        ("WARNING", "Populating font family alias mentioned outside qt.qpa.fonts"),
        ("ERROR", "genuine failure"),
    ]
