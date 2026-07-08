from __future__ import annotations

import base64
import io
import json
import time
from dataclasses import dataclass
from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any
from typing import Final
from typing import cast

import numpy as np
import PIL.Image
import tifffile
from loguru import logger
from numpy.typing import NDArray

from labelme import __version__

from . import _utils
from ._utils.shape import ShapeDict

PIL.Image.MAX_IMAGE_PIXELS = None


def _validate_flags(flags: object) -> dict[str, bool]:
    if flags is None:
        return {}
    if not isinstance(flags, dict):
        raise TypeError(f"flags must be dict: {flags}")
    if not all(isinstance(k, str) and isinstance(v, bool) for k, v in flags.items()):
        raise TypeError(f"flags must be dict of str to bool: {flags}")
    return cast(dict[str, bool], flags)


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

    flags = _validate_flags(flags=shape_json_obj.get("flags"))

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
        mask = _utils.img_b64_to_arr(shape_json_obj["mask"]).astype(bool)

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


def _dump_shape_to_json_obj(shape: ShapeDict) -> dict[str, Any]:
    json_obj: dict[str, Any] = dict(shape["other_data"])
    json_obj.update(
        label=shape["label"],
        points=[list(point) for point in shape["points"]],
        group_id=shape["group_id"],
        description=shape["description"],
        shape_type=shape["shape_type"],
        flags=shape["flags"],
        mask=None
        if shape["mask"] is None
        else _utils.img_arr_to_b64(shape["mask"].astype(np.uint8)),
    )
    return json_obj


class LabelFileError(Exception):
    """Base for read/write failures of labelme JSON annotation files."""


class LabelFileReadError(LabelFileError):
    """Wraps an underlying parse or image-decode failure during load."""


class LabelFileWriteError(LabelFileError):
    """Wraps an underlying I/O failure during save."""


@dataclass(frozen=True)
class Annotation:
    image_path: str
    image_data: bytes
    shapes: list[ShapeDict]
    flags: dict[str, bool]
    other_data: dict[str, Any]


LABEL_FILE_SUFFIX: Final[str] = ".json"

_RESERVED_TOP_LEVEL_KEYS: Final[tuple[str, ...]] = (
    "version",
    "imageData",
    "imagePath",
    "shapes",
    "flags",
    "imageHeight",
    "imageWidth",
)


def is_label_file_path(filename: str) -> bool:
    return Path(filename).suffix.lower() == LABEL_FILE_SUFFIX


def read_image_file(filename: str) -> bytes:
    t_start = time.time()
    image_pil = _imread(filename=filename)

    oriented: PIL.Image.Image = _utils.apply_exif_orientation(image=image_pil)
    ext = Path(filename).suffix.lower()
    if oriented is image_pil and ext in (".jpg", ".jpeg", ".png"):
        with open(filename, "rb") as f:
            image_data = f.read()
    else:
        with io.BytesIO() as f:
            fmt = "PNG" if "A" in oriented.mode else "JPEG"
            oriented.save(fp=f, format=fmt, quality=95)
            f.seek(0)
            image_data = f.read()

    logger.debug(
        "Loaded image file: {!r} in {:.0f}ms", filename, (time.time() - t_start) * 1000
    )
    return image_data


def _check_image_dimensions(
    *,
    image_data: bytes,
    expected_height: int | None,
    expected_width: int | None,
) -> None:
    if expected_height is None and expected_width is None:
        return
    actual_w, actual_h = _utils.img_data_to_pil(img_data=image_data).size
    if expected_height is not None and expected_height != actual_h:
        raise ValueError(
            f"imageHeight mismatch: declared={expected_height}, actual={actual_h}"
        )
    if expected_width is not None and expected_width != actual_w:
        raise ValueError(
            f"imageWidth mismatch: declared={expected_width}, actual={actual_w}"
        )


def read_label_file(filename: str) -> Annotation:
    try:
        with open(filename, encoding="utf-8") as f:
            raw: dict[str, Any] = json.load(f)
        image_path = PureWindowsPath(raw["imagePath"]).as_posix()
        if raw["imageData"] is not None:
            image_data = base64.b64decode(raw["imageData"])
        else:
            image_data = read_image_file(
                filename=str(Path(filename).parent / image_path)
            )
        _check_image_dimensions(
            image_data=image_data,
            expected_height=raw.get("imageHeight"),
            expected_width=raw.get("imageWidth"),
        )
        shapes: list[ShapeDict] = [
            _load_shape_json_obj(shape_json_obj=s) for s in raw["shapes"]
        ]
        flags = _validate_flags(flags=raw.get("flags"))
    except (
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as e:
        raise LabelFileReadError(f"failed to load {filename!r}: {e}") from e
    other_data = {k: v for k, v in raw.items() if k not in _RESERVED_TOP_LEVEL_KEYS}
    return Annotation(
        image_path=image_path,
        image_data=image_data,
        shapes=shapes,
        flags=flags,
        other_data=other_data,
    )


def write_label_file(
    filename: str,
    annotation: Annotation,
    *,
    image_height: int | None,
    image_width: int | None,
    save_image_data: bool,
) -> None:
    try:
        image_data_b64: str | None = None
        if save_image_data:
            _check_image_dimensions(
                image_data=annotation.image_data,
                expected_height=image_height,
                expected_width=image_width,
            )
            image_data_b64 = base64.b64encode(annotation.image_data).decode("utf-8")
        # JSON keys stay camelCase: changing them would break existing .json files.
        payload: dict[str, Any] = {
            "version": __version__,
            "flags": dict(annotation.flags) if annotation.flags else {},
            "shapes": [_dump_shape_to_json_obj(shape) for shape in annotation.shapes],
            "imagePath": annotation.image_path,
            "imageData": image_data_b64,
            "imageHeight": image_height,
            "imageWidth": image_width,
        }
        for key, value in annotation.other_data.items():
            if key in _RESERVED_TOP_LEVEL_KEYS:
                raise ValueError(f"reserved key in other_data: {key!r}")
            payload[key] = value
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError, ValueError) as e:
        raise LabelFileWriteError(f"failed to write {filename!r}: {e}") from e


_DISPLAYABLE_MODES = {"1", "L", "P", "RGB", "RGBA", "LA", "PA"}


def _imread(filename: str) -> PIL.Image.Image:
    ext: str = Path(filename).suffix.lower()
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
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros(arr.shape, dtype=np.uint8)
    min_val = finite.min()
    max_val = finite.max()
    if max_val - min_val == 0:
        return np.zeros(arr.shape, dtype=np.uint8)
    normalized = (arr - min_val) / (max_val - min_val) * 255
    bounded = np.nan_to_num(np.clip(normalized, 0, 255), nan=0.0)
    return bounded.astype(np.uint8)
