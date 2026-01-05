import base64
import builtins
import contextlib
import io
import json
import os.path as osp
from typing import Optional
from typing import TypedDict

import numpy as np
import PIL.Image
from loguru import logger
from numpy.typing import NDArray

from labelme import __version__
from labelme import utils

PIL.Image.MAX_IMAGE_PIXELS = None


@contextlib.contextmanager
def open(name, mode):
    assert mode in ["r", "w"]
    encoding = "utf-8"
    yield builtins.open(name, mode, encoding=encoding)
    return


class ShapeDict(TypedDict):
    label: str
    points: list[list[float]]
    shape_type: str
    flags: dict[str, bool]
    description: str
    group_id: Optional[int]
    mask: Optional[NDArray[np.bool]]
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

    assert "label" in shape_json_obj, f"label is required: {shape_json_obj}"
    assert isinstance(shape_json_obj["label"], str), (
        f"label must be str: {shape_json_obj['label']}"
    )
    label: str = shape_json_obj["label"]

    assert "points" in shape_json_obj, f"points is required: {shape_json_obj}"
    assert isinstance(shape_json_obj["points"], list), (
        f"points must be list: {shape_json_obj['points']}"
    )
    assert shape_json_obj["points"], f"points must be non-empty: {shape_json_obj}"
    assert all(
        isinstance(point, list)
        and len(point) == 2
        and all(isinstance(xy, (int, float)) for xy in point)
        for point in shape_json_obj["points"]
    ), f"points must be list of [x, y]: {shape_json_obj['points']}"
    points: list[list[float]] = shape_json_obj["points"]

    assert "shape_type" in shape_json_obj, f"shape_type is required: {shape_json_obj}"
    assert isinstance(shape_json_obj["shape_type"], str), (
        f"shape_type must be str: {shape_json_obj['shape_type']}"
    )
    shape_type: str = shape_json_obj["shape_type"]

    flags: dict = {}
    if shape_json_obj.get("flags") is not None:
        assert isinstance(shape_json_obj["flags"], dict), (
            f"flags must be dict: {shape_json_obj['flags']}"
        )
        assert all(
            isinstance(k, str) and isinstance(v, bool)
            for k, v in shape_json_obj["flags"].items()
        ), f"flags must be dict of str to bool: {shape_json_obj['flags']}"
        flags = shape_json_obj["flags"]

    description: str = ""
    if shape_json_obj.get("description") is not None:
        assert isinstance(shape_json_obj["description"], str), (
            f"description must be str: {shape_json_obj['description']}"
        )
        description = shape_json_obj["description"]

    group_id: Optional[int] = None
    if shape_json_obj.get("group_id") is not None:
        assert isinstance(shape_json_obj["group_id"], int), (
            f"group_id must be int: {shape_json_obj['group_id']}"
        )
        group_id = shape_json_obj["group_id"]

    mask: Optional[NDArray[np.bool]] = None
    if shape_json_obj.get("mask") is not None:
        assert isinstance(shape_json_obj["mask"], str), (
            f"mask must be base64-encoded PNG: {shape_json_obj['mask']}"
        )
        mask = utils.img_b64_to_arr(shape_json_obj["mask"]).astype(bool)

    other_data = {k: v for k, v in shape_json_obj.items() if k not in SHAPE_KEYS}

    loaded: ShapeDict = dict(
        label=label,
        points=points,
        shape_type=shape_type,
        flags=flags,
        description=description,
        group_id=group_id,
        mask=mask,
        other_data=other_data,
    )
    assert set(loaded.keys()) == SHAPE_KEYS | {"other_data"}
    return loaded


class LabelFileError(Exception):
    pass


class LabelFile:
    shapes: list[ShapeDict]
    suffix = ".json"

    def __init__(self, filename=None):
        self.shapes = []
        self.imagePath = None
        self.imageData = None
        if filename is not None:
            self.load(filename)
        self.filename = filename

    @staticmethod
    def load_image_file(filename):
        try:
            image_pil = PIL.Image.open(filename)
        except OSError:
            logger.error(f"Failed opening image file: {filename}")
            return

        # apply orientation to image according to exif
        image_pil = utils.apply_exif_orientation(image_pil)

        with io.BytesIO() as f:
            ext = osp.splitext(filename)[1].lower()
            if ext in [".jpg", ".jpeg"]:
                format = "JPEG"
            else:
                format = "PNG"
            image_pil.save(f, format=format)
            f.seek(0)
            return f.read()

    def load(self, filename):
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
            with open(filename, "r") as f:
                data = json.load(f)

            if data["imageData"] is not None:
                imageData = base64.b64decode(data["imageData"])
            else:
                # relative path from label file to relative path from cwd
                imagePath = osp.join(osp.dirname(filename), data["imagePath"])
                imageData = self.load_image_file(imagePath)
            flags = data.get("flags") or {}
            imagePath = data["imagePath"]
            self._check_image_height_and_width(
                base64.b64encode(imageData).decode("utf-8"),
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
    def _check_image_height_and_width(imageData, imageHeight, imageWidth):
        img_arr = utils.img_b64_to_arr(imageData)
        if imageHeight is not None and img_arr.shape[0] != imageHeight:
            logger.error(
                "imageHeight does not match with imageData or imagePath, "
                "so getting imageHeight from actual image."
            )
            imageHeight = img_arr.shape[0]
        if imageWidth is not None and img_arr.shape[1] != imageWidth:
            logger.error(
                "imageWidth does not match with imageData or imagePath, "
                "so getting imageWidth from actual image."
            )
            imageWidth = img_arr.shape[1]
        return imageHeight, imageWidth

    def save(
        self,
        filename,
        shapes,
        imagePath,
        imageHeight,
        imageWidth,
        imageData=None,
        otherData=None,
        flags=None,
    ):
        if imageData is not None:
            imageData = base64.b64encode(imageData).decode("utf-8")
            imageHeight, imageWidth = self._check_image_height_and_width(
                imageData, imageHeight, imageWidth
            )
        if otherData is None:
            otherData = {}
        if flags is None:
            flags = {}
        data = dict(
            version=__version__,
            flags=flags,
            shapes=shapes,
            imagePath=imagePath,
            imageData=imageData,
            imageHeight=imageHeight,
            imageWidth=imageWidth,
        )
        for key, value in otherData.items():
            assert key not in data
            data[key] = value
        try:
            with open(filename, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.filename = filename
        except Exception as e:
            raise LabelFileError(e)

    @staticmethod
    def is_label_file(filename):
        return osp.splitext(filename)[1].lower() == LabelFile.suffix
