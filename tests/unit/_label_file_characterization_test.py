"""Characterization tests locking the observable behavior of labelme/_label_file.py.

These tests pin the current contract — JSON schema, field names, encoding,
error handling, round-trips — so a redesign can verify it preserves behavior.
"""
from __future__ import annotations

import base64
import io
import json
import shutil
import tempfile
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import PIL.Image
import pytest

from labelme import __version__
from labelme._label_file import Annotation
from labelme._label_file import LABEL_FILE_SUFFIX
from labelme._label_file import LabelFile
from labelme._label_file import LabelFileError
from labelme._label_file import LabelFileReadError
from labelme._label_file import LabelFileWriteError
from labelme._label_file import ShapeDict
from labelme._label_file import _dump_shape_to_json_obj
from labelme._label_file import _load_shape_json_obj
from labelme._label_file import is_label_file_path
from labelme._label_file import read_image_file
from labelme._label_file import read_label_file
from labelme._label_file import write_label_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tiny_jpeg_bytes() -> bytes:
    """Return raw bytes of a minimal 10x8 JPEG image."""
    img = PIL.Image.new("RGB", (10, 8), (50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


@pytest.fixture()
def tiny_jpeg_file(tmp_path: Path, tiny_jpeg_bytes: bytes) -> Path:
    p = tmp_path / "tiny.jpg"
    p.write_bytes(tiny_jpeg_bytes)
    return p


@pytest.fixture()
def minimal_json_file(tmp_path: Path, tiny_jpeg_bytes: bytes) -> Path:
    """A valid label JSON referencing an embedded JPEG (imageData != null)."""
    b64 = base64.b64encode(tiny_jpeg_bytes).decode("utf-8")
    data: dict[str, Any] = {
        "version": "5.0.0",
        "flags": {},
        "shapes": [],
        "imagePath": "tiny.jpg",
        "imageData": b64,
        "imageHeight": None,
        "imageWidth": None,
    }
    p = tmp_path / "minimal.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture()
def fixture_jpg(data_path: Path) -> Path:
    return data_path / "annotated" / "2011_000003.jpg"


@pytest.fixture()
def fixture_json(data_path: Path) -> Path:
    return data_path / "annotated" / "2011_000003.json"


# ---------------------------------------------------------------------------
# LABEL_FILE_SUFFIX constant
# ---------------------------------------------------------------------------


def test_label_file_suffix_is_dot_json() -> None:
    assert LABEL_FILE_SUFFIX == ".json"


# ---------------------------------------------------------------------------
# is_label_file_path
# ---------------------------------------------------------------------------


def test_is_label_file_path_true_for_json() -> None:
    assert is_label_file_path("annotation.json") is True


def test_is_label_file_path_true_case_insensitive() -> None:
    assert is_label_file_path("annotation.JSON") is True


def test_is_label_file_path_false_for_jpg() -> None:
    assert is_label_file_path("image.jpg") is False


def test_is_label_file_path_false_for_png() -> None:
    assert is_label_file_path("image.png") is False


def test_is_label_file_path_false_for_no_extension() -> None:
    assert is_label_file_path("annotation") is False


# ---------------------------------------------------------------------------
# LabelFile class-level attributes
# ---------------------------------------------------------------------------


def test_label_file_suffix_class_attr() -> None:
    assert LabelFile.suffix == LABEL_FILE_SUFFIX


def test_label_file_is_label_file_static_method() -> None:
    assert LabelFile.is_label_file("foo.json") is True
    assert LabelFile.is_label_file("foo.jpg") is False


# ---------------------------------------------------------------------------
# LabelFile default constructor
# ---------------------------------------------------------------------------


def test_label_file_default_constructor_initializes_empty_state() -> None:
    lf = LabelFile()
    assert lf.shapes == []
    assert lf.image_path is None
    assert lf.image_data is None
    assert lf.other_data == {}
    assert lf.flags == {}
    assert lf.filename is None


# ---------------------------------------------------------------------------
# LabelFile constructor with filename
# ---------------------------------------------------------------------------


def test_label_file_constructor_with_filename_loads_all_attributes(
    fixture_json: Path, fixture_jpg: Path
) -> None:
    lf = LabelFile(str(fixture_json))
    assert lf.filename == str(fixture_json)
    assert lf.image_path == "2011_000003.jpg"
    assert lf.image_data is not None
    assert len(lf.shapes) > 0
    assert isinstance(lf.flags, dict)


def test_label_file_constructor_with_missing_file_raises_read_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(LabelFileReadError):
        LabelFile(str(tmp_path / "nonexistent.json"))


# ---------------------------------------------------------------------------
# LabelFile.load_image_file static method
# ---------------------------------------------------------------------------


def test_load_image_file_returns_bytes(fixture_jpg: Path) -> None:
    result = LabelFile.load_image_file(str(fixture_jpg))
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_load_image_file_matches_module_level_read_image_file(
    fixture_jpg: Path,
) -> None:
    assert LabelFile.load_image_file(str(fixture_jpg)) == read_image_file(
        str(fixture_jpg)
    )


# ---------------------------------------------------------------------------
# LabelFile.save sets filename
# ---------------------------------------------------------------------------


def test_label_file_save_updates_filename(tmp_path: Path) -> None:
    lf = LabelFile()
    dst = str(tmp_path / "out.json")
    lf.save(dst, [], "img.jpg", None, None)
    assert lf.filename == dst


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


def test_label_file_read_error_is_label_file_error() -> None:
    assert issubclass(LabelFileReadError, LabelFileError)


def test_label_file_write_error_is_label_file_error() -> None:
    assert issubclass(LabelFileWriteError, LabelFileError)


# ---------------------------------------------------------------------------
# read_label_file — embedded imageData (base64)
# ---------------------------------------------------------------------------


def test_read_label_file_decodes_base64_image_data(
    minimal_json_file: Path, tiny_jpeg_bytes: bytes
) -> None:
    ann = read_label_file(str(minimal_json_file))
    assert ann.image_data == tiny_jpeg_bytes


def test_read_label_file_with_embedded_image_data_does_not_need_image_file(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    b64 = base64.b64encode(tiny_jpeg_bytes).decode("utf-8")
    data: dict[str, Any] = {
        "version": "5.0.0",
        "flags": {},
        "shapes": [],
        "imagePath": "no_such_file.jpg",
        "imageData": b64,
        "imageHeight": None,
        "imageWidth": None,
    }
    p = tmp_path / "embedded.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    ann = read_label_file(str(p))
    assert ann.image_data == tiny_jpeg_bytes


# ---------------------------------------------------------------------------
# read_label_file — imageData=null reads from disk
# ---------------------------------------------------------------------------


def test_read_label_file_loads_image_from_disk_when_image_data_is_null(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    (tmp_path / "img.jpg").write_bytes(tiny_jpeg_bytes)
    data: dict[str, Any] = {
        "version": "5.0.0",
        "flags": {},
        "shapes": [],
        "imagePath": "img.jpg",
        "imageData": None,
        "imageHeight": None,
        "imageWidth": None,
    }
    (tmp_path / "ann.json").write_text(json.dumps(data), encoding="utf-8")
    ann = read_label_file(str(tmp_path / "ann.json"))
    assert isinstance(ann.image_data, bytes)
    assert len(ann.image_data) > 0


def test_read_label_file_raises_when_image_data_null_and_image_file_missing(
    tmp_path: Path,
) -> None:
    data: dict[str, Any] = {
        "version": "5.0.0",
        "flags": {},
        "shapes": [],
        "imagePath": "missing.jpg",
        "imageData": None,
        "imageHeight": None,
        "imageWidth": None,
    }
    p = tmp_path / "ann.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(LabelFileReadError):
        read_label_file(str(p))


# ---------------------------------------------------------------------------
# read_label_file — flags handling
# ---------------------------------------------------------------------------


def test_read_label_file_flags_key_missing_returns_empty_dict(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    b64 = base64.b64encode(tiny_jpeg_bytes).decode("utf-8")
    data: dict[str, Any] = {
        "version": "5.0.0",
        "shapes": [],
        "imagePath": "img.jpg",
        "imageData": b64,
        "imageHeight": None,
        "imageWidth": None,
    }
    p = tmp_path / "ann.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    ann = read_label_file(str(p))
    assert ann.flags == {}


def test_read_label_file_flags_null_returns_empty_dict(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    b64 = base64.b64encode(tiny_jpeg_bytes).decode("utf-8")
    data: dict[str, Any] = {
        "version": "5.0.0",
        "flags": None,
        "shapes": [],
        "imagePath": "img.jpg",
        "imageData": b64,
        "imageHeight": None,
        "imageWidth": None,
    }
    p = tmp_path / "ann.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    ann = read_label_file(str(p))
    assert ann.flags == {}


# ---------------------------------------------------------------------------
# read_label_file — version field NOT in other_data (it is reserved)
# ---------------------------------------------------------------------------


def test_read_label_file_version_is_not_in_other_data(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    b64 = base64.b64encode(tiny_jpeg_bytes).decode("utf-8")
    data: dict[str, Any] = {
        "version": "3.16.7",
        "flags": {},
        "shapes": [],
        "imagePath": "img.jpg",
        "imageData": b64,
        "imageHeight": None,
        "imageWidth": None,
    }
    p = tmp_path / "ann.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    ann = read_label_file(str(p))
    assert "version" not in ann.other_data


# ---------------------------------------------------------------------------
# read_label_file — error paths
# ---------------------------------------------------------------------------


def test_read_label_file_raises_on_nonexistent_file() -> None:
    with pytest.raises(LabelFileReadError, match="failed to load"):
        read_label_file("/nonexistent/path/file.json")


def test_read_label_file_raises_on_invalid_json(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("this is {{{ not json", encoding="utf-8")
    with pytest.raises(LabelFileReadError):
        read_label_file(str(p))


# ---------------------------------------------------------------------------
# write_label_file — exact JSON schema on disk
# ---------------------------------------------------------------------------


def test_write_label_file_produces_exact_top_level_keys(tmp_path: Path) -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=None,
        shapes=[],
        flags={},
        other_data={},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=100, image_width=200, save_image_data=False)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    assert set(data.keys()) == {
        "version",
        "flags",
        "shapes",
        "imagePath",
        "imageData",
        "imageHeight",
        "imageWidth",
    }


def test_write_label_file_version_field_is_current_version(tmp_path: Path) -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=None,
        shapes=[],
        flags={},
        other_data={},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=None, image_width=None, save_image_data=False)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    assert data["version"] == __version__


def test_write_label_file_version_is_always_overwritten_not_preserved(
    tmp_path: Path,
) -> None:
    """Old version in the annotation is discarded; current __version__ is always written."""
    ann = Annotation(
        image_path="img.jpg",
        image_data=None,
        shapes=[],
        flags={},
        other_data={},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=None, image_width=None, save_image_data=False)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    assert data["version"] == __version__
    assert data["version"] != "3.16.7"


def test_write_label_file_image_height_and_width_in_json(tmp_path: Path) -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=None,
        shapes=[],
        flags={},
        other_data={},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=128, image_width=256, save_image_data=False)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    assert data["imageHeight"] == 128
    assert data["imageWidth"] == 256


def test_write_label_file_null_dimensions_written_as_null(tmp_path: Path) -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=None,
        shapes=[],
        flags={},
        other_data={},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=None, image_width=None, save_image_data=False)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    assert data["imageHeight"] is None
    assert data["imageWidth"] is None


def test_write_label_file_save_image_data_false_writes_null_image_data(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=tiny_jpeg_bytes,
        shapes=[],
        flags={},
        other_data={},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=None, image_width=None, save_image_data=False)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    assert data["imageData"] is None


def test_write_label_file_save_image_data_true_writes_base64_string(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=tiny_jpeg_bytes,
        shapes=[],
        flags={},
        other_data={},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=8, image_width=10, save_image_data=True)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data["imageData"], str)
    assert base64.b64decode(data["imageData"]) == tiny_jpeg_bytes


def test_write_label_file_annotation_image_data_none_with_save_true_writes_null(
    tmp_path: Path,
) -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=None,
        shapes=[],
        flags={},
        other_data={},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=None, image_width=None, save_image_data=True)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    assert data["imageData"] is None


def test_write_label_file_json_uses_two_space_indent(tmp_path: Path) -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=None,
        shapes=[],
        flags={"ok": True},
        other_data={},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=None, image_width=None, save_image_data=False)
    raw = Path(dst).read_text(encoding="utf-8")
    assert "\n  " in raw


def test_write_label_file_json_has_non_ascii_unescaped(tmp_path: Path) -> None:
    ann = Annotation(
        image_path="图像.jpg",
        image_data=None,
        shapes=[],
        flags={},
        other_data={"备注": "测试"},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=None, image_width=None, save_image_data=False)
    raw = Path(dst).read_text(encoding="utf-8")
    assert "图像" in raw
    assert "备注" in raw
    assert "测试" in raw


# ---------------------------------------------------------------------------
# write_label_file — other_data passthrough and reserved key rejection
# ---------------------------------------------------------------------------


def test_write_label_file_other_data_appears_as_top_level_keys(
    tmp_path: Path,
) -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=None,
        shapes=[],
        flags={},
        other_data={"customScore": 0.99, "reviewer": "alice"},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=None, image_width=None, save_image_data=False)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    assert data["customScore"] == 0.99
    assert data["reviewer"] == "alice"


# ---------------------------------------------------------------------------
# write_label_file — round-trip unicode image path
# ---------------------------------------------------------------------------


def test_write_read_round_trip_unicode_image_path(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    ann = Annotation(
        image_path="图像_001.jpg",
        image_data=tiny_jpeg_bytes,
        shapes=[],
        flags={},
        other_data={},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=8, image_width=10, save_image_data=True)
    reloaded = read_label_file(dst)
    assert reloaded.image_path == "图像_001.jpg"


# ---------------------------------------------------------------------------
# write_label_file — version is always re-stamped on reload → write cycle
# ---------------------------------------------------------------------------


def test_old_version_in_json_is_overwritten_on_write(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    b64 = base64.b64encode(tiny_jpeg_bytes).decode("utf-8")
    old = {
        "version": "3.16.7",
        "flags": {},
        "shapes": [],
        "imagePath": "img.jpg",
        "imageData": b64,
        "imageHeight": None,
        "imageWidth": None,
    }
    src = tmp_path / "old.json"
    src.write_text(json.dumps(old), encoding="utf-8")
    ann = read_label_file(str(src))
    dst = str(tmp_path / "new.json")
    write_label_file(dst, ann, image_height=None, image_width=None, save_image_data=False)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    assert data["version"] == __version__
    assert data["version"] != "3.16.7"


# ---------------------------------------------------------------------------
# _load_shape_json_obj — required fields
# ---------------------------------------------------------------------------


def test_load_shape_json_obj_requires_label() -> None:
    with pytest.raises(ValueError, match="label is required"):
        _load_shape_json_obj({"points": [[1.0, 2.0]], "shape_type": "polygon"})


def test_load_shape_json_obj_label_must_be_str() -> None:
    with pytest.raises(TypeError, match="label must be str"):
        _load_shape_json_obj(
            {"label": 123, "points": [[1.0, 2.0]], "shape_type": "polygon"}
        )


def test_load_shape_json_obj_requires_points() -> None:
    with pytest.raises(ValueError, match="points is required"):
        _load_shape_json_obj({"label": "x", "shape_type": "polygon"})


def test_load_shape_json_obj_points_must_be_list() -> None:
    with pytest.raises(TypeError, match="points must be list"):
        _load_shape_json_obj(
            {"label": "x", "points": "bad", "shape_type": "polygon"}
        )


def test_load_shape_json_obj_points_must_be_nonempty() -> None:
    with pytest.raises(ValueError, match="points must be non-empty"):
        _load_shape_json_obj({"label": "x", "points": [], "shape_type": "polygon"})


def test_load_shape_json_obj_point_must_have_two_coordinates() -> None:
    with pytest.raises(ValueError, match="points must be list of"):
        _load_shape_json_obj(
            {"label": "x", "points": [[1.0, 2.0, 3.0]], "shape_type": "polygon"}
        )


def test_load_shape_json_obj_point_coordinates_must_be_numeric() -> None:
    with pytest.raises(ValueError, match="points must be list of"):
        _load_shape_json_obj(
            {"label": "x", "points": [["a", "b"]], "shape_type": "polygon"}
        )


def test_load_shape_json_obj_integer_point_coordinates_are_accepted() -> None:
    result = _load_shape_json_obj(
        {"label": "x", "points": [[1, 2], [3, 4]], "shape_type": "polygon"}
    )
    assert result["points"] == [[1, 2], [3, 4]]


def test_load_shape_json_obj_requires_shape_type() -> None:
    with pytest.raises(ValueError, match="shape_type is required"):
        _load_shape_json_obj({"label": "x", "points": [[1.0, 2.0]]})


def test_load_shape_json_obj_shape_type_must_be_str() -> None:
    with pytest.raises(TypeError, match="shape_type must be str"):
        _load_shape_json_obj(
            {"label": "x", "points": [[1.0, 2.0]], "shape_type": 42}
        )


# ---------------------------------------------------------------------------
# _load_shape_json_obj — optional fields and defaults
# ---------------------------------------------------------------------------


def test_load_shape_json_obj_missing_flags_defaults_to_empty_dict() -> None:
    result = _load_shape_json_obj(
        {"label": "x", "points": [[1.0, 2.0]], "shape_type": "polygon"}
    )
    assert result["flags"] == {}


def test_load_shape_json_obj_null_flags_defaults_to_empty_dict() -> None:
    result = _load_shape_json_obj(
        {"label": "x", "points": [[1.0, 2.0]], "shape_type": "polygon", "flags": None}
    )
    assert result["flags"] == {}


def test_load_shape_json_obj_flags_must_be_dict() -> None:
    with pytest.raises(TypeError, match="flags must be dict"):
        _load_shape_json_obj(
            {"label": "x", "points": [[1.0, 2.0]], "shape_type": "polygon", "flags": "bad"}
        )


def test_load_shape_json_obj_flags_key_must_be_str() -> None:
    with pytest.raises(TypeError, match="flags must be dict of str to bool"):
        _load_shape_json_obj(
            {
                "label": "x",
                "points": [[1.0, 2.0]],
                "shape_type": "polygon",
                "flags": {1: True},
            }
        )


def test_load_shape_json_obj_flags_value_must_be_bool() -> None:
    with pytest.raises(TypeError, match="flags must be dict of str to bool"):
        _load_shape_json_obj(
            {
                "label": "x",
                "points": [[1.0, 2.0]],
                "shape_type": "polygon",
                "flags": {"k": 1},
            }
        )


def test_load_shape_json_obj_missing_description_defaults_to_empty_str() -> None:
    result = _load_shape_json_obj(
        {"label": "x", "points": [[1.0, 2.0]], "shape_type": "polygon"}
    )
    assert result["description"] == ""


def test_load_shape_json_obj_null_description_defaults_to_empty_str() -> None:
    result = _load_shape_json_obj(
        {
            "label": "x",
            "points": [[1.0, 2.0]],
            "shape_type": "polygon",
            "description": None,
        }
    )
    assert result["description"] == ""


def test_load_shape_json_obj_description_must_be_str() -> None:
    with pytest.raises(TypeError, match="description must be str"):
        _load_shape_json_obj(
            {
                "label": "x",
                "points": [[1.0, 2.0]],
                "shape_type": "polygon",
                "description": 42,
            }
        )


def test_load_shape_json_obj_missing_group_id_defaults_to_none() -> None:
    result = _load_shape_json_obj(
        {"label": "x", "points": [[1.0, 2.0]], "shape_type": "polygon"}
    )
    assert result["group_id"] is None


def test_load_shape_json_obj_null_group_id_is_none() -> None:
    result = _load_shape_json_obj(
        {
            "label": "x",
            "points": [[1.0, 2.0]],
            "shape_type": "polygon",
            "group_id": None,
        }
    )
    assert result["group_id"] is None


def test_load_shape_json_obj_integer_group_id() -> None:
    result = _load_shape_json_obj(
        {
            "label": "x",
            "points": [[1.0, 2.0]],
            "shape_type": "polygon",
            "group_id": 5,
        }
    )
    assert result["group_id"] == 5


def test_load_shape_json_obj_float_group_id_rejected() -> None:
    with pytest.raises(TypeError, match="group_id must be int"):
        _load_shape_json_obj(
            {
                "label": "x",
                "points": [[1.0, 2.0]],
                "shape_type": "polygon",
                "group_id": 5.5,
            }
        )


def test_load_shape_json_obj_unknown_keys_go_to_other_data() -> None:
    result = _load_shape_json_obj(
        {
            "label": "x",
            "points": [[1.0, 2.0]],
            "shape_type": "polygon",
            "customProp": "hello",
            "score": 0.9,
        }
    )
    assert result["other_data"] == {"customProp": "hello", "score": 0.9}


def test_load_shape_json_obj_no_unknown_keys_yields_empty_other_data() -> None:
    result = _load_shape_json_obj(
        {"label": "x", "points": [[1.0, 2.0]], "shape_type": "polygon"}
    )
    assert result["other_data"] == {}


# ---------------------------------------------------------------------------
# _dump_shape_to_json_obj
# ---------------------------------------------------------------------------


def test_dump_shape_to_json_obj_includes_all_fields() -> None:
    shape = ShapeDict(
        label="cat",
        points=[[1.0, 2.0], [3.0, 4.0]],
        shape_type="rectangle",
        flags={"iscrowd": False},
        description="a cat",
        group_id=3,
        mask=None,
        other_data={"score": 0.9},
    )
    result = _dump_shape_to_json_obj(shape)
    assert result["label"] == "cat"
    assert result["points"] == [[1.0, 2.0], [3.0, 4.0]]
    assert result["shape_type"] == "rectangle"
    assert result["flags"] == {"iscrowd": False}
    assert result["description"] == "a cat"
    assert result["group_id"] == 3
    assert result["mask"] is None


def test_dump_shape_to_json_obj_spreads_other_data_at_top_level() -> None:
    shape = ShapeDict(
        label="x",
        points=[[0.0, 0.0]],
        shape_type="point",
        flags={},
        description="",
        group_id=None,
        mask=None,
        other_data={"score": 0.9, "extra": "value"},
    )
    result = _dump_shape_to_json_obj(shape)
    assert result["score"] == 0.9
    assert result["extra"] == "value"


def test_dump_shape_to_json_obj_mask_none_stays_none() -> None:
    shape = ShapeDict(
        label="x",
        points=[[0.0, 0.0]],
        shape_type="point",
        flags={},
        description="",
        group_id=None,
        mask=None,
        other_data={},
    )
    result = _dump_shape_to_json_obj(shape)
    assert result["mask"] is None


def test_dump_shape_to_json_obj_mask_array_encoded_as_string() -> None:
    mask = np.zeros((4, 5), dtype=bool)
    mask[1:3, 2:4] = True
    shape = ShapeDict(
        label="x",
        points=[[0.0, 0.0]],
        shape_type="mask",
        flags={},
        description="",
        group_id=None,
        mask=mask,
        other_data={},
    )
    result = _dump_shape_to_json_obj(shape)
    assert isinstance(result["mask"], str)


# ---------------------------------------------------------------------------
# _load_shape_json_obj / _dump_shape_to_json_obj — mask round-trip
# ---------------------------------------------------------------------------


def test_shape_mask_round_trip_via_load_and_dump() -> None:
    mask = np.zeros((4, 5), dtype=bool)
    mask[1:3, 2:4] = True
    shape = ShapeDict(
        label="thing",
        points=[[2.0, 1.0]],
        shape_type="mask",
        flags={},
        description="",
        group_id=None,
        mask=mask,
        other_data={},
    )
    dumped = _dump_shape_to_json_obj(shape)
    assert isinstance(dumped["mask"], str)
    reloaded = _load_shape_json_obj(dumped)
    assert reloaded["mask"] is not None
    assert np.array_equal(reloaded["mask"], mask)


# ---------------------------------------------------------------------------
# read_label_file / write_label_file — shape field round-trip from fixture
# ---------------------------------------------------------------------------


def test_fixture_shapes_round_trip_preserves_label_points_shape_type(
    fixture_json: Path,
) -> None:
    ann = read_label_file(str(fixture_json))
    for shape in ann.shapes:
        assert isinstance(shape["label"], str)
        assert isinstance(shape["points"], list)
        assert len(shape["points"]) >= 1
        assert isinstance(shape["shape_type"], str)


def test_fixture_shapes_have_group_id_zero_for_second_person(
    fixture_json: Path,
) -> None:
    """The fixture has group_id=0 for the second and third shapes (not null)."""
    ann = read_label_file(str(fixture_json))
    group_ids = [s["group_id"] for s in ann.shapes]
    assert 0 in group_ids


def test_fixture_shapes_have_null_group_id_for_first_person(
    fixture_json: Path,
) -> None:
    ann = read_label_file(str(fixture_json))
    assert ann.shapes[0]["group_id"] is None


# ---------------------------------------------------------------------------
# read_label_file — _RESERVED_TOP_LEVEL_KEYS not in other_data
# ---------------------------------------------------------------------------


def test_read_label_file_reserved_keys_not_in_other_data(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    b64 = base64.b64encode(tiny_jpeg_bytes).decode("utf-8")
    data: dict[str, Any] = {
        "version": "5.0.0",
        "flags": {"ok": True},
        "shapes": [],
        "imagePath": "img.jpg",
        "imageData": b64,
        "imageHeight": 8,
        "imageWidth": 10,
    }
    p = tmp_path / "ann.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    ann = read_label_file(str(p))
    reserved = {"version", "imageData", "imagePath", "shapes", "flags", "imageHeight", "imageWidth"}
    for key in reserved:
        assert key not in ann.other_data, f"Reserved key {key!r} leaked into other_data"


# ---------------------------------------------------------------------------
# write_label_file — image dimension check on write
# ---------------------------------------------------------------------------


def test_write_label_file_raises_on_image_height_mismatch(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=tiny_jpeg_bytes,
        shapes=[],
        flags={},
        other_data={},
    )
    with pytest.raises(LabelFileWriteError, match="imageHeight mismatch"):
        write_label_file(
            str(tmp_path / "out.json"),
            ann,
            image_height=999,
            image_width=None,
            save_image_data=True,
        )


def test_write_label_file_raises_on_image_width_mismatch(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=tiny_jpeg_bytes,
        shapes=[],
        flags={},
        other_data={},
    )
    with pytest.raises(LabelFileWriteError, match="imageWidth mismatch"):
        write_label_file(
            str(tmp_path / "out.json"),
            ann,
            image_height=None,
            image_width=999,
            save_image_data=True,
        )


def test_write_label_file_no_dimension_check_when_save_image_data_false(
    tmp_path: Path, tiny_jpeg_bytes: bytes
) -> None:
    """Dimension mismatch is NOT checked when save_image_data=False."""
    ann = Annotation(
        image_path="img.jpg",
        image_data=tiny_jpeg_bytes,
        shapes=[],
        flags={},
        other_data={},
    )
    dst = str(tmp_path / "out.json")
    write_label_file(dst, ann, image_height=999, image_width=None, save_image_data=False)
    with open(dst, encoding="utf-8") as f:
        data = json.load(f)
    assert data["imageHeight"] == 999


# ---------------------------------------------------------------------------
# Annotation dataclass is frozen (immutable)
# ---------------------------------------------------------------------------


def test_annotation_is_frozen() -> None:
    ann = Annotation(
        image_path="img.jpg",
        image_data=None,
        shapes=[],
        flags={},
        other_data={},
    )
    with pytest.raises((TypeError, AttributeError)):
        ann.image_path = "other.jpg"  # type: ignore[misc]
