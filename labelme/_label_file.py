from __future__ import annotations

import base64
import contextlib
import dataclasses
import io
import json
import time
import warnings
from collections.abc import Callable
from collections.abc import Iterator
from pathlib import Path
from pathlib import PureWindowsPath
from typing import Any
from typing import Final
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


@contextlib.contextmanager
def _translate_label_file_errors(filename: str, action: str) -> Iterator[None]:
    try:
        yield
    except OSError as exc:
        raise LabelFileError(
            f"Failed to {action} label file {filename!r}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise LabelFileError(
            f"Malformed JSON in label file {filename!r}: {exc}"
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise LabelFileError(
            f"Invalid label file content in {filename!r}: {exc}"
        ) from exc


_RESERVED_LABEL_JSON_KEYS: Final[frozenset[str]] = frozenset(
    {
        "version",
        "imageData",
        "imagePath",
        "shapes",
        "flags",
        "imageHeight",
        "imageWidth",
    }
)


@dataclasses.dataclass(frozen=True)
class _ParsedLabel:
    flags: dict[str, bool]
    shapes: list[ShapeDict]
    image_path: str
    image_data: bytes
    other_data: dict[str, Any]


def _parse_label_json(
    filename: str,
    image_loader: Callable[[str], bytes],
    check_dimensions: Callable[[bytes, int | None, int | None], object],
) -> _ParsedLabel:
    raw_path: Path = Path(filename)
    payload: dict[str, Any] = json.loads(raw_path.read_text(encoding="utf-8"))

    posix_image_path: str = PureWindowsPath(payload["imagePath"]).as_posix()
    encoded_image: str | None = payload["imageData"]
    image_bytes: bytes = (
        base64.b64decode(encoded_image)
        if encoded_image is not None
        else image_loader(str(raw_path.parent / posix_image_path))
    )

    check_dimensions(
        image_bytes,
        payload.get("imageHeight"),
        payload.get("imageWidth"),
    )

    return _ParsedLabel(
        flags=payload.get("flags") or {},
        shapes=[_load_shape_json_obj(shape_json_obj=s) for s in payload["shapes"]],
        image_path=posix_image_path,
        image_data=image_bytes,
        other_data={
            k: v for k, v in payload.items() if k not in _RESERVED_LABEL_JSON_KEYS
        },
    )


class LabelFile:
    shapes: list[ShapeDict]
    suffix = ".json"

    def __init__(self, filename: str | None = None) -> None:
        self.shapes: list[ShapeDict] = []
        self.image_path: str | None = None
        self.image_data: bytes | None = None
        self.other_data: dict[str, Any] = {}
        if filename is not None:
            self.load(filename)
        self.filename: str | None = filename

    @property
    def imagePath(self) -> str | None:
        warnings.warn(
            "LabelFile.imagePath is deprecated and will be removed in a future "
            "release; use image_path",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.image_path

    @imagePath.setter
    def imagePath(self, value: str | None) -> None:
        warnings.warn(
            "LabelFile.imagePath is deprecated and will be removed in a future "
            "release; use image_path",
            DeprecationWarning,
            stacklevel=2,
        )
        self.image_path = value

    @property
    def imageData(self) -> bytes | None:
        warnings.warn(
            "LabelFile.imageData is deprecated and will be removed in a future "
            "release; use image_data",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.image_data

    @imageData.setter
    def imageData(self, value: bytes | None) -> None:
        warnings.warn(
            "LabelFile.imageData is deprecated and will be removed in a future "
            "release; use image_data",
            DeprecationWarning,
            stacklevel=2,
        )
        self.image_data = value

    @property
    def otherData(self) -> dict[str, Any]:
        warnings.warn(
            "LabelFile.otherData is deprecated and will be removed in a future "
            "release; use other_data",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.other_data

    @otherData.setter
    def otherData(self, value: dict[str, Any]) -> None:
        warnings.warn(
            "LabelFile.otherData is deprecated and will be removed in a future "
            "release; use other_data",
            DeprecationWarning,
            stacklevel=2,
        )
        self.other_data = value

    @staticmethod
    def load_image_file(filename: str) -> bytes:
        t0 = time.time()
        image_pil = _imread(filename=filename)

        oriented: PIL.Image.Image = utils.apply_exif_orientation(image_pil)
        ext = Path(filename).suffix.lower()
        if oriented is image_pil and ext in (".jpg", ".jpeg", ".png"):
            # no encoding needed
            with open(filename, "rb") as f:
                image_data = f.read()
        else:
            with io.BytesIO() as f:
                format = "PNG" if "A" in oriented.mode else "JPEG"
                oriented.save(f, format=format, quality=95)
                f.seek(0)
                image_data = f.read()

        logger.debug(
            "Loaded image file: {!r} in {:.0f}ms", filename, (time.time() - t0) * 1000
        )
        return image_data

    def load(self, filename: str) -> None:
        with _translate_label_file_errors(filename, action="load"):
            parsed = _parse_label_json(
                filename,
                image_loader=self.load_image_file,
                check_dimensions=self._check_image_height_and_width,
            )
        self._adopt_parsed(parsed, filename=filename)

    def _adopt_parsed(self, parsed: _ParsedLabel, filename: str) -> None:
        for field in dataclasses.fields(parsed):
            setattr(self, field.name, getattr(parsed, field.name))
        self.filename = filename

    @staticmethod
    def _check_image_height_and_width(
        image_data: bytes, image_height: int | None, image_width: int | None
    ) -> tuple[int | None, int | None]:
        img_pil = utils.img_data_to_pil(image_data)
        actual_w, actual_h = img_pil.size
        if image_height is not None and actual_h != image_height:
            logger.error(
                "imageHeight does not match with imageData or imagePath, "
                "so getting imageHeight from actual image."
            )
            image_height = actual_h
        if image_width is not None and actual_w != image_width:
            logger.error(
                "imageWidth does not match with imageData or imagePath, "
                "so getting imageWidth from actual image."
            )
            image_width = actual_w
        return image_height, image_width

    def save(
        self,
        filename: str,
        shapes: list[dict[str, Any]],
        image_path: str,
        image_height: int | None,
        image_width: int | None,
        image_data: bytes | None = None,
        other_data: dict[str, Any] | None = None,
        flags: dict[str, bool] | None = None,
    ) -> None:
        image_data_b64: str | None = None
        if image_data is not None:
            image_height, image_width = self._check_image_height_and_width(
                image_data, image_height, image_width
            )
            image_data_b64 = base64.b64encode(image_data).decode("utf-8")
        if other_data is None:
            other_data = {}
        if flags is None:
            flags = {}
        # JSON keys stay camelCase — on-disk format, breaks existing .json files.
        data = {
            "version": __version__,
            "flags": flags,
            "shapes": shapes,
            "imagePath": image_path,
            "imageData": image_data_b64,
            "imageHeight": image_height,
            "imageWidth": image_width,
        }
        for key, value in other_data.items():
            assert key not in data
            data[key] = value
        with _translate_label_file_errors(filename, action="save"):
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.filename = filename

    @staticmethod
    def is_label_file(filename: str) -> bool:
        return Path(filename).suffix.lower() == LabelFile.suffix


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
    try:
        img_arr: NDArray = tifffile.imread(filename)
    except tifffile.TiffFileError as exc:
        raise OSError(f"Failed to read TIFF image {filename!r}: {exc}") from exc

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
