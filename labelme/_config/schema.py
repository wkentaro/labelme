from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from typing import Literal

Section = Literal["General", "Labels", "Canvas"]
Kind = Literal["bool", "enum", "str_list"]


@dataclass(frozen=True)
class Setting:
    key_path: tuple[str, ...]
    section: Section
    label: str
    kind: Kind
    # For "enum": the allowed values. A None entry is a real choice meaning
    # "unset/disabled"; it round-trips to YAML null and the dialog renders it
    # as an explicit "(none)" option, never as the string "None".
    choices: tuple[object, ...] | None = None


SETTINGS: Final[tuple[Setting, ...]] = (
    Setting(
        key_path=("auto_save",),
        section="General",
        label="Auto-save annotations",
        kind="bool",
    ),
    Setting(
        key_path=("display_label_popup",),
        section="General",
        label="Show label popup on new shape",
        kind="bool",
    ),
    Setting(
        key_path=("with_image_data",),
        section="General",
        label="Store image data in annotation file",
        kind="bool",
    ),
    Setting(
        key_path=("labels",),
        section="Labels",
        label="Predefined labels",
        kind="str_list",
    ),
    Setting(
        key_path=("flags",),
        section="Labels",
        label="Predefined image flags",
        kind="str_list",
    ),
    Setting(
        key_path=("validate_label",),
        section="Labels",
        label="Label validation",
        kind="enum",
        choices=(None, "exact"),
    ),
    Setting(
        key_path=("canvas", "fill_drawing"),
        section="Canvas",
        label="Fill shape while drawing",
        kind="bool",
    ),
)
