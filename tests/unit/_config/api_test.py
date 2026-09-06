from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest

from labelme import _config


def _steer_home(*, monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    monkeypatch.setenv("HOME", str(home))
    # ntpath.expanduser ignores HOME, so without this the test would read and
    # write the real user profile on Windows.
    monkeypatch.setenv("USERPROFILE", str(home))


def test_get_user_config_file_creates_empty(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _steer_home(monkeypatch=monkeypatch, home=tmp_path)
    config_file = _config.get_user_config_file()
    assert Path(config_file).read_text() == ""


def test_get_user_config_file_does_not_overwrite(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _steer_home(monkeypatch=monkeypatch, home=tmp_path)
    config_path = tmp_path / ".labelmerc"
    config_path.write_text("auto_save: true\n")
    config_file = _config.get_user_config_file()
    content = Path(config_file).read_text()
    assert content == "auto_save: true\n"


def test_get_user_config_file_skip_creation(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _steer_home(monkeypatch=monkeypatch, home=tmp_path)
    config_file = _config.get_user_config_file(create_if_missing=False)
    assert not Path(config_file).exists()


@pytest.mark.parametrize("old_value", [True, False])
def test_migrate_store_data_to_with_image_data(
    *, tmp_path: Path, old_value: bool
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"store_data: {str(old_value).lower()}\n")
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert config["with_image_data"] is old_value
    assert "store_data" not in config


def test_migrate_removes_logger_level(*, tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("logger_level: info\n")
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert "logger_level" not in config


@pytest.mark.parametrize("language", [None, "en_US", "ja_JP", "xx_ZZ"])
@pytest.mark.parametrize("source", ["file", "override"])
def test_load_config_preserves_language(
    *, tmp_path: Path, language: str | None, source: str
) -> None:
    config_file = None
    overrides = {"language": language}
    if source == "file":
        config_file = tmp_path / "config.yaml"
        config_file.write_text(json.dumps(overrides))
        overrides = {}
    config = _config.load_config(config_file=config_file, config_overrides=overrides)
    assert config["language"] == language


@pytest.mark.parametrize("language", [True, 1, [], {}])
def test_load_config_rejects_non_string_language(*, language: object) -> None:
    with pytest.raises(ValueError, match="Config key 'language' must be str or null"):
        _config.load_config(config_file=None, config_overrides={"language": language})


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
def test_migrate_ai_model_name(*, input_name: str, expected_name: str) -> None:
    config: dict = {"ai": {"default": input_name}}
    _config._migrate_config_from_file(config_from_yaml=config)
    assert config["ai"]["default"] == expected_name


@pytest.mark.parametrize("model_name", [True, 42, ["Sam"]])
def test_migrate_tolerates_non_string_ai_default(*, model_name: object) -> None:
    config: dict = {"ai": {"default": model_name}}
    _config._migrate_config_from_file(config_from_yaml=config)
    assert config["ai"]["default"] == model_name


def test_load_config_rejects_ai_default_that_is_not_a_string(
    *,
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("labels:\n  - cat\n  - dog\nai:\n  default: true\n")
    with pytest.raises(ValueError, match="Config key 'ai.default' must be str"):
        _config.load_config(config_file=config_file, config_overrides={})


def test_load_config_keeps_settings_with_unknown_ai_default(*, tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("auto_save: false\nai:\n  default: Unknown Model\n")

    config = _config.load_config(config_file=config_file, config_overrides={})

    assert config["auto_save"] is False
    assert config["ai"]["default"] == "Unknown Model"


@pytest.mark.parametrize("value", [-1, 101, True, "80"])
def test_load_config_rejects_invalid_polygon_detail(
    *, tmp_path: Path, value: object
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"mask_polygonization:\n  detail: {json.dumps(value)}\n")

    with pytest.raises(
        ValueError, match=r"mask_polygonization\.detail.*(?:int|integer)"
    ):
        _config.load_config(config_file=config_file, config_overrides={})


@pytest.mark.parametrize(
    ("config_text", "key_name", "expected_type"),
    [
        ('auto_save: "false"\n', "auto_save", "bool"),
        ('epsilon: "10.0"\n', "epsilon", "float"),
        ("epsilon: true\n", "epsilon", "float"),
        ('canvas:\n  num_backups: "10"\n', "canvas.num_backups", "int"),
        ("file_search: true\n", "file_search", "str or null"),
    ],
)
def test_load_config_rejects_wrong_scalar_type(
    *, tmp_path: Path, config_text: str, key_name: str, expected_type: str
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_text)

    with pytest.raises(
        ValueError, match=f"Config key {key_name!r} must be {expected_type}"
    ):
        _config.load_config(config_file=config_file, config_overrides={})


@pytest.mark.parametrize("source", ["file", "override"])
def test_load_config_normalizes_integer_epsilon(*, tmp_path: Path, source: str) -> None:
    config_file = None
    config_overrides = {}
    if source == "file":
        config_file = tmp_path / "config.yaml"
        config_file.write_text("epsilon: 10\n")
    else:
        config_overrides = {"epsilon": 10}

    config = _config.load_config(
        config_file=config_file,
        config_overrides=config_overrides,
    )

    assert config["epsilon"] == 10.0
    assert isinstance(config["epsilon"], float)


@pytest.mark.parametrize(
    ("config_text", "key_name"),
    [
        ("label_completion: anywhere\n", "label_completion"),
        ("color_theme: sepia\n", "color_theme"),
        ("canvas:\n  double_click: save\n", "canvas.double_click"),
    ],
)
def test_load_config_rejects_invalid_enum(
    *, tmp_path: Path, config_text: str, key_name: str
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_text)

    with pytest.raises(
        ValueError, match=f"Unexpected value for config key {key_name!r}"
    ):
        _config.load_config(config_file=config_file, config_overrides={})


@pytest.mark.parametrize("num_backups", [-1, 0])
def test_load_config_rejects_invalid_canvas_backup_count(*, num_backups: int) -> None:
    with pytest.raises(ValueError, match="canvas.num_backups must be"):
        _config.load_config(
            config_file=None,
            config_overrides={"canvas": {"num_backups": num_backups}},
        )


def test_load_config_accepts_disabled_canvas_double_click() -> None:
    config = _config.load_config(
        config_file=None, config_overrides={"canvas": {"double_click": None}}
    )
    assert config["canvas"]["double_click"] is None


_POLYGON_TO_SHAPE_RENAMES: Final = {
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
def test_migrate_polygon_shortcut_to_shape(*, old_key: str, new_key: str) -> None:
    config = {"shortcuts": {old_key: "Ctrl+X"}}
    _config._migrate_config_from_file(config_from_yaml=config)
    assert old_key not in config["shortcuts"]
    assert config["shortcuts"][new_key] == "Ctrl+X"


def test_migrate_polygon_shortcuts_no_shortcuts_key() -> None:
    config = {}
    _config._migrate_config_from_file(config_from_yaml=config)
    assert "shortcuts" not in config


@pytest.mark.parametrize("section", ["shortcuts", "ai"])
def test_migrate_tolerates_empty_section(*, section: str) -> None:
    config = {section: None}
    _config._migrate_config_from_file(config_from_yaml=config)
    assert config[section] is None


@pytest.mark.parametrize(
    ("section", "probe"),
    [("shortcuts", ("save", "Ctrl+S")), ("ai", ("default", "Sam2 (balanced)"))],
    ids=["shortcuts", "ai"],
)
def test_load_config_empty_section_keeps_defaults(
    *, tmp_path: Path, section: str, probe: tuple[str, str]
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"{section}:\n")
    config = _config.load_config(config_file=config_file, config_overrides={})
    key, value = probe
    assert config[section][key] == value


@pytest.mark.parametrize("section", ["shortcuts", "ai"])
def test_migrate_leaves_malformed_section_for_merge_to_report(*, section: str) -> None:
    config = {section: "oops"}
    _config._migrate_config_from_file(config_from_yaml=config)
    assert config[section] == "oops"


@pytest.mark.parametrize("section", ["shortcuts", "ai"])
def test_load_config_malformed_section_raises(*, tmp_path: Path, section: str) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"{section}: oops\n")
    with pytest.raises(
        ValueError, match=f"Config section {section!r} must be a mapping"
    ):
        _config.load_config(config_file=config_file, config_overrides={})


@pytest.mark.parametrize(
    "old_key, new_key",
    list(_POLYGON_TO_SHAPE_RENAMES.items()),
    ids=list(_POLYGON_TO_SHAPE_RENAMES.keys()),
)
def test_migrate_polygon_shortcut_drops_old_key_when_new_key_exists(
    *, old_key: str, new_key: str
) -> None:
    config = {"shortcuts": {old_key: "Ctrl+X", new_key: "Ctrl+Y"}}
    _config._migrate_config_from_file(config_from_yaml=config)
    assert config["shortcuts"][new_key] == "Ctrl+Y"
    assert old_key not in config["shortcuts"]


def test_load_config_tolerates_both_polygon_and_shape_shortcuts(
    *,
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "shortcuts:\n"
        "  edit_polygon: Ctrl+X\n"
        "  edit_shape: Ctrl+Y\n"
        "  delete_polygon: Ctrl+Z\n"
    )
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert config["shortcuts"]["edit_shape"] == "Ctrl+Y"
    assert config["shortcuts"]["delete_shape"] == "Ctrl+Z"
    assert "edit_polygon" not in config["shortcuts"]
    assert "delete_polygon" not in config["shortcuts"]


def test_migrate_removes_add_point_to_edge_shortcut() -> None:
    config = {"shortcuts": {"add_point_to_edge": "Ctrl+X"}}
    _config._migrate_config_from_file(config_from_yaml=config)
    assert "add_point_to_edge" not in config["shortcuts"]


def test_load_config_tolerates_removed_add_point_to_edge_shortcut(
    *,
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("shortcuts:\n  add_point_to_edge: Ctrl+X\n")
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert "add_point_to_edge" not in config["shortcuts"]


@pytest.mark.parametrize(
    ("ai_polygon", "ai_mask", "expected"),
    [
        (True, False, True),
        (False, True, True),
        (True, True, True),
        (False, False, False),
    ],
    ids=["polygon", "mask", "both", "neither"],
)
def test_migrate_ai_crosshair_keys_to_ai_points_to_shape(
    *, ai_polygon: bool, ai_mask: bool, expected: bool
) -> None:
    config = {"canvas": {"crosshair": {"ai_polygon": ai_polygon, "ai_mask": ai_mask}}}
    _config._migrate_config_from_file(config_from_yaml=config)
    crosshair = config["canvas"]["crosshair"]
    assert "ai_polygon" not in crosshair
    assert "ai_mask" not in crosshair
    assert crosshair["ai_points_to_shape"] is expected


def test_migrate_ai_crosshair_keeps_explicit_ai_points_to_shape() -> None:
    config = {
        "canvas": {"crosshair": {"ai_polygon": True, "ai_points_to_shape": False}}
    }
    _config._migrate_config_from_file(config_from_yaml=config)
    crosshair = config["canvas"]["crosshair"]
    assert "ai_polygon" not in crosshair
    assert crosshair["ai_points_to_shape"] is False


def test_load_config_tolerates_legacy_ai_crosshair_keys(*, tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "canvas:\n  crosshair:\n    ai_polygon: true\n    ai_mask: false\n"
    )
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert config["canvas"]["crosshair"]["ai_points_to_shape"] is True


def test_migrate_leaves_malformed_crosshair_for_merge_to_report() -> None:
    config = {"canvas": {"crosshair": "oops"}}
    _config._migrate_config_from_file(config_from_yaml=config)
    assert config["canvas"]["crosshair"] == "oops"


def test_load_config_malformed_crosshair_raises(*, tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("canvas:\n  crosshair: oops\n")
    with pytest.raises(
        ValueError, match="Config section 'crosshair' must be a mapping"
    ):
        _config.load_config(config_file=config_file, config_overrides={})


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
    *, old_config: dict[str, bool], expected: dict[str, bool]
) -> None:
    config = old_config.copy()
    _config._migrate_config_from_file(config_from_yaml=config)
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
        ({"labels": "cat"}, "Config key 'labels' must be list or null"),
        ({"not_a_real_key": True}, "Unexpected key in config: not_a_real_key"),
        (
            {"shortcuts": {"not_a_real_shortcut": "Ctrl+Z"}},
            "Unexpected key in config: not_a_real_shortcut",
        ),
    ],
    ids=[
        "validate_label",
        "shape_color",
        "labels",
        "labels_not_a_list",
        "unknown_key",
        "unknown_key_nested",
    ],
)
def test_load_config_rejects_invalid_override(*, overrides: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _config.load_config(config_file=None, config_overrides=overrides)


@pytest.mark.parametrize("label", [None, False, 1, 1.0, [], {}])
def test_load_config_rejects_non_string_label(*, label: object) -> None:
    with pytest.raises(ValueError, match="Each label must be a string"):
        _config.load_config(
            config_file=None,
            config_overrides={"labels": ["cat", label]},
        )


@pytest.mark.parametrize("flag", [None, False, 1, 1.0, [], {}])
def test_load_config_rejects_non_string_flag(*, flag: object) -> None:
    with pytest.raises(ValueError, match="Each flag must be a string"):
        _config.load_config(
            config_file=None,
            config_overrides={"flags": ["occluded", flag]},
        )


@pytest.mark.parametrize(
    "label_flags",
    [
        {1: ["occluded"]},
        {"cat": "occluded"},
        {"cat": ["occluded", 1]},
    ],
)
def test_load_config_rejects_malformed_label_flags(*, label_flags: dict) -> None:
    with pytest.raises(ValueError, match="label_flags must map"):
        _config.load_config(
            config_file=None,
            config_overrides={"label_flags": label_flags},
        )


@pytest.mark.parametrize(
    "color",
    [[0, 0, 0], [0, 0, 0, 256], [0, 0, 0, True], "black"],
)
def test_load_config_rejects_invalid_shape_rgba(*, color: object) -> None:
    with pytest.raises(ValueError, match="shape.line_color.*list"):
        _config.load_config(
            config_file=None,
            config_overrides={"shape": {"line_color": color}},
        )


@pytest.mark.parametrize(
    ("config_text", "labels"),
    [
        ("labels: null\n", None),
        ("labels: []\n", []),
        ('labels: [""]\n', [""]),
    ],
)
def test_load_config_accepts_compatible_labels(
    *, tmp_path: Path, config_text: str, labels: list[str] | None
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_text)
    config = _config.load_config(
        config_file=config_file,
        config_overrides={},
    )
    assert config["labels"] == labels


def test_load_config_requires_labels_when_validate_label_enabled() -> None:
    with pytest.raises(
        ValueError, match="labels must be specified when validate_label is enabled"
    ):
        _config.load_config(
            config_file=None, config_overrides={"validate_label": "exact"}
        )


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        (
            {"shape_color": "auto", "shift_auto_shape_color": -2},
            {
                "mode": "auto",
                "auto": {"shift": -2},
                "uniform": {"color": [0, 255, 0]},
                "by_label": {"colors": None, "fallback": [0, 255, 0]},
            },
        ),
        (
            {
                "shape_color": None,
                "default_shape_color": [215, 60, 233],
            },
            {
                "mode": "uniform",
                "auto": {"shift": 0},
                "uniform": {"color": [215, 60, 233]},
                "by_label": {"colors": None, "fallback": [215, 60, 233]},
            },
        ),
        (
            {
                "shape_color": "manual",
                "default_shape_color": [215, 60, 233],
                "label_colors": {"cat": [255, 0, 0]},
            },
            {
                "mode": "by_label",
                "auto": {"shift": 0},
                "uniform": {"color": [215, 60, 233]},
                "by_label": {
                    "colors": {"cat": [255, 0, 0]},
                    "fallback": [215, 60, 233],
                },
            },
        ),
    ],
    ids=["auto", "uniform", "by-label"],
)
def test_load_config_migrates_legacy_shape_color_from_file(
    *, tmp_path: Path, legacy: dict, expected: dict
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(json.dumps(legacy))

    config = _config.load_config(config_file=config_file, config_overrides={})

    assert config["shape_color"] == expected
    assert "default_shape_color" not in config
    assert "shift_auto_shape_color" not in config
    assert "label_colors" not in config


def test_load_config_migrates_legacy_shape_color_from_overrides() -> None:
    config = _config.load_config(
        config_file=None,
        config_overrides={
            "shape_color": "manual",
            "default_shape_color": [215, 60, 233],
            "label_colors": {"cat": [255, 0, 0]},
        },
    )

    assert config["shape_color"]["mode"] == "by_label"
    assert config["shape_color"]["by_label"] == {
        "colors": {"cat": [255, 0, 0]},
        "fallback": [215, 60, 233],
    }


def test_load_config_migrates_legacy_shape_color_sibling_without_mode() -> None:
    config = _config.load_config(
        config_file=None,
        config_overrides={"default_shape_color": [215, 60, 233]},
    )

    assert config["shape_color"]["mode"] == "auto"
    assert config["shape_color"]["uniform"]["color"] == [215, 60, 233]


def test_load_config_rejects_invalid_migrated_legacy_shape_color(
    *,
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        json.dumps(
            {
                "shape_color": "manual",
                "shift_auto_shape_color": "invalid",
            }
        )
    )

    with pytest.raises(ValueError, match="shape_color.auto.shift"):
        _config.load_config(config_file=config_file, config_overrides={})


def test_load_config_rejects_falsey_invalid_legacy_default_shape_color(
    *,
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("shape_color: null\ndefault_shape_color: []\n")

    with pytest.raises(ValueError, match="shape_color.uniform.color"):
        _config.load_config(config_file=config_file, config_overrides={})


def test_load_config_native_empty_shape_color_section_keeps_defaults() -> None:
    config = _config.load_config(
        config_file=None,
        config_overrides={"shape_color": {"auto": None}},
    )

    assert config["shape_color"]["auto"] == {"shift": 0}


def test_load_config_validates_native_shape_color_over_legacy_file(
    *,
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("shape_color: manual\n")

    with pytest.raises(ValueError, match="shape_color.auto.shift"):
        _config.load_config(
            config_file=config_file,
            config_overrides={"shape_color": {"auto": {"shift": "invalid"}}},
        )


def test_legacy_shape_color_override_preserves_config_file_values(
    *,
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
shape_color:
  mode: uniform
  uniform:
    color: [1, 2, 3]
  by_label:
    colors:
      cat: [4, 5, 6]
    fallback: [7, 8, 9]
"""
    )

    config = _config.load_config(
        config_file=config_file,
        config_overrides={"shift_auto_shape_color": -2},
    )

    assert config["shape_color"] == {
        "mode": "uniform",
        "auto": {"shift": -2},
        "uniform": {"color": [1, 2, 3]},
        "by_label": {
            "colors": {"cat": [4, 5, 6]},
            "fallback": [7, 8, 9],
        },
    }


def test_load_config_rejects_mixed_new_and_legacy_shape_color() -> None:
    with pytest.raises(ValueError, match="cannot be combined"):
        _config.load_config(
            config_file=None,
            config_overrides={
                "shape_color": {"mode": "uniform"},
                "default_shape_color": [215, 60, 233],
            },
        )


@pytest.mark.parametrize(
    ("shape_color", "message"),
    [
        ({"mode": "random"}, "shape_color.mode"),
        ({"auto": {"shift": True}}, "shape_color.auto.shift"),
        ({"uniform": {"color": [256, 0, 0]}}, "shape_color.uniform.color"),
        (
            {"by_label": {"colors": {"cat": [0, 0]}}},
            "shape_color.by_label.colors.cat",
        ),
    ],
    ids=["mode", "shift", "uniform-rgb", "label-rgb"],
)
def test_load_config_rejects_invalid_shape_color(
    *, shape_color: dict, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _config.load_config(
            config_file=None,
            config_overrides={"shape_color": shape_color},
        )


@pytest.mark.parametrize(
    ("key", "saved", "override"),
    [
        ("language", "ja_JP", None),
        ("flags", ["occluded"], None),
        ("label_flags", {"cat": ["occluded"]}, None),
        ("label_flags", {"cat": ["occluded"]}, {"dog": ["hidden"]}),
    ],
)
def test_load_config_overrides_nullable_values_using_default_types(
    *, tmp_path: Path, key: str, saved: object, override: object
) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(json.dumps({key: saved, "canvas": {"num_backups": 12}}))
    config = _config.load_config(
        config_file=config_file,
        config_overrides={key: override, "canvas": {"double_click": None}},
    )
    assert config[key] == override
    assert config["canvas"]["num_backups"] == 12
    assert config["canvas"]["double_click"] is None
