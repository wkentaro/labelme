from __future__ import annotations

import dataclasses
import typing
from typing import Final
from typing import Literal
from typing import cast

from PySide6.QtCore import QT_TRANSLATE_NOOP

from .._ai_models import AI_ASSIST_MODEL_OPTIONS

Group = Literal[
    "Appearance and language",
    "Files and saving",
    "Drawing and canvas",
    "Continue between images",
    "Label sources",
    "Label behavior",
    "AI assist",
]
Kind = Literal["bool", "enum", "str_list", "language"]

# Group names double as headings. QT_TRANSLATE_NOOP marks them for
# pyside6-lupdate under the SettingsDialog context (where they are resolved via
# self.tr) without translating here. The assert keeps the markers in sync with
# Group so a newly added group cannot silently lose its translation.
_TRANSLATABLE_GROUPS: Final = (
    QT_TRANSLATE_NOOP("SettingsDialog", "Appearance and language"),
    QT_TRANSLATE_NOOP("SettingsDialog", "Files and saving"),
    QT_TRANSLATE_NOOP("SettingsDialog", "Drawing and canvas"),
    QT_TRANSLATE_NOOP("SettingsDialog", "Continue between images"),
    QT_TRANSLATE_NOOP("SettingsDialog", "Label sources"),
    QT_TRANSLATE_NOOP("SettingsDialog", "Label behavior"),
    QT_TRANSLATE_NOOP("SettingsDialog", "AI assist"),
)
assert set(_TRANSLATABLE_GROUPS) == set(typing.get_args(Group))


@dataclasses.dataclass(frozen=True)
class Setting:
    key_path: tuple[str, ...]
    group: Group
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
        group="Appearance and language",
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
        key_path=("language",),
        group="Appearance and language",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Language")),
        kind="language",
        note=cast(
            str, QT_TRANSLATE_NOOP("SettingsDialog", "Takes effect after restart.")
        ),
    ),
    Setting(
        key_path=("auto_save",),
        group="Files and saving",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Save automatically")),
        kind="bool",
    ),
    Setting(
        key_path=("with_image_data",),
        group="Files and saving",
        label=cast(
            str, QT_TRANSLATE_NOOP("SettingsDialog", "Save image data in label file")
        ),
        kind="bool",
        note=cast(
            str,
            QT_TRANSLATE_NOOP(
                "SettingsDialog", "Embeds the image in the label JSON file."
            ),
        ),
    ),
    Setting(
        key_path=("display_label_popup",),
        group="Drawing and canvas",
        label=cast(
            str, QT_TRANSLATE_NOOP("SettingsDialog", "Show label popup on new shape")
        ),
        kind="bool",
    ),
    Setting(
        key_path=("keep_prev",),
        group="Continue between images",
        label=cast(
            str, QT_TRANSLATE_NOOP("SettingsDialog", "Keep previous annotation")
        ),
        kind="bool",
    ),
    Setting(
        key_path=("keep_prev_scale",),
        group="Continue between images",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Keep previous zoom")),
        kind="bool",
    ),
    Setting(
        key_path=("keep_prev_brightness_contrast",),
        group="Continue between images",
        label=cast(
            str,
            QT_TRANSLATE_NOOP("SettingsDialog", "Keep previous brightness/contrast"),
        ),
        kind="bool",
    ),
    Setting(
        key_path=("canvas", "fill_drawing"),
        group="Drawing and canvas",
        label=cast(
            str, QT_TRANSLATE_NOOP("SettingsDialog", "Fill polygon while drawing")
        ),
        kind="bool",
    ),
    Setting(
        key_path=("canvas", "allow_out_of_bounds_points"),
        group="Drawing and canvas",
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
        key_path=("shape", "show_labels"),
        group="Drawing and canvas",
        label=cast(
            str, QT_TRANSLATE_NOOP("SettingsDialog", "Show shape labels on canvas")
        ),
        kind="bool",
        beta=True,
    ),
    Setting(
        key_path=("labels",),
        group="Label sources",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Predefined labels")),
        kind="str_list",
    ),
    Setting(
        key_path=("flags",),
        group="Label sources",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Predefined image flags")),
        kind="str_list",
    ),
    Setting(
        key_path=("validate_label",),
        group="Label behavior",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Label validation")),
        kind="enum",
        choices=(None, "exact"),
    ),
    Setting(
        key_path=("sort_labels",),
        group="Label behavior",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Sort labels")),
        kind="bool",
        note=cast(
            str,
            QT_TRANSLATE_NOOP(
                "SettingsDialog",
                "Sort the label list alphabetically instead of keeping the "
                "provided order.",
            ),
        ),
    ),
    Setting(
        key_path=("show_label_text_field",),
        group="Label behavior",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Show label text field")),
        kind="bool",
    ),
    Setting(
        key_path=("label_completion",),
        group="Label behavior",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Label completion")),
        kind="enum",
        choices=("startswith", "contains"),
        choice_labels=(
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Starts with")),
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Contains")),
        ),
    ),
    Setting(
        # Choices are the models' display names, matching the format
        # AiAssistedAnnotationWidget itself stores in ai.default (see
        # _ai_assisted_annotation_widget.py, where the dock combobox looks up
        # its initial selection by display name, not model id).
        key_path=("ai", "default"),
        group="AI assist",
        label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Default model")),
        kind="enum",
        choices=tuple(option.display_name for option in AI_ASSIST_MODEL_OPTIONS),
        # pyside6-lupdate needs literal markers here. A schema test keeps these
        # translation declarations aligned with the shared non-Qt model list.
        choice_labels=(
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "EfficientSam (speed)")),
            cast(
                str,
                QT_TRANSLATE_NOOP("SettingsDialog", "EfficientSam (accuracy)"),
            ),
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Sam (speed)")),
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Sam (balanced)")),
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Sam (accuracy)")),
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Sam2 (speed)")),
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Sam2 (balanced)")),
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Sam2 (accuracy)")),
            cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Sam3")),
        ),
    ),
)
