from __future__ import annotations

from pathlib import Path

import pytest

from labelme.config import load_config
from labelme.config import safe_load
from labelme.config import set_override


def _parse(config_file: Path) -> dict | None:
    return safe_load(config_file.read_text())


def test_creates_file_with_header_when_missing(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    set_override(config_file=config_file, key_path=["auto_save"], value=False)

    content = config_file.read_text()
    assert content.startswith("# Labelme config file")
    assert _parse(config_file) == {"auto_save": False}


def test_preserves_comment_on_untouched_key(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("# my custom note\nauto_save: false\n")

    set_override(config_file=config_file, key_path=["with_image_data"], value=True)

    content = config_file.read_text()
    assert "# my custom note" in content
    assert _parse(config_file) == {"auto_save": False, "with_image_data": True}


def test_prunes_key_when_value_equals_default(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("auto_save: false\nwith_image_data: true\n")

    # auto_save default is true, so setting it back to true removes the override
    set_override(config_file=config_file, key_path=["auto_save"], value=True)

    assert _parse(config_file) == {"with_image_data": True}


def test_writes_nested_key(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    set_override(config_file=config_file, key_path=["shape", "point_size"], value=12)

    content = config_file.read_text()
    assert "shape:" in content
    assert _parse(config_file) == {"shape": {"point_size": 12}}


def test_prunes_nested_key_and_empty_parent(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("shape:\n  point_size: 12\n")

    # point_size default is 8; reverting empties shape, which should be pruned too
    set_override(config_file=config_file, key_path=["shape", "point_size"], value=8)

    assert _parse(config_file) is None


def test_keeps_sibling_when_pruning_nested_key(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("shape:\n  point_size: 12\n  line_color: [1, 2, 3, 4]\n")

    set_override(config_file=config_file, key_path=["shape", "point_size"], value=8)

    assert _parse(config_file) == {"shape": {"line_color": [1, 2, 3, 4]}}


def test_toggle_then_revert_is_idempotent(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    set_override(config_file=config_file, key_path=["shape", "point_size"], value=12)
    set_override(config_file=config_file, key_path=["shape", "point_size"], value=8)

    assert _parse(config_file) is None


def test_writes_list_in_flow_style(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    set_override(
        config_file=config_file,
        key_path=["default_shape_color"],
        value=[255, 0, 0],
    )

    assert "default_shape_color: [255, 0, 0]" in config_file.read_text()


def test_unknown_key_raises(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    with pytest.raises(ValueError, match="Unknown config key"):
        set_override(config_file=config_file, key_path=["nope"], value=1)


def test_raises_when_parent_key_is_not_a_mapping(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("shape: 42\n")

    with pytest.raises(ValueError, match="non-mapping"):
        set_override(
            config_file=config_file, key_path=["shape", "point_size"], value=12
        )


def test_reseeds_when_top_level_is_not_a_mapping(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("- one\n- two\n")

    set_override(config_file=config_file, key_path=["auto_save"], value=False)

    content = config_file.read_text()
    assert content.startswith("# Labelme config file")
    assert _parse(config_file) == {"auto_save": False}


def test_preserves_comment_only_file_when_no_override_remains(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("# my custom note\n")

    # auto_save default is true; this leaves no override, so the doc stays empty
    set_override(config_file=config_file, key_path=["auto_save"], value=True)

    assert "# my custom note" in config_file.read_text()
    assert _parse(config_file) is None


def test_preserves_leading_comment_when_last_key_pruned(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("# top comment\nauto_save: false\n")

    # reverting the only override to its default empties the mapping
    set_override(config_file=config_file, key_path=["auto_save"], value=True)

    assert "# top comment" in config_file.read_text()
    assert _parse(config_file) is None


def test_written_file_reloads_via_load_config(tmp_path: Path) -> None:
    config_file = tmp_path / ".labelmerc"

    set_override(config_file=config_file, key_path=["auto_save"], value=False)
    set_override(config_file=config_file, key_path=["shape", "point_size"], value=12)

    config = load_config(config_file=config_file, config_overrides={})

    assert config["auto_save"] is False
    assert config["shape"]["point_size"] == 12
    # an untouched key keeps its default
    assert config["with_image_data"] is False
