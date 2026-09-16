from __future__ import annotations

from pathlib import Path

from labelme import _config


def test_load_retired_release_keys(*, tmp_path: Path) -> None:
    config_file = tmp_path / "labelmerc"
    config_file.write_text("""\
instance_label_auto_increment: true
auto_save: false
shortcuts:
  edit_line_color: Ctrl+L
  edit_fill_color: Ctrl+Shift+L
  add_point: Ctrl+Shift+P
  add_point_to_edge: Ctrl+Shift+P
  edit_polygon: Ctrl+J
""")
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert config["auto_save"] is False
    assert config["shortcuts"]["edit_shape"] == "Ctrl+J"


def test_migrate_keeps_explicit_current_values(*, tmp_path: Path) -> None:
    config_file = tmp_path / "labelmerc"
    config_file.write_text("""\
store_data: true
with_image_data: false
keep_prev_brightness: true
keep_prev_brightness_contrast: false
""")
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert config["with_image_data"] is False
    assert config["keep_prev_brightness_contrast"] is False


def test_reset_to_default_does_not_revive_legacy_overrides(*, tmp_path: Path) -> None:
    config_file = tmp_path / "labelmerc"
    config_file.write_text(
        "store_data: true\nkeep_prev_brightness: true\n"
        "shortcuts:\n  edit_polygon: Ctrl+K\n"
    )
    _config.set_overrides(
        config_file=config_file,
        overrides=[
            (("with_image_data",), False),
            (("keep_prev_brightness_contrast",), False),
            (("shortcuts", "edit_shape"), "Ctrl+J"),
        ],
    )
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert config["with_image_data"] is False
    assert config["keep_prev_brightness_contrast"] is False
    assert config["shortcuts"]["edit_shape"] == "Ctrl+J"
    assert config_file.read_text() == ""
