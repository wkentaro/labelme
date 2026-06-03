from __future__ import annotations

from dataclasses import dataclass
from typing import Final

SECTION_GENERAL: Final = "General"
SECTION_LABELS: Final = "Labels"
SECTION_CANVAS: Final = "Canvas"

SECTIONS: Final[tuple[str, ...]] = (SECTION_GENERAL, SECTION_LABELS, SECTION_CANVAS)

KINDS: Final[frozenset[str]] = frozenset({"bool", "enum", "str_list"})


@dataclass(frozen=True)
class Setting:
    key_path: tuple[str, ...]
    section: str
    label: str
    kind: str
    # For "enum": the allowed values. A None entry is a real choice meaning
    # "unset/disabled"; it round-trips to YAML null and the dialog renders it
    # as an explicit "(none)" option, never as the string "None".
    choices: tuple[object, ...] | None = None


SETTINGS: Final[tuple[Setting, ...]] = (
    Setting(
        key_path=("auto_save",),
        section=SECTION_GENERAL,
        label="Auto-save annotations",
        kind="bool",
    ),
    Setting(
        key_path=("display_label_popup",),
        section=SECTION_GENERAL,
        label="Show label popup on new shape",
        kind="bool",
    ),
    Setting(
        key_path=("with_image_data",),
        section=SECTION_GENERAL,
        label="Store image data in annotation file",
        kind="bool",
    ),
    Setting(
        key_path=("labels",),
        section=SECTION_LABELS,
        label="Predefined labels",
        kind="str_list",
    ),
    Setting(
        key_path=("flags",),
        section=SECTION_LABELS,
        label="Predefined image flags",
        kind="str_list",
    ),
    Setting(
        key_path=("validate_label",),
        section=SECTION_LABELS,
        label="Label validation",
        kind="enum",
        choices=(None, "exact"),
    ),
    Setting(
        key_path=("canvas", "fill_drawing"),
        section=SECTION_CANVAS,
        label="Fill shape while drawing",
        kind="bool",
    ),
)
