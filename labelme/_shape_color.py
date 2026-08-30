from __future__ import annotations

from typing import Final

import imgviz
import numpy as np
from numpy.typing import NDArray

_LABEL_COLORMAP: Final[NDArray[np.uint8]] = imgviz.label_colormap()


def resolve_shape_color(
    *, config: dict, label: str, label_index: int
) -> tuple[int, int, int]:
    mode = config["mode"]
    if mode == "auto":
        label_id = 1 + label_index + config["auto"]["shift"]
        r, g, b = _LABEL_COLORMAP[label_id % len(_LABEL_COLORMAP)].tolist()
        return r, g, b
    if mode == "uniform":
        r, g, b = config["uniform"]["color"]
        return r, g, b

    colors = config["by_label"]["colors"]
    rgb = colors.get(label) if colors else None
    if rgb is None:
        rgb = config["by_label"]["fallback"]
    r, g, b = rgb
    return r, g, b
