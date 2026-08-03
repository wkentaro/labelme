from __future__ import annotations

import dataclasses
from typing import Final


@dataclasses.dataclass(frozen=True)
class AiAssistModelOption:
    model_name: str
    display_name: str
    supports_point_prompts: bool


AI_ASSIST_MODEL_OPTIONS: Final[tuple[AiAssistModelOption, ...]] = (
    AiAssistModelOption(
        model_name="efficientsam:10m",
        display_name="EfficientSam (speed)",
        supports_point_prompts=True,
    ),
    AiAssistModelOption(
        model_name="efficientsam:latest",
        display_name="EfficientSam (accuracy)",
        supports_point_prompts=True,
    ),
    AiAssistModelOption(
        model_name="sam:100m",
        display_name="Sam (speed)",
        supports_point_prompts=True,
    ),
    AiAssistModelOption(
        model_name="sam:300m",
        display_name="Sam (balanced)",
        supports_point_prompts=True,
    ),
    AiAssistModelOption(
        model_name="sam:latest",
        display_name="Sam (accuracy)",
        supports_point_prompts=True,
    ),
    AiAssistModelOption(
        model_name="sam2:small",
        display_name="Sam2 (speed)",
        supports_point_prompts=True,
    ),
    AiAssistModelOption(
        model_name="sam2:latest",
        display_name="Sam2 (balanced)",
        supports_point_prompts=True,
    ),
    AiAssistModelOption(
        model_name="sam2:large",
        display_name="Sam2 (accuracy)",
        supports_point_prompts=True,
    ),
    AiAssistModelOption(
        model_name="sam3:latest",
        display_name="Sam3",
        supports_point_prompts=False,
    ),
)


def find_ai_assist_model_option(*, model_name: str) -> AiAssistModelOption | None:
    for option in AI_ASSIST_MODEL_OPTIONS:
        if option.model_name == model_name:
            return option
    return None


def supports_point_prompts(*, model_name: str) -> bool:
    option = find_ai_assist_model_option(model_name=model_name)
    return option is None or option.supports_point_prompts
