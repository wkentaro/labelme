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
        display_name="EfficientSAM Tiny",
    ),
    _AiAssistModelOption(
        model_name="efficientsam:latest",
        display_name="EfficientSAM Small",
    ),
    _AiAssistModelOption(
        model_name="sam:100m",
        display_name="SAM Base",
    ),
    _AiAssistModelOption(
        model_name="sam:300m",
        display_name="SAM Large",
    ),
    _AiAssistModelOption(
        model_name="sam:latest",
        display_name="SAM Huge",
    ),
    _AiAssistModelOption(
        model_name="sam2:small",
        display_name="SAM 2 Small",
    ),
    _AiAssistModelOption(
        model_name="sam2:latest",
        display_name="SAM 2 Base+",
    ),
    _AiAssistModelOption(
        model_name="sam2:large",
        display_name="SAM 2 Large",
    ),
    _AiAssistModelOption(
        model_name="sam3:latest",
        display_name="SAM 3",
    ),
)


AI_TEXT_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("sam3:latest", "SAM 3"),
    ("yoloworld:latest", "YOLO-World"),
)
# Text models that return boxes without masks.
AI_TEXT_BOX_ONLY_MODELS: Final[frozenset[str]] = frozenset({"yoloworld:latest"})


def find_ai_assist_model_option(*, model_name: str) -> _AiAssistModelOption | None:
    for option in AI_ASSIST_MODEL_OPTIONS:
        if option.model_name == model_name:
            return option
    return None


def accepts_example_boxes(*, model_name: str) -> bool:
    # YOLO-World detects from text only; SAM3 also takes example boxes.
    return model_name.startswith("sam3:")
