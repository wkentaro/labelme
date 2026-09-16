from __future__ import annotations

import copy
from pathlib import Path
from typing import Final
from typing import cast

from loguru import logger

from .. import _yaml
from .._ai_models import AI_TEXT_MODEL_OPTIONS
from ._migration import migrate_config
from ._shape_color import migrate_shape_color
from ._shape_color import validate_shape_color
from ._writer import reset_config
from ._writer import set_overrides

__all__ = ["get_user_config_file", "load_config", "reset_config", "set_overrides"]

here = Path(__file__).resolve().parent


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
    MASK_POLYGONIZATION_DETAIL_MAX: Final = 100

    key = key_path[-1]
    if key_path == ("label_flags",) and value is not None:
        if not isinstance(value, dict) or any(
            not isinstance(pattern, str)
            or not isinstance(names, list)
            or any(not isinstance(name, str) for name in names)
            for pattern, names in value.items()
        ):
            raise ValueError("label_flags must map string patterns to lists of strings")
    if key_path == ("mask_polygonization", "detail") and (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= MASK_POLYGONIZATION_DETAIL_MAX
    ):
        raise ValueError(
            "mask_polygonization.detail must be an integer between 0 and 100, "
            f"but got {value!r}"
        )
    if (
        key_path == ("ai", "text_model")
        and value is not None
        and value not in (model_name for model_name, _ in AI_TEXT_MODEL_OPTIONS)
    ):
        raise ValueError(f"Unexpected AI Text Prompt model: {value!r}")
    if key == "validate_label" and value not in [None, "exact"]:
        raise ValueError(f"Unexpected value for config key 'validate_label': {value}")
    if key != "labels" or value is None:
        return
    if not isinstance(value, list):
        raise ValueError(
            f"Config key 'labels' must be a list, "
            f"but got {type(value).__name__}: {value!r}"
        )
    if len(value) != len(set(value)):
        raise ValueError(f"Duplicates are detected for config key 'labels': {value}")


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
            migrate_config(config_from_yaml=config_from_yaml)
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
