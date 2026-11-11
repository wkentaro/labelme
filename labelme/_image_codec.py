# MIT License
# Copyright (c) Kentaro Wada

from __future__ import annotations

import base64
import io
from typing import Final

import numpy as np
import PIL.ExifTags
import PIL.Image
import PIL.ImageOps
from numpy.typing import NDArray


def img_data_to_pil(*, img_data: bytes) -> PIL.Image.Image:
    return PIL.Image.open(io.BytesIO(img_data))


def img_data_to_arr(*, img_data: bytes) -> NDArray[np.uint8]:
    img_pil = img_data_to_pil(img_data=img_data)
    img_arr = np.array(img_pil)
    return img_arr


def img_b64_to_arr(*, img_b64: str | bytes) -> NDArray[np.uint8]:
    img_data = base64.b64decode(img_b64)
    img_arr = img_data_to_arr(img_data=img_data)
    return img_arr


def _img_pil_to_data(*, img_pil: PIL.Image.Image) -> bytes:
    f = io.BytesIO()
    img_pil.save(f, format="PNG")
    img_data = f.getvalue()
    return img_data


def img_arr_to_b64(*, img_arr: NDArray[np.uint8]) -> str:
    img_data = img_arr_to_data(img_arr=img_arr)
    img_b64 = base64.b64encode(img_data).decode("utf-8")
    return img_b64


def img_arr_to_data(*, img_arr: NDArray[np.uint8]) -> bytes:
    img_pil = PIL.Image.fromarray(img_arr)
    img_data = _img_pil_to_data(img_pil=img_pil)
    return img_data


def apply_exif_orientation(*, image: PIL.Image.Image) -> PIL.Image.Image:
    # Values of the EXIF Orientation tag, which encodes the transform needed to
    # display the stored pixels the right way up.
    EXIF_ORIENTATION_NORMAL: Final = 1
    EXIF_ORIENTATION_MIRROR_LEFT_TO_RIGHT: Final = 2
    EXIF_ORIENTATION_ROTATE_180: Final = 3
    EXIF_ORIENTATION_MIRROR_TOP_TO_BOTTOM: Final = 4
    EXIF_ORIENTATION_MIRROR_TOP_TO_LEFT: Final = 5
    EXIF_ORIENTATION_ROTATE_270: Final = 6
    EXIF_ORIENTATION_MIRROR_TOP_TO_RIGHT: Final = 7
    EXIF_ORIENTATION_ROTATE_90: Final = 8

    try:
        exif = image._getexif()  # ty: ignore[unresolved-attribute]
    except AttributeError:
        exif = None

    if exif is None:
        return image

    exif = {PIL.ExifTags.TAGS[k]: v for k, v in exif.items() if k in PIL.ExifTags.TAGS}

    orientation = exif.get("Orientation", None)

    if orientation == EXIF_ORIENTATION_NORMAL:
        return image
    elif orientation == EXIF_ORIENTATION_MIRROR_LEFT_TO_RIGHT:
        return PIL.ImageOps.mirror(image)
    elif orientation == EXIF_ORIENTATION_ROTATE_180:
        return image.transpose(PIL.Image.ROTATE_180)
    elif orientation == EXIF_ORIENTATION_MIRROR_TOP_TO_BOTTOM:
        return PIL.ImageOps.flip(image)
    elif orientation == EXIF_ORIENTATION_MIRROR_TOP_TO_LEFT:
        return PIL.ImageOps.mirror(image.transpose(PIL.Image.ROTATE_270))
    elif orientation == EXIF_ORIENTATION_ROTATE_270:
        return image.transpose(PIL.Image.ROTATE_270)
    elif orientation == EXIF_ORIENTATION_MIRROR_TOP_TO_RIGHT:
        return PIL.ImageOps.mirror(image.transpose(PIL.Image.ROTATE_90))
    elif orientation == EXIF_ORIENTATION_ROTATE_90:
        return image.transpose(PIL.Image.ROTATE_90)
    else:
        return image
