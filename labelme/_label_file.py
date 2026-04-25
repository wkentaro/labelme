from __future__ import annotations

import base64
import io
import json
import os.path as osp
import time
from pathlib import PureWindowsPath
from typing import Any
from typing import TypedDict

import numpy as np
import PIL.Image
import tifffile
from loguru import logger
from numpy.typing import NDArray

from labelme import __version__
from labelme import utils

PIL.Image.MAX_IMAGE_PIXELS = None


class ShapeDict(TypedDict):
    label: str
    points: list[list[float]]
    shape_type: str
    flags: dict[str, bool]
    description: str
    group_id: int | None
    mask: NDArray[np.bool_] | None
    other_data: dict


def _load_shape_json_obj(shape_json_obj: dict) -> ShapeDict:
    SHAPE_KEYS: set[str] = {
        "label",
        "points",
        "group_id",
        "shape_type",
        "flags",
        "description",
        "mask",
    }

    if "label" not in shape_json_obj:
        raise ValueError(f"label is required: {shape_json_obj}")
    if not isinstance(shape_json_obj["label"], str):
        raise TypeError(f"label must be str: {shape_json_obj['label']}")
    label: str = shape_json_obj["label"]

    if "points" not in shape_json_obj:
        raise ValueError(f"points is required: {shape_json_obj}")
    if not isinstance(shape_json_obj["points"], list):
        raise TypeError(f"points must be list: {shape_json_obj['points']}")
    if not shape_json_obj["points"]:
        raise ValueError(f"points must be non-empty: {shape_json_obj}")
    if not all(
        isinstance(point, list)
        and len(point) == 2
        and all(isinstance(xy, int | float) for xy in point)
        for point in shape_json_obj["points"]
    ):
        raise ValueError(f"points must be list of [x, y]: {shape_json_obj['points']}")
    points: list[list[float]] = shape_json_obj["points"]

    if "shape_type" not in shape_json_obj:
        raise ValueError(f"shape_type is required: {shape_json_obj}")
    if not isinstance(shape_json_obj["shape_type"], str):
        raise TypeError(f"shape_type must be str: {shape_json_obj['shape_type']}")
    shape_type: str = shape_json_obj["shape_type"]

    flags: dict = {}
    if shape_json_obj.get("flags") is not None:
        if not isinstance(shape_json_obj["flags"], dict):
            raise TypeError(f"flags must be dict: {shape_json_obj['flags']}")
        if not all(
            isinstance(k, str) and isinstance(v, bool)
            for k, v in shape_json_obj["flags"].items()
        ):
            raise TypeError(
                f"flags must be dict of str to bool: {shape_json_obj['flags']}"
            )
        flags = shape_json_obj["flags"]

    description: str = ""
    if shape_json_obj.get("description") is not None:
        if not isinstance(shape_json_obj["description"], str):
            raise TypeError(f"description must be str: {shape_json_obj['description']}")
        description = shape_json_obj["description"]

    group_id: int | None = None
    if shape_json_obj.get("group_id") is not None:
        if not isinstance(shape_json_obj["group_id"], int):
            raise TypeError(f"group_id must be int: {shape_json_obj['group_id']}")
        group_id = shape_json_obj["group_id"]

    mask: NDArray[np.bool_] | None = None
    if shape_json_obj.get("mask") is not None:
        if not isinstance(shape_json_obj["mask"], str):
            raise TypeError(
                f"mask must be base64-encoded PNG: {shape_json_obj['mask']}"
            )
        mask = utils.img_b64_to_arr(shape_json_obj["mask"]).astype(bool)

    other_data = {k: v for k, v in shape_json_obj.items() if k not in SHAPE_KEYS}

    loaded: ShapeDict = ShapeDict(
        label=label,
        points=points,
        shape_type=shape_type,
        flags=flags,
        description=description,
        group_id=group_id,
        mask=mask,
        other_data=other_data,
    )
    if set(loaded.keys()) != SHAPE_KEYS | {"other_data"}:
        raise RuntimeError(
            f"unexpected keys: {set(loaded.keys())} != {SHAPE_KEYS | {'other_data'}}"
        )
    return loaded


class LabelFileError(Exception):
    pass


class LabelFile:
    shapes: list[ShapeDict]
    suffix = ".json"

    def __init__(self, filename: str | None = None) -> None:
        self.shapes: list[ShapeDict] = []
        self.imagePath: str | None = None
        self.imageData: bytes | None = None
        if filename is not None:
            self.load(filename)
        self.filename: str | None = filename

    @staticmethod
    def load_image_file(filename: str) -> bytes:
        t0 = time.time()
        image_pil = _imread(filename=filename)

        oriented: PIL.Image.Image = utils.apply_exif_orientation(image_pil)
        ext = osp.splitext(filename)[1].lower()
        if oriented is image_pil and ext in (".jpg", ".jpeg", ".png"):
            # no encoding needed
            with open(filename, "rb") as f:
                imageData = f.read()
        else:
            with io.BytesIO() as f:
                format = "PNG" if "A" in oriented.mode else "JPEG"
                oriented.save(f, format=format, quality=95)
                f.seek(0)
                imageData = f.read()

        logger.debug(
            "Loaded image file: {!r} in {:.0f}ms", filename, (time.time() - t0) * 1000
        )
        return imageData

    def load(self, filename: str) -> None:
        keys = [
            "version",
            "imageData",
            "imagePath",
            "shapes",  # polygonal annotations
            "flags",  # image level flags
            "imageHeight",
            "imageWidth",
        ]
        try:
            with open(filename, encoding="utf-8") as f:
                data = json.load(f)

            # Normalize Windows-style backslash paths to POSIX forward slashes
            imagePath = PureWindowsPath(data["imagePath"]).as_posix()

            if data["imageData"] is not None:
                imageData = base64.b64decode(data["imageData"])
            else:
                # relative path from label file to relative path from cwd
                imageData = self.load_image_file(
                    osp.join(osp.dirname(filename), imagePath)
                )
            flags = data.get("flags") or {}
            self._check_image_height_and_width(
                imageData,
                data.get("imageHeight"),
                data.get("imageWidth"),
            )
            shapes: list[ShapeDict] = [
                _load_shape_json_obj(shape_json_obj=s) for s in data["shapes"]
            ]
        except Exception as e:
            raise LabelFileError(e)

        otherData = {}
        for key, value in data.items():
            if key not in keys:
                otherData[key] = value

        # Only replace data after everything is loaded.
        self.flags = flags
        self.shapes = shapes
        self.imagePath = imagePath
        self.imageData = imageData
        self.filename = filename
        self.otherData = otherData

    @staticmethod
    def _check_image_height_and_width(
        imageData: bytes, imageHeight: int | None, imageWidth: int | None
    ) -> tuple[int | None, int | None]:
        img_pil = utils.img_data_to_pil(imageData)
        actual_w, actual_h = img_pil.size
        if imageHeight is not None and actual_h != imageHeight:
            logger.error(
                "imageHeight does not match with imageData or imagePath, "
                "so getting imageHeight from actual image."
            )
            imageHeight = actual_h
        if imageWidth is not None and actual_w != imageWidth:
            logger.error(
                "imageWidth does not match with imageData or imagePath, "
                "so getting imageWidth from actual image."
            )
            imageWidth = actual_w
        return imageHeight, imageWidth

    def save(
        self,
        filename: str,
        shapes: list[dict[str, Any]],
        imagePath: str,
        imageHeight: int | None,
        imageWidth: int | None,
        imageData: bytes | None = None,
        otherData: dict[str, Any] | None = None,
        flags: dict[str, bool] | None = None,
    ) -> None:
        imageData_b64: str | None = None
        if imageData is not None:
            imageHeight, imageWidth = self._check_image_height_and_width(
                imageData, imageHeight, imageWidth
            )
            imageData_b64 = base64.b64encode(imageData).decode("utf-8")
        if otherData is None:
            otherData = {}
        if flags is None:
            flags = {}
        data = dict(
            version=__version__,
            flags=flags,
            shapes=shapes,
            imagePath=imagePath,
            imageData=imageData_b64,
            imageHeight=imageHeight,
            imageWidth=imageWidth,
        )
        for key, value in otherData.items():
            assert key not in data
            data[key] = value
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.filename = filename
        except Exception as e:
            raise LabelFileError(e)

    @staticmethod
    def is_label_file(filename: str) -> bool:
        return osp.splitext(filename)[1].lower() == LabelFile.suffix


_DISPLAYABLE_MODES = {"1", "L", "P", "RGB", "RGBA", "LA", "PA"}


def _imread(filename: str) -> PIL.Image.Image:
    ext: str = osp.splitext(filename)[1].lower()
    try:
        image_pil = PIL.Image.open(filename)
        if image_pil.mode not in _DISPLAYABLE_MODES:
            raise PIL.UnidentifiedImageError
        return image_pil
    except PIL.UnidentifiedImageError:
        if ext in (".tif", ".tiff"):
            return _imread_tiff(filename)
        raise


def _imread_tiff(filename: str) -> PIL.Image.Image:
    img_arr: NDArray = tifffile.imread(filename)

    if img_arr.ndim == 2:
        img_arr_normalized = _normalize_to_uint8(img_arr)
    elif img_arr.ndim == 3:
        if img_arr.shape[2] >= 3:
            img_arr_normalized = np.stack(
                [_normalize_to_uint8(img_arr[:, :, i]) for i in range(3)],
                axis=2,
            )
        else:
            img_arr_normalized = _normalize_to_uint8(img_arr[:, :, 0])
    else:
        raise OSError(f"Unsupported image shape: {img_arr.shape}")

    return PIL.Image.fromarray(img_arr_normalized)


def _normalize_to_uint8(arr: NDArray) -> NDArray[np.uint8]:
    arr = arr.astype(np.float64)
    min_val = np.nanmin(arr)
    max_val = np.nanmax(arr)
    if np.isnan(min_val) or np.isnan(max_val) or max_val - min_val == 0:
        return np.zeros(arr.shape, dtype=np.uint8)
    normalized = (arr - min_val) / (max_val - min_val) * 255
    return np.clip(normalized, 0, 255).astype(np.uint8)
