import os.path as osp
import re
import shutil

import yaml
from loguru import logger

here = osp.dirname(osp.abspath(__file__))


def update_dict(target_dict, new_dict, validate_item=None):
    for key, value in new_dict.items():
        if validate_item:
            validate_item(key, value)
        if key not in target_dict:
            logger.warning(f"Skipping unexpected key in config: {key}")
            continue
        if isinstance(target_dict[key], dict) and isinstance(value, dict):
            update_dict(target_dict[key], value, validate_item=validate_item)
        else:
            target_dict[key] = value


# -----------------------------------------------------------------------------


def _get_default_config_and_create_labelmerc():
    config_file = osp.join(here, "default_config.yaml")
    with open(config_file) as f:
        config = yaml.safe_load(f)

    # save default config to ~/.labelmerc
    user_config_file = osp.join(osp.expanduser("~"), ".labelmerc")
    if not osp.exists(user_config_file):
        try:
            shutil.copy(config_file, user_config_file)
        except Exception:
            logger.warning(f"Failed to save config: {user_config_file}")

    return config


def validate_config_item(key, value):
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


def get_config(config_file_or_yaml=None, config_from_args=None):
    # 1. default config
    config = _get_default_config_and_create_labelmerc()

    # 2. specified as file or yaml
    if config_file_or_yaml is not None:
        config_from_yaml = yaml.safe_load(config_file_or_yaml)
        if not isinstance(config_from_yaml, dict):
            with open(config_from_yaml) as f:
                logger.info(f"Loading config file from: {config_from_yaml}")
                config_from_yaml = yaml.safe_load(f)
        _migrate_config_from_file(config_from_yaml=config_from_yaml)
        update_dict(config, config_from_yaml, validate_item=validate_config_item)

    # 3. command line argument or specified config file
    if config_from_args is not None:
        update_dict(config, config_from_args, validate_item=validate_config_item)

    return config
