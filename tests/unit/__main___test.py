from __future__ import annotations

import os
import sys
import types
import warnings
from collections.abc import Callable
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from loguru import logger
from PySide6 import QtCore

from labelme.__main__ import _LOGGER_LEVELS
from labelme.__main__ import _LoggerIO
from labelme.__main__ import _parse_list_arg
from labelme.__main__ import _resolve_config_source
from labelme.__main__ import _route_qt_logging_to_loguru
from labelme.__main__ import _setup_loguru
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


def test_resolve_config_source_falls_back_to_defaults_on_missing_default_file(
    tmp_path: Path,
) -> None:
    missing_default = tmp_path / "unwritable" / ".labelmerc"
    warnings_logged: list[str] = []
    sink_id = logger.add(
        lambda m: warnings_logged.append(m.record["message"]), level="WARNING"
    )
    try:
        resolved = _resolve_config_source(
            config_arg=None, default_config_file=str(missing_default)
        )
    finally:
        logger.remove(sink_id)

    assert resolved == (None, {})
    assert len(warnings_logged) == 1
    # The warning quotes the path with !r, which doubles the backslashes of a
    # Windows path.
    assert repr(str(missing_default)) in warnings_logged[0]


def test_resolve_config_source_reads_an_existing_default_file(tmp_path: Path) -> None:
    default_config_file = tmp_path / ".labelmerc"
    default_config_file.touch()

    assert _resolve_config_source(
        config_arg=None, default_config_file=str(default_config_file)
    ) == (default_config_file, {})


def test_resolve_config_source_exits_on_an_explicit_missing_file(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit) as exc:
        _resolve_config_source(
            config_arg=str(tmp_path / "typo.yaml"),
            default_config_file=str(tmp_path / ".labelmerc"),
        )

    assert exc.value.code == 1


def test_resolve_config_source_exits_on_a_value_too_long_to_be_a_path(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit) as exc:
        _resolve_config_source(
            config_arg="x" * 300, default_config_file=str(tmp_path / ".labelmerc")
        )

    assert exc.value.code == 1


def test_resolve_config_source_reads_an_explicit_file(tmp_path: Path) -> None:
    config_file = tmp_path / "custom.yaml"
    config_file.write_text("auto_save: true\n", encoding="utf-8")

    assert _resolve_config_source(
        config_arg=str(config_file), default_config_file=str(tmp_path / ".labelmerc")
    ) == (config_file, {})


def test_resolve_config_source_takes_a_yaml_string_as_overrides(tmp_path: Path) -> None:
    assert _resolve_config_source(
        config_arg="{auto_save: true}",
        default_config_file=str(tmp_path / ".labelmerc"),
    ) == (None, {"auto_save": True})


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


@pytest.fixture()
def remove_loguru_sinks() -> Iterator[None]:
    yield
    # _setup_loguru registers the captured stderr as a sink, so leaving it behind
    # would make every later log call write to a stream pytest has closed.
    logger.remove()


def test_setup_loguru_degrades_to_stderr_when_the_cache_dir_cannot_be_created(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    remove_loguru_sinks: None,
) -> None:
    def raise_permission_error(*args: object, **kwargs: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "mkdir", raise_permission_error)

    _setup_loguru(logger_level="INFO")

    err = capsys.readouterr().err
    assert "Failed to set up the log file" in err
    assert "PermissionError" in err


def test_setup_loguru_degrades_to_stderr_when_the_home_directory_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    remove_loguru_sinks: None,
) -> None:
    def raise_runtime_error(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(Path, "expanduser", raise_runtime_error)

    _setup_loguru(logger_level="INFO")

    err = capsys.readouterr().err
    assert "Failed to set up the log file" in err
    assert "RuntimeError: Could not determine home directory." in err


def test_setup_loguru_degrades_to_stderr_when_the_log_file_cannot_be_opened(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    remove_loguru_sinks: None,
) -> None:
    cache_dir = tmp_path / ".cache" / "labelme"
    cache_dir.mkdir(parents=True)
    (cache_dir / "labelme.log").mkdir()

    def expand_to_tmp_cache_dir(self: Path) -> Path:
        return cache_dir

    monkeypatch.setattr(os, "name", "posix")
    # Patched instead of steering HOME because ntpath.expanduser ignores HOME,
    # so on Windows the test would resolve the real profile.
    monkeypatch.setattr(Path, "expanduser", expand_to_tmp_cache_dir)

    _setup_loguru(logger_level="INFO")

    err = capsys.readouterr().err
    assert "Failed to set up the log file" in err
    assert repr(str(cache_dir / "labelme.log")) in err


def test_setup_loguru_degrades_to_stderr_without_localappdata(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    remove_loguru_sinks: None,
) -> None:
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    _setup_loguru(logger_level="INFO")

    err = capsys.readouterr().err
    assert "Failed to set up the log file" in err
    assert "KeyError: 'LOCALAPPDATA'" in err


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
