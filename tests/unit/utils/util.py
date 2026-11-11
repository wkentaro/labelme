from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from labelme import _image_codec

here = Path(__file__).parent
data_dir = here.parent.parent / "data"


def get_img_and_data() -> tuple[NDArray[np.uint8], dict[str, Any]]:
    json_file = data_dir / "annotated_with_data/apc2016_obj3.json"
    with open(json_file) as f:
        data = json.load(f)
    img_b64 = data["imageData"]
    img = _image_codec.img_b64_to_arr(img_b64=img_b64)
    return img, data
