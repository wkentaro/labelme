from __future__ import annotations

import base64
import io
import json
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Final
from typing import TypedDict

import numpy as np
import PIL.Image
import PIL.ImageOps
import tifffile

import labelme


LABEL_FILE_SUFFIX: Final[str] = ".json"

_RESERVED_TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "version",
        "flags",
        "shapes",
        "imagePath",
        "imageData",
        "imageHeight",
        "imageWidth",
    }
)

_SHAPE_KNOWN_KEYS: Final[frozenset[str]] = frozenset(
    {
        "label",
        "points",
        "shape_type",
        "flags",
        "description",
        "group_id",
        "mask",
    }
)


class LabelFileError(Exception):
    pass


class LabelFileReadError(LabelFileError):
    pass


class LabelFileWriteError(LabelFileError):
    pass


class ShapeDict(TypedDict):
    label: str
    points: list[list[float]]
    shape_type: str
    flags: dict[str, bool]
    description: str
    group_id: int | None
    mask: np.ndarray | None
    other_data: dict[str, Any]


@dataclass(frozen=True)
class Annotation:
    image_path: str
    image_data: bytes | None
    shapes: list[ShapeDict]
    flags: dict[str, bool]
    other_data: dict[str, Any]


def is_label_file_path(filename: str) -> bool:
    return Path(filename).suffix.lower() == LABEL_FILE_SUFFIX


def _decode_mask(b64_str: str) -> np.ndarray:
    raw = base64.b64decode(b64_str)
    img = PIL.Image.open(io.BytesIO(raw))
    return np.array(img).astype(bool)


def _encode_mask(mask: np.ndarray) -> str:
    img = PIL.Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _load_shape_json_obj(raw: dict[str, Any]) -> ShapeDict:
    if "label" not in raw:
        raise ValueError("label is required")
    label = raw["label"]
    if not isinstance(label, str):
        raise TypeError("label must be str")

    if "points" not in raw:
        raise ValueError("points is required")
    points = raw["points"]
    if not isinstance(points, list):
        raise TypeError("points must be list")
    if len(points) == 0:
        raise ValueError("points must be non-empty")
    for pt in points:
        if not isinstance(pt, list) or len(pt) != 2:
            raise ValueError("points must be list of [x, y] pairs")
        if not all(isinstance(c, (int, float)) for c in pt):
            raise ValueError("points must be list of numeric [x, y] pairs")

    if "shape_type" not in raw:
        raise ValueError("shape_type is required")
    shape_type = raw["shape_type"]
    if not isinstance(shape_type, str):
        raise TypeError("shape_type must be str")

    raw_flags = raw.get("flags")
    if raw_flags is None:
        flags: dict[str, bool] = {}
    elif not isinstance(raw_flags, dict):
        raise TypeError("flags must be dict")
    else:
        for k, v in raw_flags.items():
            if not isinstance(k, str) or not isinstance(v, bool):
                raise TypeError("flags must be dict of str to bool")
        flags = raw_flags

    raw_description = raw.get("description")
    if raw_description is None:
        description: str = ""
    elif not isinstance(raw_description, str):
        raise TypeError("description must be str")
    else:
        description = raw_description

    raw_group_id = raw.get("group_id")
    if raw_group_id is None:
        group_id: int | None = None
    elif isinstance(raw_group_id, bool) or not isinstance(raw_group_id, int):
        raise TypeError("group_id must be int or null")
    else:
        group_id = raw_group_id

    raw_mask = raw.get("mask")
    if raw_mask is None:
        mask: np.ndarray | None = None
    else:
        mask = _decode_mask(raw_mask)

    other_data = {k: v for k, v in raw.items() if k not in _SHAPE_KNOWN_KEYS}

    return ShapeDict(
        label=label,
        points=points,
        shape_type=shape_type,
        flags=flags,
        description=description,
        group_id=group_id,
        mask=mask,
        other_data=other_data,
    )


def _dump_shape_to_json_obj(shape: ShapeDict) -> dict[str, Any]:
    raw_mask = shape["mask"]
    if raw_mask is not None:
        mask_val: str | None = _encode_mask(raw_mask)
    else:
        mask_val = None

    result: dict[str, Any] = {
        "label": shape["label"],
        "points": shape["points"],
        "shape_type": shape["shape_type"],
        "flags": shape["flags"],
        "description": shape["description"],
        "group_id": shape["group_id"],
        "mask": mask_val,
    }
    result.update(shape["other_data"])
    return result


def _get_image_dimensions(image_data: bytes) -> tuple[int, int]:
    img = PIL.Image.open(io.BytesIO(image_data))
    width, height = img.size
    return height, width


def read_label_file(filename: str) -> Annotation:
    try:
        with open(filename, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        raise LabelFileReadError(f"failed to load {filename!r}: {exc}") from exc

    if "imagePath" not in raw:
        raise LabelFileReadError("imagePath is required")
    if "imageData" not in raw:
        raise LabelFileReadError("imageData is required")
    if "shapes" not in raw:
        raise LabelFileReadError("shapes is required")

    image_path: str = raw["imagePath"].replace("\\", "/")

    raw_image_data = raw["imageData"]
    if raw_image_data is not None:
        image_data: bytes | None = base64.b64decode(raw_image_data)
    else:
        image_dir = Path(filename).parent
        image_file = image_dir / image_path
        try:
            image_data = read_image_file(str(image_file))
        except Exception as exc:
            raise LabelFileReadError(
                f"failed to load image {str(image_file)!r}: {exc}"
            ) from exc

    raw_flags = raw.get("flags")
    flags: dict[str, bool] = raw_flags if isinstance(raw_flags, dict) else {}

    shapes: list[ShapeDict] = []
    for shape_raw in raw["shapes"]:
        try:
            shapes.append(_load_shape_json_obj(shape_raw))
        except (ValueError, TypeError) as exc:
            raise LabelFileReadError(str(exc)) from exc

    image_height = raw.get("imageHeight")
    image_width = raw.get("imageWidth")

    if image_data is not None and (image_height is not None or image_width is not None):
        actual_h, actual_w = _get_image_dimensions(image_data)
        if image_height is not None and actual_h != image_height:
            raise LabelFileReadError(
                f"imageHeight mismatch: file says {image_height}, image is {actual_h}"
            )
        if image_width is not None and actual_w != image_width:
            raise LabelFileReadError(
                f"imageWidth mismatch: file says {image_width}, image is {actual_w}"
            )

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
    image_height: int | None,
    image_width: int | None,
    save_image_data: bool,
) -> None:
    for key in annotation.other_data:
        if key in _RESERVED_TOP_LEVEL_KEYS:
            raise LabelFileWriteError(f"reserved key {key!r} in other_data")

    if save_image_data and annotation.image_data is not None:
        actual_h, actual_w = _get_image_dimensions(annotation.image_data)
        if image_height is not None and actual_h != image_height:
            raise LabelFileWriteError(
                f"imageHeight mismatch: provided {image_height}, image is {actual_h}"
            )
        if image_width is not None and actual_w != image_width:
            raise LabelFileWriteError(
                f"imageWidth mismatch: provided {image_width}, image is {actual_w}"
            )

    if save_image_data and annotation.image_data is not None:
        image_data_str: str | None = base64.b64encode(annotation.image_data).decode(
            "utf-8"
        )
        h_out: int | None = image_height
        w_out: int | None = image_width
    else:
        image_data_str = None
        h_out = image_height
        w_out = image_width

    if save_image_data and annotation.image_data is None:
        image_data_str = None
        h_out = None
        w_out = None

    shapes_json = [_dump_shape_to_json_obj(s) for s in annotation.shapes]

    data: dict[str, Any] = {
        "version": labelme.__version__,
        "flags": annotation.flags,
        "shapes": shapes_json,
        "imagePath": annotation.image_path,
        "imageData": image_data_str,
        "imageHeight": h_out,
        "imageWidth": w_out,
    }
    data.update(annotation.other_data)

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        raise LabelFileWriteError(f"failed to write {filename!r}: {exc}") from exc


def _normalize_tiff_to_pil(img_array: np.ndarray) -> PIL.Image.Image:
    if img_array.ndim == 2:
        arr = img_array
        if arr.dtype.kind == "f":
            vmin = arr.min()
            vmax = arr.max()
            if vmax > vmin:
                arr = ((arr - vmin) / (vmax - vmin) * 255).astype(np.uint8)
            else:
                arr = np.zeros_like(arr, dtype=np.uint8)
        else:
            arr = arr.astype(np.uint8)
        return PIL.Image.fromarray(arr, mode="L")
    elif img_array.ndim == 3:
        bands = img_array.shape[2]
        if bands == 1:
            return _normalize_tiff_to_pil(img_array[:, :, 0])
        elif bands == 2:
            return _normalize_tiff_to_pil(img_array[:, :, 0])
        elif bands == 3:
            arr = img_array
            if arr.dtype.kind == "f":
                vmin = arr.min()
                vmax = arr.max()
                if vmax > vmin:
                    arr = ((arr - vmin) / (vmax - vmin) * 255).astype(np.uint8)
                else:
                    arr = np.zeros_like(arr, dtype=np.uint8)
            else:
                arr = arr.astype(np.uint8)
            return PIL.Image.fromarray(arr, mode="RGB")
        elif bands == 4:
            arr = img_array
            if arr.dtype.kind == "f":
                vmin = arr.min()
                vmax = arr.max()
                if vmax > vmin:
                    arr = ((arr - vmin) / (vmax - vmin) * 255).astype(np.uint8)
                else:
                    arr = np.zeros_like(arr, dtype=np.uint8)
            else:
                arr = arr.astype(np.uint8)
            return PIL.Image.fromarray(arr, mode="RGBA")
        else:
            rgb = img_array[:, :, :3]
            return _normalize_tiff_to_pil(rgb)
    else:
        raise ValueError(f"unexpected array shape: {img_array.shape}")


def _pil_to_bytes(img: PIL.Image.Image) -> bytes:
    buf = io.BytesIO()
    if img.mode in ("RGBA", "LA", "PA"):
        img.save(buf, format="PNG")
    else:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(buf, format="JPEG")
    return buf.getvalue()


def read_image_file(filename: str) -> bytes:
    ext = Path(filename).suffix.lower()
    if ext in (".tif", ".tiff"):
        arr = tifffile.imread(filename)
        pil_img = _normalize_tiff_to_pil(arr)
        return _pil_to_bytes(pil_img)

    with open(filename, "rb") as f:
        raw_bytes = f.read()

    img = PIL.Image.open(io.BytesIO(raw_bytes))
    img = PIL.ImageOps.exif_transpose(img)

    if img.mode in ("RGB", "RGBA", "L"):
        return raw_bytes

    buf = io.BytesIO()
    if img.mode in ("LA", "PA"):
        img = img.convert("RGBA")
        img.save(buf, format="PNG")
    else:
        img = img.convert("RGB")
        img.save(buf, format="JPEG")
    return buf.getvalue()


class LabelFile:
    suffix: str = LABEL_FILE_SUFFIX

    def __init__(self, filename: str | None = None) -> None:
        self.shapes: list[ShapeDict] = []
        self.image_path: str | None = None
        self.image_data: bytes | None = None
        self.flags: dict[str, bool] = {}
        self.other_data: dict[str, Any] = {}
        self.filename: str | None = None

        if filename is not None:
            self.load(filename=filename)

    def __getattr__(self, name: str) -> Any:
        _CAMEL_TO_SNAKE: dict[str, str] = {
            "imagePath": "image_path",
            "imageData": "image_data",
            "otherData": "other_data",
        }
        if name in _CAMEL_TO_SNAKE:
            snake = _CAMEL_TO_SNAKE[name]
            warnings.warn(
                f"Use {snake!r} instead of {name!r}",
                DeprecationWarning,
                stacklevel=2,
            )
            return getattr(self, snake)
        raise AttributeError(f"{type(self).__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        _CAMEL_TO_SNAKE: dict[str, str] = {
            "imagePath": "image_path",
            "imageData": "image_data",
            "otherData": "other_data",
        }
        if name in _CAMEL_TO_SNAKE:
            snake = _CAMEL_TO_SNAKE[name]
            warnings.warn(
                f"Use {snake!r} instead of {name!r}",
                DeprecationWarning,
                stacklevel=2,
            )
            super().__setattr__(snake, value)
        else:
            super().__setattr__(name, value)

    def load(self, filename: str) -> None:
        ann = read_label_file(filename=filename)
        self.filename = filename
        self.image_path = ann.image_path
        self.image_data = ann.image_data
        self.shapes = ann.shapes
        self.flags = ann.flags
        self.other_data = ann.other_data

    def save(
        self,
        filename: str,
        shapes: list[ShapeDict],
        image_path: str,
        image_data: bytes | None,
        other_data: dict[str, Any] | None,
        flags: dict[str, bool] | None = None,
        image_height: int | None = None,
        image_width: int | None = None,
    ) -> None:
        ann = Annotation(
            image_path=image_path,
            image_data=image_data,
            shapes=shapes,
            flags=flags or {},
            other_data=other_data or {},
        )
        write_label_file(
            filename=filename,
            annotation=ann,
            image_height=image_height,
            image_width=image_width,
            save_image_data=image_data is not None,
        )
        self.filename = filename

    @staticmethod
    def is_label_file(filename: str) -> bool:
        return is_label_file_path(filename=filename)

    @staticmethod
    def load_image_file(filename: str) -> bytes:
        return read_image_file(filename=filename)
