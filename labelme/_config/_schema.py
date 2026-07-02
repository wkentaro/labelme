from __future__ import annotations

import dataclasses
import typing
from typing import Final
from typing import Literal
from typing import cast

from PySide6.QtCore import QT_TRANSLATE_NOOP

Section = Literal["General", "Labels"]
Kind = Literal["bool", "enum", "str_list", "language"]

# Section names double as tab titles. QT_TRANSLATE_NOOP marks them for pyside6-lupdate
# under the SettingsDialog context (where they are resolved via self.tr) without
# translating here; the labels below are marked the same way at their call site.
# The assert keeps the markers in sync with Section so a newly added section
# cannot silently lose its translation.
_TRANSLATABLE_SECTIONS: Final = (
    QT_TRANSLATE_NOOP("SettingsDialog", "General"),
    QT_TRANSLATE_NOOP("SettingsDialog", "Labels"),
)
assert set(_TRANSLATABLE_SECTIONS) == set(typing.get_args(Section))


@dataclasses.dataclass(frozen=True)
class Setting:
    key_path: tuple[str, ...]
    section: Section
    label: str
    kind: Kind
    # For "enum": the allowed values. A None entry is a real choice meaning
    # "unset/disabled"; it round-trips to YAML null and the dialog renders it
    # as an explicit "(none)" option, never as the string "None".
    choices: tuple[object, ...] | None = None
    # Display labels paralleling choices; falls back to str(choice) when None.
    choice_labels: tuple[str, ...] | None = None
    # Optional muted caption rendered beneath the control.
    note: str | None = None
    # Marks a feature shipped for early use: renders a "BETA" badge beside the
    # label so users expect rough edges and report issues. Drop when it stabilizes.
    beta: bool = False


SETTINGS: Final[tuple[Setting, ...]] = (
    Setting(
        key_path=("color_theme",),
        section="General",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Color theme")),
        kind="enum",
        choices=("system", "light", "dark"),
        choice_labels=(
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "System")),
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Light")),
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Dark")),
        ),
    ),
    Setting(
        key_path=("display_label_popup",),
        section="General",
        label=cast(
            str, QT_TRANSLATE_NOOP("SettingsDialog", "Show label popup on new shape")
        ),
        kind="bool",
    ),
    Setting(
        key_path=("shape", "show_labels"),
        section="General",
        label=cast(
            str, QT_TRANSLATE_NOOP("SettingsDialog", "Show shape labels on canvas")
        ),
        kind="bool",
        beta=True,
    ),
    Setting(
        key_path=("canvas", "allow_out_of_bounds_points"),
        section="General",
        label=cast(
            str,
            QT_TRANSLATE_NOOP(
                "SettingsDialog", "Allow points outside the image boundary"
            ),
        ),
        kind="bool",
        note=cast(
            str,
            QT_TRANSLATE_NOOP(
                "SettingsDialog",
                "Let shape points extend beyond the image, e.g. for partially "
                "visible objects.",
            ),
        ),
        beta=True,
    ),
    Setting(
        key_path=("language",),
        section="General",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Language")),
        kind="language",
        note=cast(
            str, QT_TRANSLATE_NOOP("SettingsDialog", "Takes effect after restart.")
        ),
    ),
    Setting(
        key_path=("labels",),
        section="Labels",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Predefined labels")),
        kind="str_list",
    ),
    Setting(
        key_path=("flags",),
        section="Labels",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Predefined image flags")),
        kind="str_list",
    ),
    Setting(
        key_path=("validate_label",),
        section="Labels",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Label validation")),
        kind="enum",
        choices=(None, "exact"),
    ),
)
