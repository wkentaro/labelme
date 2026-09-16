from __future__ import annotations

import re
from typing import Final

from loguru import logger

from ._shape_color import migrate_shape_color


def migrate_config(*, config_from_yaml: dict) -> None:
    migrate_shape_color(config=config_from_yaml)
    if "instance_label_auto_increment" in config_from_yaml:
        logger.info("Migrating old config: removing instance_label_auto_increment")
        del config_from_yaml["instance_label_auto_increment"]
    keep_prev_brightness: bool = config_from_yaml.pop("keep_prev_brightness", False)
    keep_prev_contrast: bool = config_from_yaml.pop("keep_prev_contrast", False)
    if keep_prev_brightness or keep_prev_contrast:
        logger.info(
            "Migrating old config: keep_prev_brightness={} or keep_prev_contrast={} "
            "-> keep_prev_brightness_contrast=True",
            keep_prev_brightness,
            keep_prev_contrast,
        )
        config_from_yaml.setdefault("keep_prev_brightness_contrast", True)

    if "store_data" in config_from_yaml:
        logger.info("Migrating old config: store_data -> with_image_data")
        config_from_yaml.setdefault(
            "with_image_data", config_from_yaml.pop("store_data")
        )

    if "logger_level" in config_from_yaml:
        logger.info("Migrating old config: removing logger_level")
        del config_from_yaml["logger_level"]

    # Leave malformed sections for validation.
    shortcuts = config_from_yaml.get("shortcuts")
    if not isinstance(shortcuts, dict):
        shortcuts = {}
    # These actions were removed; neither their old nor renamed shortcuts apply.
    for key in ("add_point", "add_point_to_edge", "edit_line_color", "edit_fill_color"):
        if key in shortcuts:
            logger.info("Migrating old config: removing shortcuts.{}", key)
            del shortcuts[key]

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

    # Leave malformed sections for validation.
    canvas = config_from_yaml.get("canvas")
    crosshair = canvas.get("crosshair") if isinstance(canvas, dict) else None
    if not isinstance(crosshair, dict):
        crosshair = {}
    ai_polygon = crosshair.pop("ai_polygon", None)
    ai_mask = crosshair.pop("ai_mask", None)
    if ai_polygon is None and ai_mask is None:
        return
    logger.info(
        "Migrating old config: canvas.crosshair.ai_polygon={} or "
        "canvas.crosshair.ai_mask={} -> canvas.crosshair.ai_points_to_shape",
        ai_polygon,
        ai_mask,
    )
    if "ai_points_to_shape" not in crosshair:
        crosshair["ai_points_to_shape"] = bool(ai_polygon) or bool(ai_mask)
