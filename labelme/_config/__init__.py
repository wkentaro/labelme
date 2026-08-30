from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Final
from typing import cast

from loguru import logger

from .. import _yaml
from ._shape_color import migrate_shape_color
from ._shape_color import validate_shape_color
from ._writer import set_overrides

__all__ = ["get_user_config_file", "load_config", "set_overrides"]

here = Path(__file__).resolve().parent

_MASK_POLYGONIZATION_DETAIL_MAX: Final = 100


def _update_dict(
    *,
    target_dict: dict[str, object],
    new_dict: dict[str, object],
    key_path: tuple[str, ...],
) -> None:
    for key, value in new_dict.items():
        item_path = (*key_path, key)
        _validate_config_item(key_path=item_path, value=value)
        if key not in target_dict:
            raise ValueError(f"Unexpected key in config: {key}")
        if not isinstance(target_dict[key], dict):
            target_dict[key] = value
            continue

        # target_dict[key] is a section, so the override must be a mapping.
        if value is None:
            # An empty section (e.g. a bare `shortcuts:`) keeps its defaults
            # instead of wiping the whole section.
            continue
        if not isinstance(value, dict):
            # A non-mapping override (e.g. `shortcuts: oops`) would wipe the
            # section with a scalar and crash the app downstream; surface it as
            # a config error instead.
            raise ValueError(
                f"Config section {key!r} must be a mapping, "
                f"but got {type(value).__name__}: {value!r}"
            )
        _update_dict(
            target_dict=cast(dict[str, object], target_dict[key]),
            new_dict=cast(dict[str, object], value),
            key_path=item_path,
        )


def _validate_config_item(*, key_path: tuple[str, ...], value: object) -> None:
    key = key_path[-1]
    if key_path == ("mask_polygonization", "detail") and (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= _MASK_POLYGONIZATION_DETAIL_MAX
    ):
        raise ValueError(
            "mask_polygonization.detail must be an integer between 0 and 100, "
            f"but got {value!r}"
        )
    if key == "validate_label" and value not in [None, "exact"]:
        raise ValueError(f"Unexpected value for config key 'validate_label': {value}")
    if key == "labels" and value is not None:
        if not isinstance(value, list):
            raise ValueError(
                f"Config key 'labels' must be a list, "
                f"but got {type(value).__name__}: {value!r}"
            )
        if len(value) != len(set(value)):
            raise ValueError(
                f"Duplicates are detected for config key 'labels': {value}"
            )


def _migrate_config_from_file(*, config_from_yaml: dict) -> None:
    migrate_shape_color(config=config_from_yaml)
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

    if "logger_level" in config_from_yaml:
        logger.info("Migrating old config: removing logger_level")
        del config_from_yaml["logger_level"]

    # A malformed section (e.g. `shortcuts: oops`) is left untouched here so the
    # merge in _update_dict reports it as a config error instead of crashing.
    shortcuts = config_from_yaml.get("shortcuts")
    if not isinstance(shortcuts, dict):
        shortcuts = {}
    if shortcuts.pop("add_point_to_edge", None):
        logger.info("Migrating old config: removing shortcuts.add_point_to_edge")

    ai = config_from_yaml.get("ai")
    if (
        isinstance(ai, dict)
        and isinstance(model_name := ai.get("default"), str)
        and (m := re.match(r"^SegmentAnything \((.*)\)$", model_name))
    ):
        model_name_new: str = f"Sam ({m.group(1)})"
        logger.info(
            "Migrating old config: ai.default={!r} -> ai.default={!r}",
            model_name,
            model_name_new,
        )
        ai["default"] = model_name_new

    # Migrate polygon shortcut keys to shape
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
    for old_key, new_key in _POLYGON_TO_SHAPE_RENAMES.items():
        if old_key not in shortcuts:
            continue
        old_value = shortcuts.pop(old_key)
        if new_key in shortcuts:
            logger.info(
                "Migrating old config: dropping shortcuts.{}={!r} superseded by "
                "shortcuts.{}={!r}",
                old_key,
                old_value,
                new_key,
                shortcuts[new_key],
            )
            continue
        logger.info(
            "Migrating old config: shortcuts.{} -> shortcuts.{}",
            old_key,
            new_key,
        )
        shortcuts[new_key] = old_value

    # A malformed canvas/crosshair section is left untouched so the merge in
    # _update_dict reports it as a config error instead of crashing.
    canvas = config_from_yaml.get("canvas")
    crosshair = canvas.get("crosshair") if isinstance(canvas, dict) else None
    if not isinstance(crosshair, dict):
        crosshair = {}
    ai_polygon = crosshair.pop("ai_polygon", None)
    ai_mask = crosshair.pop("ai_mask", None)
    if ai_polygon is not None or ai_mask is not None:
        logger.info(
            "Migrating old config: canvas.crosshair.ai_polygon={} or "
            "canvas.crosshair.ai_mask={} -> canvas.crosshair.ai_points_to_shape",
            ai_polygon,
            ai_mask,
        )
        if "ai_points_to_shape" not in crosshair:
            crosshair["ai_points_to_shape"] = bool(ai_polygon) or bool(ai_mask)


def get_user_config_file(*, create_if_missing: bool = True) -> str:
    user_config_path = Path("~/.labelmerc").expanduser()
    if not user_config_path.exists() and create_if_missing:
        try:
            user_config_path.touch()
        except Exception:
            logger.warning("Failed to save config: {!r}", str(user_config_path))
    return str(user_config_path)


def load_config(*, config_file: Path | None, config_overrides: dict) -> dict:
    config: dict
    with open(here / "default_config.yaml", encoding="utf-8") as f:
        config = _yaml.safe_load(f)

    if config_file is not None:
        with open(config_file, encoding="utf-8") as f:
            config_from_yaml = _yaml.safe_load(f)
        if isinstance(config_from_yaml, dict):
            _migrate_config_from_file(config_from_yaml=config_from_yaml)
            if "shape_color" in config_from_yaml:
                validate_shape_color(config=config_from_yaml["shape_color"])
            _update_dict(target_dict=config, new_dict=config_from_yaml, key_path=())

    config_overrides = copy.deepcopy(config_overrides)
    migrate_shape_color(config=config_overrides)
    if "shape_color" in config_overrides:
        validate_shape_color(config=config_overrides["shape_color"])
    _update_dict(target_dict=config, new_dict=config_overrides, key_path=())

    if not config["labels"] and config["validate_label"]:
        raise ValueError("labels must be specified when validate_label is enabled")
    validate_shape_color(config=config["shape_color"])

    return config
