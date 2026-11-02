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
    if (
        "keep_prev_brightness" in config_from_yaml
        or "keep_prev_contrast" in config_from_yaml
    ):
        keep_prev_brightness = config_from_yaml.pop("keep_prev_brightness", False)
        keep_prev_contrast = config_from_yaml.pop("keep_prev_contrast", False)
        keep_prev = bool(keep_prev_brightness or keep_prev_contrast)
        logger.info(
            "Migrating old config: keep_prev_brightness={} or keep_prev_contrast={} "
            "-> keep_prev_brightness_contrast={}",
            keep_prev_brightness,
            keep_prev_contrast,
            keep_prev,
        )
        config_from_yaml.setdefault("keep_prev_brightness_contrast", keep_prev)

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
    for key in (
        "add_point",
        "add_point_to_edge",
        "edit_line_color",
        "edit_fill_color",
        "fit_width",
    ):
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

    _SHORTCUT_RENAMES: Final = {
        "edit_polygon": "edit_shape",
        "delete_polygon": "delete_shape",
        "duplicate_polygon": "duplicate_shape",
        "copy_polygon": "copy_shape",
        "paste_polygon": "paste_shape",
        "show_all_polygons": "show_all_shapes",
        "hide_all_polygons": "hide_all_shapes",
        "toggle_all_polygons": "toggle_all_shapes",
        "create_ai_detect": "create_ai_find_all",
    }
    # AI-Points and AI-Box merged into AI-Segment, which takes the first
    # bound shortcut of the two.
    old_shortcut_keys = [
        key for key in ("create_ai_points", "create_ai_box") if key in shortcuts
    ]
    if old_shortcut_keys:
        logger.warning(
            "Deprecated config: shortcuts.{} -> shortcuts.create_ai_segment",
            "/".join(old_shortcut_keys),
        )
        old_shortcuts = [shortcuts.pop(key) for key in old_shortcut_keys]
        shortcuts.setdefault(
            "create_ai_segment",
            next((value for value in old_shortcuts if value), None),
        )

    for old_key, new_key in _SHORTCUT_RENAMES.items():
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
    if "ai_detect" in crosshair:
        logger.info(
            "Migrating old config: canvas.crosshair.ai_detect -> "
            "canvas.crosshair.ai_find_all"
        )
        ai_detect = crosshair.pop("ai_detect")
        crosshair.setdefault("ai_find_all", ai_detect)
    # AI-Points and AI-Box merged into AI-Segment; either one enabled the
    # crosshair. Older names for AI-Points (ai_polygon, ai_mask) count too.
    old_crosshair_keys = [
        key
        for key in ("ai_points_to_shape", "ai_box_to_shape", "ai_polygon", "ai_mask")
        if key in crosshair
    ]
    if old_crosshair_keys:
        logger.warning(
            "Deprecated config: canvas.crosshair.{} -> canvas.crosshair.ai_segment",
            "/".join(old_crosshair_keys),
        )
        old_values = [crosshair.pop(key) for key in old_crosshair_keys]
        crosshair.setdefault("ai_segment", any(old_values))
