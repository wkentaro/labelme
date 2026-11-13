from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING
from typing import Final
from typing import Literal
from typing import cast

from PySide6.QtCore import QT_TRANSLATE_NOOP

if TYPE_CHECKING:
    import osam


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
# The menu leads each tool with its fastest, balanced and most accurate model.
# Per new image on an Apple M-series CPU: EfficientSAM Tiny 0.3 s, SAM 2 Base+
# 0.6 s, SAM 3 3.7 s; for text, YOLO-World 0.2 s and SAM 3 4.3 s.
AI_MODEL_TIERS: Final[dict[str, str]] = {
    "efficientsam:10m": cast(str, QT_TRANSLATE_NOOP("_ModelMenuButton", "Fastest")),
    "sam2:latest": cast(str, QT_TRANSLATE_NOOP("_ModelMenuButton", "Balanced")),
    "sam3:latest": cast(str, QT_TRANSLATE_NOOP("_ModelMenuButton", "Most accurate")),
    "yoloworld:latest": cast(str, QT_TRANSLATE_NOOP("_ModelMenuButton", "Fastest")),
}
# What each model trades, shown when the pointer rests on it in the menu.
_ORIGINAL_SAM: Final = cast(
    str,
    QT_TRANSLATE_NOOP(
        "_ModelMenuButton", "The original SAM. SAM 2 is faster at every size."
    ),
)
AI_MODEL_TOOLTIPS: Final[dict[str, str]] = {
    "efficientsam:10m": cast(
        str,
        QT_TRANSLATE_NOOP(
            "_ModelMenuButton",
            "Fastest, with rough outlines. Runs well on any computer.",
        ),
    ),
    "efficientsam:latest": cast(
        str,
        QT_TRANSLATE_NOOP(
            "_ModelMenuButton",
            "Sharper outlines than Tiny, but slower than SAM 2 Base+.",
        ),
    ),
    "sam:100m": _ORIGINAL_SAM,
    "sam:300m": _ORIGINAL_SAM,
    "sam:latest": _ORIGINAL_SAM,
    "sam2:small": cast(
        str,
        QT_TRANSLATE_NOOP(
            "_ModelMenuButton", "A smaller download than Base+, a little less accurate."
        ),
    ),
    "sam2:latest": cast(
        str,
        QT_TRANSLATE_NOOP(
            "_ModelMenuButton", "Balanced speed and accuracy. Runs well on a CPU."
        ),
    ),
    "sam2:large": cast(
        str,
        QT_TRANSLATE_NOOP("_ModelMenuButton", "More accurate than Base+, but slower."),
    ),
    "sam3:latest": cast(
        str,
        QT_TRANSLATE_NOOP(
            "_ModelMenuButton",
            "Most accurate, but slower than SAM 2 Base+. Best with a GPU.",
        ),
    ),
    "yoloworld:latest": cast(
        str,
        QT_TRANSLATE_NOOP("_ModelMenuButton", "Fastest. Finds boxes, without masks."),
    ),
}
# The rest go under "More models…".
AI_ASSIST_FOLDED_MODELS: Final[frozenset[str]] = frozenset(
    option.model_name
    for option in AI_ASSIST_MODEL_OPTIONS
    if option.model_name not in AI_MODEL_TIERS
)


AI_TEXT_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("sam3:latest", "SAM 3"),
    ("yoloworld:latest", "YOLO-World"),
)
# Text models that return boxes without masks.
AI_TEXT_BOX_ONLY_MODELS: Final[frozenset[str]] = frozenset({"yoloworld:latest"})

# Bytes each model downloads before its first use, on the CPU; SAM3 downloads
# half that for a GPU.
AI_MODEL_DOWNLOAD_SIZES: Final[dict[str, int]] = {
    "efficientsam:10m": 41_365_489,
    "efficientsam:latest": 106_124_065,
    "sam:100m": 108_571_344,
    "sam:300m": 331_312_787,
    "sam:latest": 664_987_190,
    "sam2:small": 183_345_862,
    "sam2:latest": 326_727_239,
    "sam2:large": 909_984_581,
    "sam3:latest": 3_664_204_623,
    "yoloworld:latest": 672_850_840,
}


def find_ai_assist_model_option(*, model_name: str) -> _AiAssistModelOption | None:
    for option in AI_ASSIST_MODEL_OPTIONS:
        if option.model_name == model_name:
            return option
    return None


# The AI device setting; "auto" lets osam pick one.
Device = Literal["auto", "cpu"]


def osam_client(
    *,
    device: Device,
    in_process: bool = True,
    max_loaded_models: int | None = None,
    timeout: float | None = None,
    auto_pull: bool = True,
) -> osam.Client:
    # In this process for listing, pulling and removing, which load no model.
    import osam  # noqa: PLC0415 -- deferred: ~250ms off importing labelme._app

    return osam.Client(
        device=None if device == "auto" else device,
        in_process=in_process,
        max_loaded_models=max_loaded_models,
        timeout=timeout,
        auto_pull=auto_pull,
    )


def model_info(*, client: osam.Client, name: str) -> osam.types.ModelInfo:
    [info] = [info for info in client.list() if info.name == name]
    return info


def accepts_example_boxes(*, model_name: str) -> bool:
    # Such as SAM3; YOLO-World detects from text only.
    info = model_info(client=osam_client(device="auto"), name=model_name)
    return "example_boxes" in info.prompt_kinds
