from pathlib import Path

import pytest
import yaml

from labelme.config import _migrate_config_from_file
from labelme.config import get_user_config_file
from labelme.config import load_config


def test_get_user_config_file_creates_sparse(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = get_user_config_file()
    content = Path(config_file).read_text()
    assert content.startswith("# Labelme config file")
    parsed = yaml.safe_load(content)
    assert parsed is None


def test_get_user_config_file_does_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / ".labelmerc"
    config_path.write_text("auto_save: true\n")
    config_file = get_user_config_file()
    content = Path(config_file).read_text()
    assert content == "auto_save: true\n"


def test_get_user_config_file_skip_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = get_user_config_file(create_if_missing=False)
    assert not Path(config_file).exists()


@pytest.mark.parametrize("old_value", [True, False])
def test_migrate_store_data_to_with_image_data(tmp_path, old_value):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"store_data: {str(old_value).lower()}\n")
    config = load_config(config_file=config_file, config_overrides={})
    assert config["with_image_data"] is old_value
    assert "store_data" not in config


@pytest.mark.parametrize(
    "input_name, expected_name",
    [
        ("SegmentAnything (balanced)", "Sam (balanced)"),
        ("SegmentAnything (tiny)", "Sam (tiny)"),
        ("Sam (balanced)", "Sam (balanced)"),
        ("Sam (large)", "Sam (large)"),
        ("Sam2 (balanced)", "Sam2 (balanced)"),
    ],
)
def test_migrate_ai_model_name(input_name: str, expected_name: str) -> None:
    config: dict = {"ai": {"default": input_name}}
    _migrate_config_from_file(config)
    assert config["ai"]["default"] == expected_name


_POLYGON_TO_SHAPE_RENAMES = {
    "edit_polygon": "edit_shape",
    "delete_polygon": "delete_shape",
    "duplicate_polygon": "duplicate_shape",
    "copy_polygon": "copy_shape",
    "paste_polygon": "paste_shape",
    "show_all_polygons": "show_all_shapes",
    "hide_all_polygons": "hide_all_shapes",
    "toggle_all_polygons": "toggle_all_shapes",
}


@pytest.mark.parametrize(
    "old_key, new_key",
    list(_POLYGON_TO_SHAPE_RENAMES.items()),
    ids=list(_POLYGON_TO_SHAPE_RENAMES.keys()),
)
def test_migrate_polygon_shortcut_to_shape(old_key, new_key):
    config = {"shortcuts": {old_key: "Ctrl+X"}}
    _migrate_config_from_file(config)
    assert old_key not in config["shortcuts"]
    assert config["shortcuts"][new_key] == "Ctrl+X"


def test_migrate_polygon_shortcuts_no_shortcuts_key():
    config = {}
    _migrate_config_from_file(config)
    assert "shortcuts" not in config


def test_migrate_polygon_shortcut_skips_when_new_key_exists():
    config = {"shortcuts": {"edit_polygon": "Ctrl+X", "edit_shape": "Ctrl+Y"}}
    _migrate_config_from_file(config)
    assert config["shortcuts"]["edit_shape"] == "Ctrl+Y"
    assert "edit_polygon" in config["shortcuts"]


def test_unknown_config_key_warns_and_does_not_raise(tmp_path):
    """Unknown keys in .labelmerc should warn and be ignored, not crash."""
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("unknown_key: true\n")
    # Must not raise; labelme should open normally
    config = load_config(config_file=config_file, config_overrides={})
    assert "unknown_key" not in config


def test_unknown_config_key_does_not_affect_valid_keys(tmp_path):
    """Unknown keys should be silently skipped; valid keys still applied."""
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("unknown_key: 42\nauto_save: true\n")
    config = load_config(config_file=config_file, config_overrides={})
    assert config["auto_save"] is True
    assert "unknown_key" not in config


def test_invalid_value_for_known_key_still_raises(tmp_path):
    """Bad values for *known* keys should still raise ValueError."""
    config_file = tmp_path / ".labelmerc"
    config_file.write_text("validate_label: bad_value\n")
    with pytest.raises(ValueError, match="validate_label"):
        load_config(config_file=config_file, config_overrides={})
