from __future__ import annotations

import os.path as osp
import re
from collections.abc import Callable
from collections.abc import Sized
from pathlib import Path
from typing import cast

import yaml
from loguru import logger

here = osp.dirname(osp.abspath(__file__))


def _update_dict(
    target_dict: dict[str, object],
    new_dict: dict[str, object],
    validate_item: Callable[[str, object], None] | None = None,
) -> None:
    for key, value in new_dict.items():
        if validate_item:
            validate_item(key, value)
        if key not in target_dict:
            raise ValueError(f"Unexpected key in config: {key}")
        if isinstance(target_dict[key], dict) and isinstance(value, dict):
            _update_dict(
                cast(dict[str, object], target_dict[key]),
                cast(dict[str, object], value),
                validate_item=validate_item,
            )
        else:
            target_dict[key] = value


def _validate_config_item(key: str, value: object) -> None:
    if key == "validate_label" and value not in [None, "exact"]:
        raise ValueError(f"Unexpected value for config key 'validate_label': {value}")
    if key == "shape_color" and value not in [None, "auto", "manual"]:
        raise ValueError(f"Unexpected value for config key 'shape_color': {value}")
    if key == "dark_mode" and value not in [True, False, None]:
        raise ValueError(f"Unexpected value for config key 'dark_mode': {value}")
    if key == "labels" and value is not None and len(value) != len(set(value)):
        raise ValueError(f"Duplicates are detected for config key 'labels': {value}")


def _migrate_config_from_file(config_from_yaml: dict) -> None:
    keep_prev_brightness: bool = config_from_yaml.pop("keep_prev_brightness", False)
    keep_prev_contrast: bool = config_from_yaml.pop("keep_prev_contrast", False)
    if keep_prev_brightness or keep_prev_contrast:
        logger.info(
            "Migrating old config: keep_prev_brightness={} or keep_prev_contrast={} "
            "-> keep_prev_brightness_contrast=True",
            keep_prev_brightness,
            keep_prev_contrast,
        )
        config_from_yaml["keep_prev_brightness_contrast"] = True

    if "store_data" in config_from_yaml:
        logger.info("Migrating old config: store_data -> with_image_data")
        config_from_yaml["with_image_data"] = config_from_yaml.pop("store_data")

    if config_from_yaml.get("shortcuts", {}).pop("add_point_to_edge", None):
        logger.info("Migrating old config: removing shortcuts.add_point_to_edge")

    if (model_name := config_from_yaml.get("ai", {}).get("default")) and (
        m := re.match(r"^SegmentAnything \((.*)\)$", model_name)
    ):
        model_name_new: str = f"Sam ({m.group(1)})"
        logger.info(
            "Migrating old config: ai.default={!r} -> ai.default={!r}",
            model_name,
            model_name_new,
        )
        config_from_yaml["ai"]["default"] = model_name_new

    # Migrate polygon shortcut keys to shape
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
    shortcuts = config_from_yaml.get("shortcuts", {})
    for old_key, new_key in _POLYGON_TO_SHAPE_RENAMES.items():
        if old_key in shortcuts and new_key not in shortcuts:
            logger.info(
                "Migrating old config: shortcuts.{} -> shortcuts.{}",
                old_key,
                new_key,
            )
            shortcuts[new_key] = shortcuts.pop(old_key)


def get_user_config_file(create_if_missing: bool = True) -> str:
    user_config_file: str = osp.join(osp.expanduser("~"), ".labelmerc")
    if not osp.exists(user_config_file) and create_if_missing:
        try:
            with open(user_config_file, "w") as f:
                f.write(
                    "# Labelme config file.\n"
                    "# Only add settings you want to override.\n"
                    "# For all available options and defaults, see:\n"
                    "#   https://github.com/wkentaro/labelme/blob/main/labelme/config/default_config.yaml\n"
                    "#\n"
                    "# Example:\n"
                    "# with_image_data: true\n"
                    "# auto_save: false\n"
                    "# labels: [cat, dog]\n"
                )
        except Exception:
            logger.warning("Failed to save config: {!r}", user_config_file)
    return user_config_file


def load_config(config_file: Path | None, config_overrides: dict) -> dict:
    config: dict
    with open(osp.join(here, "default_config.yaml")) as f:
        config = yaml.safe_load(f)

    if config_file is not None:
        with open(config_file) as f:
            config_from_yaml = yaml.safe_load(f)
        if isinstance(config_from_yaml, dict):
            _migrate_config_from_file(config_from_yaml=config_from_yaml)
            _update_dict(config, config_from_yaml, validate_item=_validate_config_item)

    _update_dict(config, config_overrides, validate_item=_validate_config_item)

    if not config["labels"] and config["validate_label"]:
        raise ValueError("labels must be specified when validate_label is enabled")

    return config
