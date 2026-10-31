from __future__ import annotations

import dataclasses
from typing import Final


@dataclasses.dataclass(frozen=True)
class _AiAssistModelOption:
    model_name: str
    display_name: str


AI_ASSIST_MODEL_OPTIONS: Final[tuple[_AiAssistModelOption, ...]] = (
    _AiAssistModelOption(
        model_name="efficientsam:10m",
        display_name="EfficientSam (speed)",
    ),
    _AiAssistModelOption(
        model_name="efficientsam:latest",
        display_name="EfficientSam (accuracy)",
    ),
    _AiAssistModelOption(
        model_name="sam:100m",
        display_name="Sam (speed)",
    ),
    _AiAssistModelOption(
        model_name="sam:300m",
        display_name="Sam (balanced)",
    ),
    _AiAssistModelOption(
        model_name="sam:latest",
        display_name="Sam (accuracy)",
    ),
    _AiAssistModelOption(
        model_name="sam2:small",
        display_name="Sam2 (speed)",
    ),
    _AiAssistModelOption(
        model_name="sam2:latest",
        display_name="Sam2 (balanced)",
    ),
    _AiAssistModelOption(
        model_name="sam2:large",
        display_name="Sam2 (accuracy)",
    ),
    _AiAssistModelOption(
        model_name="sam3:latest",
        display_name="Sam3",
    ),
)


AI_TEXT_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("sam3:latest", "SAM3 (smart)"),
    ("yoloworld:latest", "YOLO-World (fast)"),
)


def find_ai_assist_model_option(*, model_name: str) -> _AiAssistModelOption | None:
    for option in AI_ASSIST_MODEL_OPTIONS:
        if option.model_name == model_name:
            return option
    return None
