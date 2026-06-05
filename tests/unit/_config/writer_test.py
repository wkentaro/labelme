from __future__ import annotations

from pathlib import Path

import pytest

from labelme import _config
from labelme import _yaml


def _parse(config_file: Path) -> dict | None:
    return _yaml.safe_load(config_file.read_text())


def test_creates_file_when_missing(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    _config.set_override(config_file=config_file, key_path=["auto_save"], value=False)

    assert _parse(config_file) == {"auto_save": False}


def test_preserves_comment_on_untouched_key(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("# my custom note\nauto_save: false\n")

    _config.set_override(
        config_file=config_file, key_path=["with_image_data"], value=True
    )

    content = config_file.read_text()
    assert "# my custom note" in content
    assert _parse(config_file) == {"auto_save": False, "with_image_data": True}


def test_prunes_key_when_value_equals_default(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("auto_save: false\nwith_image_data: true\n")

    # auto_save default is true, so setting it back to true removes the override
    _config.set_override(config_file=config_file, key_path=["auto_save"], value=True)

    assert _parse(config_file) == {"with_image_data": True}


def test_writes_nested_key(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    _config.set_override(
        config_file=config_file, key_path=["shape", "point_size"], value=12
    )

    content = config_file.read_text()
    assert "shape:" in content
    assert _parse(config_file) == {"shape": {"point_size": 12}}


def test_prunes_nested_key_and_empty_parent(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("shape:\n  point_size: 12\n")

    # point_size default is 8; reverting empties shape, which should be pruned too
    _config.set_override(
        config_file=config_file, key_path=["shape", "point_size"], value=8
    )

    assert _parse(config_file) is None


def test_keeps_sibling_when_pruning_nested_key(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("shape:\n  point_size: 12\n  line_color: [1, 2, 3, 4]\n")

    _config.set_override(
        config_file=config_file, key_path=["shape", "point_size"], value=8
    )

    assert _parse(config_file) == {"shape": {"line_color": [1, 2, 3, 4]}}


def test_toggle_then_revert_is_idempotent(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    _config.set_override(
        config_file=config_file, key_path=["shape", "point_size"], value=12
    )
    _config.set_override(
        config_file=config_file, key_path=["shape", "point_size"], value=8
    )

    assert _parse(config_file) is None


def test_writes_list_in_flow_style(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    _config.set_override(
        config_file=config_file,
        key_path=["default_shape_color"],
        value=[255, 0, 0],
    )

    assert "default_shape_color: [255, 0, 0]" in config_file.read_text()


def test_label_named_like_a_boolean_survives_round_trip(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    _config.set_override(
        config_file=config_file, key_path=["labels"], value=["yes", "no"]
    )

    config = _config.load_config(config_file=config_file, config_overrides={})
    assert config["labels"] == ["yes", "no"]


def test_empty_key_path_raises(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    with pytest.raises(ValueError, match="key_path must not be empty"):
        _config.set_override(config_file=config_file, key_path=[], value=1)


def test_unknown_key_raises(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    with pytest.raises(ValueError, match="Unknown config key"):
        _config.set_override(config_file=config_file, key_path=["nope"], value=1)


def test_raises_when_parent_key_is_not_a_mapping(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("shape: 42\n")

    with pytest.raises(ValueError, match="non-mapping"):
        _config.set_override(
            config_file=config_file, key_path=["shape", "point_size"], value=12
        )


def test_overwrites_when_top_level_is_not_a_mapping(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("- one\n- two\n")

    _config.set_override(config_file=config_file, key_path=["auto_save"], value=False)

    assert _parse(config_file) == {"auto_save": False}


def test_empties_file_when_last_override_pruned(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("auto_save: false\n")

    # reverting the only override to its default leaves nothing to persist
    _config.set_override(config_file=config_file, key_path=["auto_save"], value=True)

    assert config_file.read_text() == ""


def test_written_file_reloads_via_load_config(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    _config.set_override(config_file=config_file, key_path=["auto_save"], value=False)
    _config.set_override(
        config_file=config_file, key_path=["shape", "point_size"], value=12
    )

    config = _config.load_config(config_file=config_file, config_overrides={})

    assert config["auto_save"] is False
    assert config["shape"]["point_size"] == 12
    # an untouched key keeps its default
    assert config["with_image_data"] is False


def test_write_failure_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / ".labelmerc"

    def _fail(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("labelme._config._writer.os.replace", _fail)

    with pytest.raises(OSError, match="disk full"):
        _config.set_override(
            config_file=config_file, key_path=["auto_save"], value=False
        )

    assert not config_file.exists()
    assert list(tmp_path.iterdir()) == []
