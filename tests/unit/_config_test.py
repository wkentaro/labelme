from __future__ import annotations

from pathlib import Path

import pytest

from labelme import _config


def test_get_user_config_file_creates_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = _config.get_user_config_file()
    assert Path(config_file).read_text() == ""


def test_get_user_config_file_does_not_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_path = tmp_path / ".labelmerc"
    config_path.write_text("auto_save: true\n")
    config_file = _config.get_user_config_file()
    content = Path(config_file).read_text()
    assert content == "auto_save: true\n"


def test_get_user_config_file_skip_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = _config.get_user_config_file(create_if_missing=False)
    assert not Path(config_file).exists()


@pytest.mark.parametrize("old_value", [True, False])
def test_migrate_store_data_to_with_image_data(tmp_path: Path, old_value: bool) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"store_data: {str(old_value).lower()}\n")
    config = _config.load_config(config_file=config_file, config_overrides={})
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
    _config._migrate_config_from_file(config)
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
def test_migrate_polygon_shortcut_to_shape(old_key: str, new_key: str) -> None:
    config = {"shortcuts": {old_key: "Ctrl+X"}}
    _config._migrate_config_from_file(config)
    assert old_key not in config["shortcuts"]
    assert config["shortcuts"][new_key] == "Ctrl+X"


def test_migrate_polygon_shortcuts_no_shortcuts_key() -> None:
    config = {}
    _config._migrate_config_from_file(config)
    assert "shortcuts" not in config


def test_migrate_polygon_shortcut_skips_when_new_key_exists() -> None:
    config = {"shortcuts": {"edit_polygon": "Ctrl+X", "edit_shape": "Ctrl+Y"}}
    _config._migrate_config_from_file(config)
    assert config["shortcuts"]["edit_shape"] == "Ctrl+Y"
    assert "edit_polygon" in config["shortcuts"]


@pytest.mark.parametrize(
    ("old_config", "expected"),
    [
        ({"keep_prev_brightness": True}, {"keep_prev_brightness_contrast": True}),
        ({"keep_prev_contrast": True}, {"keep_prev_brightness_contrast": True}),
        (
            {"keep_prev_brightness": True, "keep_prev_contrast": True},
            {"keep_prev_brightness_contrast": True},
        ),
        ({"keep_prev_brightness": False, "keep_prev_contrast": False}, {}),
    ],
    ids=["brightness", "contrast", "both", "both_disabled"],
)
def test_migrate_keep_prev_brightness_contrast(
    old_config: dict[str, bool], expected: dict[str, bool]
) -> None:
    config = old_config.copy()
    _config._migrate_config_from_file(config)
    assert config == expected


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"validate_label": "none"},
            "Unexpected value for config key 'validate_label'",
        ),
        ({"shape_color": "random"}, "Unexpected value for config key 'shape_color'"),
        ({"labels": ["cat", "cat"]}, "Duplicates are detected for config key 'labels'"),
    ],
    ids=["validate_label", "shape_color", "labels"],
)
def test_load_config_rejects_invalid_override(overrides: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _config.load_config(config_file=None, config_overrides=overrides)


def test_load_config_requires_labels_when_validate_label_enabled() -> None:
    with pytest.raises(
        ValueError, match="labels must be specified when validate_label is enabled"
    ):
        _config.load_config(
            config_file=None, config_overrides={"validate_label": "exact"}
        )
