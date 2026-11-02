from __future__ import annotations

from pathlib import Path

import pytest

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


def test_load_ai_detect_keys_as_ai_find_all(*, tmp_path: Path) -> None:
    config_file = tmp_path / "labelmerc"
    config_file.write_text("""\
canvas:
  crosshair:
    ai_detect: false
shortcuts:
  create_ai_detect: Ctrl+Shift+F
""")
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert config["canvas"]["crosshair"]["ai_find_all"] is False
    assert config["shortcuts"]["create_ai_find_all"] == "Ctrl+Shift+F"


@pytest.mark.parametrize(
    ("points", "box", "expected"),
    [(False, True, True), (True, False, True), (False, False, False)],
)
def test_load_ai_points_and_ai_box_keys_as_ai_segment(
    *, tmp_path: Path, points: bool, box: bool, expected: bool
) -> None:
    config_file = tmp_path / "labelmerc"
    config_file.write_text(f"""\
canvas:
  crosshair:
    ai_points_to_shape: {str(points).lower()}
    ai_box_to_shape: {str(box).lower()}
shortcuts:
  create_ai_points:
  create_ai_box: Ctrl+B
""")
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert config["canvas"]["crosshair"]["ai_segment"] is expected
    assert "ai_points_to_shape" not in config["canvas"]["crosshair"]
    assert config["shortcuts"]["create_ai_segment"] == "Ctrl+B"
    assert "create_ai_box" not in config["shortcuts"]


def test_load_ai_points_and_ai_box_shortcuts_both_kept(*, tmp_path: Path) -> None:
    config_file = tmp_path / "labelmerc"
    config_file.write_text("""\
shortcuts:
  create_ai_points: [Ctrl+P, Ctrl+B]
  create_ai_box: Ctrl+B
""")
    config = _config.load_config(config_file=config_file, config_overrides={})
    assert config["shortcuts"]["create_ai_segment"] == ["Ctrl+P", "Ctrl+B"]
