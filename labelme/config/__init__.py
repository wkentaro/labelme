import os.path as osp
import re
import shutil
from pathlib import Path

import yaml
from loguru import logger

here = osp.dirname(osp.abspath(__file__))


def _update_dict(target_dict, new_dict, validate_item=None):
    for key, value in new_dict.items():
        if validate_item:
            validate_item(key, value)
        if key not in target_dict:
            raise ValueError(f"Unexpected key in config: {key}")
        if isinstance(target_dict[key], dict) and isinstance(value, dict):
            _update_dict(target_dict[key], value, validate_item=validate_item)
        else:
            target_dict[key] = value


def _validate_config_item(key, value):
    if key == "validate_label" and value not in [None, "exact"]:
        raise ValueError(f"Unexpected value for config key 'validate_label': {value}")
    if key == "shape_color" and value not in [None, "auto", "manual"]:
        raise ValueError(f"Unexpected value for config key 'shape_color': {value}")
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


def get_user_config_file(create_if_missing: bool = True) -> str:
    user_config_file: str = osp.join(osp.expanduser("~"), ".labelmerc")
    if not osp.exists(user_config_file) and create_if_missing:
        try:
            shutil.copy(osp.join(here, "default_config.yaml"), user_config_file)
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
