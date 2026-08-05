from __future__ import annotations

from typing import cast

from loguru import logger


def _is_rgb(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(
            isinstance(channel, int)
            and not isinstance(channel, bool)
            and 0 <= channel <= 255
            for channel in value
        )
    )


def _validate_rgb(*, path: str, value: object) -> None:
    if not _is_rgb(value):
        raise ValueError(f"{path} must be a list of three integers from 0 to 255")


def validate_shape_color(*, config: object) -> None:
    if not isinstance(config, dict):
        raise ValueError("shape_color must be a mapping")
    config = cast(dict[str, object], config)
    if "mode" in config and config["mode"] not in ["auto", "uniform", "by_label"]:
        raise ValueError(
            "shape_color.mode must be one of 'auto', 'uniform', or 'by_label'"
        )
    if "auto" in config:
        auto = config["auto"]
        if auto is None:
            auto = {}
        if not isinstance(auto, dict):
            raise ValueError("shape_color.auto must be a mapping")
        auto = cast(dict[str, object], auto)
        if "shift" in auto:
            shift = auto["shift"]
            if not isinstance(shift, int) or isinstance(shift, bool):
                raise ValueError("shape_color.auto.shift must be an integer")
    if "uniform" in config:
        uniform = config["uniform"]
        if uniform is None:
            uniform = {}
        if not isinstance(uniform, dict):
            raise ValueError("shape_color.uniform must be a mapping")
        uniform = cast(dict[str, object], uniform)
        if "color" in uniform:
            _validate_rgb(path="shape_color.uniform.color", value=uniform["color"])
    if "by_label" in config:
        by_label = config["by_label"]
        if by_label is None:
            by_label = {}
        if not isinstance(by_label, dict):
            raise ValueError("shape_color.by_label must be a mapping")
        by_label = cast(dict[str, object], by_label)
        if "fallback" in by_label:
            _validate_rgb(
                path="shape_color.by_label.fallback", value=by_label["fallback"]
            )
        if "colors" in by_label and by_label["colors"] is not None:
            colors = by_label["colors"]
            if not isinstance(colors, dict):
                raise ValueError("shape_color.by_label.colors must be a mapping")
            for label, color in colors.items():
                if not isinstance(label, str) or not label:
                    raise ValueError(
                        "shape_color.by_label.colors keys must be non-empty strings"
                    )
                _validate_rgb(path=f"shape_color.by_label.colors.{label}", value=color)


def migrate_shape_color(*, config: dict) -> None:
    """Migrate legacy shape color keys in place."""
    legacy_siblings = {
        "default_shape_color",
        "shift_auto_shape_color",
        "label_colors",
    }
    raw_shape_color = config.get("shape_color")
    has_legacy_shape_color = "shape_color" in config and not isinstance(
        raw_shape_color, dict
    )
    has_legacy_sibling = any(key in config for key in legacy_siblings)
    if isinstance(raw_shape_color, dict):
        if has_legacy_sibling:
            raise ValueError(
                "New shape_color config cannot be combined with legacy color keys"
            )
        return
    if not has_legacy_shape_color and not has_legacy_sibling:
        return
    if raw_shape_color not in [None, "auto", "manual"]:
        raise ValueError(
            f"Unexpected value for config key 'shape_color': {raw_shape_color}"
        )

    logger.info("Migrating legacy shape color config to nested shape_color settings")
    shape_color: dict = {}
    if has_legacy_shape_color:
        shape_color["mode"] = {
            "auto": "auto",
            "manual": "by_label",
            None: "uniform",
        }[raw_shape_color]
    if "shift_auto_shape_color" in config:
        shape_color["auto"] = {"shift": config.pop("shift_auto_shape_color")}
    if "default_shape_color" in config:
        default_color = config.pop("default_shape_color")
        if default_color is None:
            default_color = [0, 255, 0]
        shape_color["uniform"] = {"color": default_color}
        shape_color.setdefault("by_label", {})["fallback"] = default_color
    if "label_colors" in config:
        shape_color.setdefault("by_label", {})["colors"] = config.pop("label_colors")
    config.pop("shape_color", None)
    config["shape_color"] = shape_color
