from __future__ import annotations

import json
import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any
from typing import TextIO

import numpy as np
import pytest
from numpy.typing import NDArray

from labelme._label_file import Annotation
from labelme._label_file import LabelFileReadError
from labelme._label_file import LabelFileWriteError
from labelme._label_file import ShapeDict
from labelme._label_file import _check_image_dimensions
from labelme._label_file import _dump_shape_to_json_obj
from labelme._label_file import _load_shape_json_obj
from labelme._label_file import _normalize_to_uint8
from labelme._label_file import is_label_file_path
from labelme._label_file import read_label_file
from labelme._label_file import write_label_file
from labelme._utils import img_arr_to_b64


def test_read_label_file_load_windows_path(data_path: Path, tmp_path: Path) -> None:
    """Test that read_label_file loads JSON with Windows-style backslash paths.

    Regression test for https://github.com/wkentaro/labelme/issues/1725
    """
    (tmp_path / "images").mkdir()
    shutil.copy(
        data_path / "annotated" / "2011_000003.jpg",
        tmp_path / "images" / "2011_000003.jpg",
    )

    json_file = tmp_path / "annotations" / "2011_000003.json"
    json_file.parent.mkdir()
    with open(data_path / "annotated" / "2011_000003.json") as f:
        json_data = json.load(f)
    json_data["imagePath"] = "..\\images\\2011_000003.jpg"
    with open(json_file, "w") as f:
        json.dump(json_data, f)

    annotation = read_label_file(filename=str(json_file))
    assert annotation.image_path == "../images/2011_000003.jpg"
    assert annotation.image_data is not None


@pytest.fixture()
def annotated_raw(data_path: Path) -> dict[str, Any]:
    src = data_path / "annotated" / "2011_000003.json"
    with open(src) as f:
        return json.load(f)


@pytest.fixture()
def annotated_dst(data_path: Path, tmp_path: Path) -> Path:
    shutil.copy(
        data_path / "annotated" / "2011_000003.jpg",
        tmp_path / "2011_000003.jpg",
    )
    return tmp_path / "2011_000003.json"


def _dump_json(*, path: Path, raw: dict[str, Any]) -> None:
    with open(path, "w") as f:
        json.dump(raw, f)


def test_read_label_file_returns_label_data(data_path: Path) -> None:
    label_data = read_label_file(
        filename=str(data_path / "annotated" / "2011_000003.json")
    )

    assert label_data.image_path == "2011_000003.jpg"
    assert label_data.image_data
    assert label_data.shapes


def test_read_label_file_extracts_other_data(
    annotated_raw: dict[str, Any],
    annotated_dst: Path,
) -> None:
    annotated_raw["customField"] = {"reviewer": "alice"}
    _dump_json(path=annotated_dst, raw=annotated_raw)

    label_data = read_label_file(filename=str(annotated_dst))

    assert label_data.other_data == {"customField": {"reviewer": "alice"}}


@pytest.mark.parametrize(
    "mutator,error_match",
    [
        (lambda raw: raw.pop("imagePath"), "imagePath"),
        (lambda raw: raw.pop("imageData"), "imageData"),
        (lambda raw: raw.pop("shapes"), "shapes"),
        (lambda raw: raw.update({"imageHeight": 1}), "imageHeight mismatch"),
        (lambda raw: raw.update({"imageWidth": 1}), "imageWidth mismatch"),
        (lambda raw: raw.update({"imageHeight": True}), "imageHeight must be int"),
        (lambda raw: raw.update({"imageWidth": True}), "imageWidth must be int"),
        (lambda raw: raw.update({"imageHeight": 1.0}), "imageHeight must be int"),
        (lambda raw: raw.update({"imageWidth": 1.0}), "imageWidth must be int"),
        (lambda raw: raw.update({"flags": "urgent"}), "flags must be dict:"),
        (lambda raw: raw.update({"flags": False}), "flags must be dict:"),
        (
            lambda raw: raw.update({"flags": {"blurry": 1}}),
            "flags must be dict of str to bool",
        ),
    ],
    ids=[
        "missing_imagePath",
        "missing_imageData",
        "missing_shapes",
        "imageHeight_mismatch",
        "imageWidth_mismatch",
        "imageHeight_bool",
        "imageWidth_bool",
        "imageHeight_float",
        "imageWidth_float",
        "flags_not_dict",
        "flags_falsy_not_dict",
        "flags_value_not_bool",
    ],
)
def test_read_label_file_raises_read_error_on_malformed(
    annotated_raw: dict[str, Any],
    annotated_dst: Path,
    mutator: Callable[[dict[str, Any]], Any],
    error_match: str,
) -> None:
    mutator(annotated_raw)
    _dump_json(path=annotated_dst, raw=annotated_raw)

    with pytest.raises(LabelFileReadError, match=error_match):
        read_label_file(filename=str(annotated_dst))


@pytest.mark.parametrize(
    ("break_shape", "error_match"),
    [
        (lambda shape: shape.pop("label"), "label is required"),
        (lambda shape: shape.update(label=1), "label must be str"),
        (lambda shape: shape.pop("points"), "points is required"),
        (lambda shape: shape.update(points="nope"), "points must be list:"),
        (lambda shape: shape.update(points=[]), "points must be non-empty"),
        (
            lambda shape: shape.update(points=[[0.0, 0.0, 0.0]]),
            "points must be list of",
        ),
        (lambda shape: shape.update(points=[[True, 0.0]]), "points must be list of"),
        (lambda shape: shape.pop("shape_type"), "shape_type is required"),
        (lambda shape: shape.update(shape_type=5), "shape_type must be str"),
        (lambda shape: shape.update(flags="no"), "flags must be dict:"),
        (
            lambda shape: shape.update(flags={"a": 1}),
            "flags must be dict of str to bool",
        ),
        (lambda shape: shape.update(description=1), "description must be str"),
        (lambda shape: shape.update(group_id="1"), "group_id must be int"),
        (lambda shape: shape.update(group_id=True), "group_id must be int"),
        (lambda shape: shape.update(mask=123), "mask must be base64-encoded PNG"),
    ],
    ids=[
        "label_missing",
        "label_not_str",
        "points_missing",
        "points_not_list",
        "points_empty",
        "points_bad_entry",
        "points_bool_coord",
        "shape_type_missing",
        "shape_type_not_str",
        "flags_not_dict",
        "flags_value_not_bool",
        "description_not_str",
        "group_id_not_int",
        "group_id_bool",
        "mask_not_str",
    ],
)
def test_read_label_file_raises_on_malformed_shape_field(
    annotated_raw: dict[str, Any],
    annotated_dst: Path,
    break_shape: Callable[[dict[str, Any]], Any],
    error_match: str,
) -> None:
    shape: dict[str, Any] = {
        "label": "x",
        "points": [[0.0, 0.0]],
        "shape_type": "point",
    }
    break_shape(shape)
    annotated_raw["shapes"].append(shape)
    _dump_json(path=annotated_dst, raw=annotated_raw)

    with pytest.raises(LabelFileReadError, match=error_match):
        read_label_file(filename=str(annotated_dst))


@pytest.fixture()
def sample_mask() -> NDArray[np.bool_]:
    mask = np.zeros((3, 4), dtype=bool)
    mask[1, 2] = True
    return mask


@pytest.mark.parametrize(
    ("shape_type", "points"),
    [
        ("polygon", [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]]),
        ("rectangle", [[2.0, 3.0], [-1.0, -2.0]]),
        (
            "oriented_rectangle",
            [[0.0, 0.0], [2.0, 0.0], [2.0, 1.0], [0.0, 1.0]],
        ),
        ("point", [[0.0, 0.0]]),
        ("line", [[0.0, 0.0], [1.0, 1.0]]),
        ("circle", [[0.0, 0.0], [1.0, 0.0]]),
        ("linestrip", [[0.0, 0.0], [1.0, 1.0]]),
        ("points", [[0.0, 0.0]]),
        # Degenerate but saveable by the editor: v5.x ai_polygon wrote 2-point
        # polygons, and vertex edits can collapse rectangles and coincide
        # points; such files must stay loadable.
        ("polygon", [[0.0, 0.0], [1.0, 1.0]]),
        ("rectangle", [[0.0, 0.0], [0.0, 1.0]]),
        ("line", [[1.0, 1.0], [1.0, 1.0]]),
        ("linestrip", [[0.0, 0.0]]),
    ],
)
def test_load_shape_json_obj_accepts_supported_geometry(
    shape_type: str, points: list[list[float]]
) -> None:
    loaded = _load_shape_json_obj(
        shape_json_obj={
            "label": "shape",
            "points": points,
            "shape_type": shape_type,
        }
    )

    assert loaded["shape_type"] == shape_type
    assert loaded["points"] == points


def test_load_shape_json_obj_accepts_out_of_bounds_mask_shape(
    sample_mask: NDArray[np.bool_],
) -> None:
    loaded = _load_shape_json_obj(
        shape_json_obj={
            "label": "mask",
            "points": [[-2.25, -3.25], [0.75, -1.25]],
            "shape_type": "mask",
            "mask": img_arr_to_b64(sample_mask.astype(np.uint8)),
        }
    )

    assert loaded["mask"] is not None
    assert np.array_equal(loaded["mask"], sample_mask)


@pytest.mark.parametrize(
    ("shape_type", "points"),
    [
        ("rectangle", [[0.0, 0.0]]),
        (
            "oriented_rectangle",
            [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        ),
        ("point", [[0.0, 0.0], [1.0, 1.0]]),
        ("line", [[0.0, 0.0]]),
        ("circle", [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]),
        ("mask", [[0.0, 0.0]]),
    ],
)
def test_load_shape_json_obj_rejects_wrong_point_count(
    shape_type: str, points: list[list[float]]
) -> None:
    shape_json_obj: dict[str, Any] = {
        "label": "shape",
        "points": points,
        "shape_type": shape_type,
    }
    if shape_type == "mask":
        shape_json_obj["mask"] = img_arr_to_b64(np.ones((1, 1), dtype=np.uint8))

    with pytest.raises(ValueError, match="points"):
        _load_shape_json_obj(shape_json_obj=shape_json_obj)


def test_load_shape_json_obj_rejects_unknown_shape_type() -> None:
    with pytest.raises(ValueError, match="shape_type"):
        _load_shape_json_obj(
            shape_json_obj={
                "label": "shape",
                "points": [[0.0, 0.0]],
                "shape_type": "triangle",
            }
        )


def test_load_shape_json_obj_rejects_non_finite_points() -> None:
    with pytest.raises(ValueError, match="points"):
        _load_shape_json_obj(
            shape_json_obj={
                "label": "shape",
                "points": [[float("inf"), 0.0]],
                "shape_type": "point",
            }
        )


def test_load_shape_json_obj_requires_mask_for_mask_shape() -> None:
    with pytest.raises(ValueError, match="mask"):
        _load_shape_json_obj(
            shape_json_obj={
                "label": "mask",
                "points": [[0.0, 0.0], [1.0, 1.0]],
                "shape_type": "mask",
            }
        )


def test_load_shape_json_obj_rejects_mask_for_non_mask_shape(
    sample_mask: NDArray[np.bool_],
) -> None:
    with pytest.raises(ValueError, match="mask"):
        _load_shape_json_obj(
            shape_json_obj={
                "label": "rectangle",
                "points": [[0.0, 0.0], [3.0, 2.0]],
                "shape_type": "rectangle",
                "mask": img_arr_to_b64(sample_mask.astype(np.uint8)),
            }
        )


def test_load_shape_json_obj_rejects_multichannel_mask() -> None:
    with pytest.raises(ValueError, match="mask"):
        _load_shape_json_obj(
            shape_json_obj={
                "label": "mask",
                "points": [[0.0, 0.0], [3.0, 2.0]],
                "shape_type": "mask",
                "mask": img_arr_to_b64(np.ones((3, 4, 3), dtype=np.uint8)),
            }
        )


def test_load_shape_json_obj_accepts_mask_extent_mismatch(
    sample_mask: NDArray[np.bool_],
) -> None:
    # Fractional whole-shape drags shift points without resampling the mask,
    # so the saved bbox extent can drift from the mask dimensions.
    loaded = _load_shape_json_obj(
        shape_json_obj={
            "label": "mask",
            "points": [[0.5, 0.5], [4.5, 2.5]],
            "shape_type": "mask",
            "mask": img_arr_to_b64(sample_mask.astype(np.uint8)),
        }
    )

    assert loaded["mask"] is not None
    assert np.array_equal(loaded["mask"], sample_mask)


def test_read_label_file_reports_shape_index_field_and_filename(
    annotated_raw: dict[str, Any],
    annotated_dst: Path,
) -> None:
    annotated_raw["shapes"] = [
        {"label": "valid", "points": [[0.0, 0.0]], "shape_type": "point"},
        {"label": "bad", "points": [[0.0, 0.0]], "shape_type": "triangle"},
    ]
    _dump_json(path=annotated_dst, raw=annotated_raw)

    with pytest.raises(LabelFileReadError) as exc_info:
        read_label_file(filename=str(annotated_dst))

    # The message quotes the filename with !r, which doubles the backslashes of
    # a Windows path.
    assert repr(str(annotated_dst)) in str(exc_info.value)
    assert "shapes[1]: shape_type" in str(exc_info.value)


def test_read_label_file_wraps_coordinate_overflow(
    annotated_raw: dict[str, Any],
    annotated_dst: Path,
) -> None:
    annotated_raw["shapes"] = [
        {
            "label": "bad",
            "points": [[10**400, 0.0]],
            "shape_type": "point",
        }
    ]
    _dump_json(path=annotated_dst, raw=annotated_raw)

    with pytest.raises(LabelFileReadError) as exc_info:
        read_label_file(filename=str(annotated_dst))

    assert repr(str(annotated_dst)) in str(exc_info.value)
    assert "shapes[0]: points" in str(exc_info.value)


def test_load_shape_json_obj_parses_all_fields() -> None:
    loaded = _load_shape_json_obj(
        shape_json_obj={
            "label": "cat",
            "points": [[1.0, 2.0], [3.0, 4.0]],
            "shape_type": "rectangle",
            "flags": {"occluded": True},
            "description": "a note",
            "group_id": 7,
        }
    )

    assert loaded == {
        "label": "cat",
        "points": [[1.0, 2.0], [3.0, 4.0]],
        "shape_type": "rectangle",
        "flags": {"occluded": True},
        "description": "a note",
        "group_id": 7,
        "mask": None,
        "other_data": {},
    }


def test_load_shape_json_obj_defaults_absent_optional_fields() -> None:
    loaded = _load_shape_json_obj(
        shape_json_obj={
            "label": "cat",
            "points": [[0.0, 0.0]],
            "shape_type": "point",
        }
    )

    assert loaded == {
        "label": "cat",
        "points": [[0.0, 0.0]],
        "shape_type": "point",
        "flags": {},
        "description": "",
        "group_id": None,
        "mask": None,
        "other_data": {},
    }


def test_load_shape_json_obj_keeps_falsy_group_id() -> None:
    loaded = _load_shape_json_obj(
        shape_json_obj={
            "label": "cat",
            "points": [[0.0, 0.0]],
            "shape_type": "point",
            "group_id": 0,
        }
    )

    assert loaded["group_id"] == 0


def test_load_shape_json_obj_buckets_unknown_keys_into_other_data() -> None:
    loaded = _load_shape_json_obj(
        shape_json_obj={
            "label": "cat",
            "points": [[0.0, 0.0]],
            "shape_type": "point",
            "score": 0.9,
            "reviewer": "alice",
        }
    )

    assert loaded["other_data"] == {"score": 0.9, "reviewer": "alice"}


def test_load_shape_json_obj_decodes_mask_to_bool_array(
    sample_mask: NDArray[np.bool_],
) -> None:
    loaded = _load_shape_json_obj(
        shape_json_obj={
            "label": "thing",
            "points": [[0.0, 0.0], [4.0, 3.0]],
            "shape_type": "mask",
            "mask": img_arr_to_b64(sample_mask.astype(np.uint8)),
        }
    )

    assert loaded["mask"] is not None
    assert loaded["mask"].dtype == np.bool_
    assert np.array_equal(loaded["mask"], sample_mask)


def test_dump_shape_to_json_obj_without_mask() -> None:
    shape = ShapeDict(
        label="cat",
        points=[[1.0, 2.0], [3.0, 4.0]],
        shape_type="rectangle",
        flags={"occluded": True},
        description="a note",
        group_id=7,
        mask=None,
        other_data={"score": 0.9},
    )

    json_obj = _dump_shape_to_json_obj(shape=shape)

    assert json_obj == {
        "label": "cat",
        "points": [[1.0, 2.0], [3.0, 4.0]],
        "shape_type": "rectangle",
        "flags": {"occluded": True},
        "description": "a note",
        "group_id": 7,
        "mask": None,
        "score": 0.9,
    }


def test_shape_codec_round_trips_mask(sample_mask: NDArray[np.bool_]) -> None:
    shape = ShapeDict(
        label="thing",
        points=[[0.0, 0.0], [4.0, 3.0]],
        shape_type="mask",
        flags={},
        description="",
        group_id=None,
        mask=sample_mask,
        other_data={},
    )

    reloaded = _load_shape_json_obj(shape_json_obj=_dump_shape_to_json_obj(shape=shape))

    assert reloaded["mask"] is not None
    assert np.array_equal(reloaded["mask"], sample_mask)


def test_write_label_file_round_trips(data_path: Path, tmp_path: Path) -> None:
    src = read_label_file(filename=str(data_path / "annotated" / "2011_000003.json"))
    dst = tmp_path / "out.json"

    annotation = Annotation(
        image_path=src.image_path,
        image_data=src.image_data,
        shapes=src.shapes,
        flags={"ok": True},
        other_data={"customField": 42},
    )
    write_label_file(
        filename=str(dst),
        annotation=annotation,
        image_height=None,
        image_width=None,
        save_image_data=True,
    )

    reloaded = read_label_file(filename=str(dst))
    assert reloaded.image_path == src.image_path
    assert reloaded.flags == {"ok": True}
    assert reloaded.other_data == {"customField": 42}
    assert [(s["label"], s["points"], s["shape_type"]) for s in reloaded.shapes] == [
        (s["label"], s["points"], s["shape_type"]) for s in src.shapes
    ]


def test_write_label_file_round_trips_mask_shape(
    data_path: Path, annotated_dst: Path
) -> None:
    src = read_label_file(filename=str(data_path / "annotated" / "2011_000003.json"))
    mask = np.zeros((4, 5), dtype=bool)
    mask[1:3, 2:4] = True
    shape = ShapeDict(
        label="thing",
        points=[[2.0, 1.0], [3.0, 2.0]],
        shape_type="mask",
        flags={"verified": True},
        description="d",
        group_id=7,
        mask=mask,
        other_data={"score": 0.5},
    )
    annotation = Annotation(
        image_path=src.image_path,
        image_data=src.image_data,
        shapes=[shape],
        flags={},
        other_data={},
    )
    write_label_file(
        filename=str(annotated_dst),
        annotation=annotation,
        image_height=None,
        image_width=None,
        save_image_data=True,
    )

    [reloaded_shape] = read_label_file(filename=str(annotated_dst)).shapes
    assert reloaded_shape["label"] == "thing"
    assert reloaded_shape["shape_type"] == "mask"
    assert reloaded_shape["group_id"] == 7
    assert reloaded_shape["description"] == "d"
    assert reloaded_shape["flags"] == {"verified": True}
    assert reloaded_shape["other_data"] == {"score": 0.5}
    assert reloaded_shape["mask"] is not None
    assert np.array_equal(reloaded_shape["mask"], mask)


@pytest.fixture()
def annotation_to_write() -> Annotation:
    return Annotation(
        image_path="new.jpg",
        image_data=b"",
        shapes=[],
        flags={"reviewed": True},
        other_data={},
    )


@pytest.fixture()
def existing_label_file(tmp_path: Path) -> Path:
    filename = tmp_path / "annotation.json"
    filename.write_text("last good", encoding="utf-8")
    return filename


def test_write_label_file_atomically_replaces_existing_file(
    annotation_to_write: Annotation,
    existing_label_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_replace = os.replace
    replacement_sources: list[Path] = []

    def _replace(src: str, dst: str) -> None:
        source = Path(src)
        assert source.parent == existing_label_file.parent
        assert Path(dst) == existing_label_file
        assert existing_label_file.read_text(encoding="utf-8") == "last good"
        assert json.loads(source.read_text(encoding="utf-8"))["imagePath"] == "new.jpg"
        replacement_sources.append(source)
        real_replace(src, dst)

    monkeypatch.setattr("labelme._label_file.os.replace", _replace)

    write_label_file(
        filename=str(existing_label_file),
        annotation=annotation_to_write,
        image_height=None,
        image_width=None,
        save_image_data=False,
    )

    assert replacement_sources
    assert json.loads(existing_label_file.read_text(encoding="utf-8"))["imagePath"] == (
        "new.jpg"
    )
    assert list(existing_label_file.parent.iterdir()) == [existing_label_file]


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX file modes")
def test_write_label_file_preserves_existing_file_mode(
    annotation_to_write: Annotation,
    existing_label_file: Path,
) -> None:
    existing_label_file.chmod(0o640)

    write_label_file(
        filename=str(existing_label_file),
        annotation=annotation_to_write,
        image_height=None,
        image_width=None,
        save_image_data=False,
    )

    assert stat.S_IMODE(existing_label_file.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX file modes")
def test_write_label_file_uses_default_mode_for_new_file(
    annotation_to_write: Annotation,
    tmp_path: Path,
) -> None:
    reference_file = tmp_path / "reference.json"
    reference_file.write_text("", encoding="utf-8")
    label_file = tmp_path / "annotation.json"

    write_label_file(
        filename=str(label_file),
        annotation=annotation_to_write,
        image_height=None,
        image_width=None,
        save_image_data=False,
    )

    assert stat.S_IMODE(label_file.stat().st_mode) == stat.S_IMODE(
        reference_file.stat().st_mode
    )


@pytest.mark.skipif(os.name == "nt", reason="requires POSIX filename limits")
def test_write_label_file_supports_long_filename(
    annotation_to_write: Annotation,
    tmp_path: Path,
) -> None:
    label_file = tmp_path / f"{'a' * 245}.json"

    write_label_file(
        filename=str(label_file),
        annotation=annotation_to_write,
        image_height=None,
        image_width=None,
        save_image_data=False,
    )

    assert label_file.exists()
    assert list(tmp_path.iterdir()) == [label_file]


def test_write_label_file_serialization_failure_preserves_existing_file(
    annotation_to_write: Annotation,
    existing_label_file: Path,
) -> None:
    annotation = Annotation(
        image_path=annotation_to_write.image_path,
        image_data=annotation_to_write.image_data,
        shapes=annotation_to_write.shapes,
        flags=annotation_to_write.flags,
        other_data={"not_serializable": object()},
    )

    with pytest.raises(LabelFileWriteError, match="not JSON serializable"):
        write_label_file(
            filename=str(existing_label_file),
            annotation=annotation,
            image_height=None,
            image_width=None,
            save_image_data=False,
        )

    assert existing_label_file.read_text(encoding="utf-8") == "last good"
    assert list(existing_label_file.parent.iterdir()) == [existing_label_file]


def test_write_label_file_write_failure_preserves_existing_file(
    annotation_to_write: Annotation,
    existing_label_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_during_write(_obj: object, file: TextIO, **_kwargs: object) -> None:
        file.write("{")
        raise OSError("disk full")

    monkeypatch.setattr("labelme._label_file.json.dump", _fail_during_write)

    with pytest.raises(LabelFileWriteError, match="disk full"):
        write_label_file(
            filename=str(existing_label_file),
            annotation=annotation_to_write,
            image_height=None,
            image_width=None,
            save_image_data=False,
        )

    assert existing_label_file.read_text(encoding="utf-8") == "last good"
    assert list(existing_label_file.parent.iterdir()) == [existing_label_file]


def test_write_label_file_close_failure_preserves_existing_file(
    annotation_to_write: Annotation,
    existing_label_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_during_close(_obj: object, file: TextIO, **_kwargs: object) -> None:
        file.write("{")
        # Closing the descriptor underneath makes the flush inside close() fail,
        # i.e. an error surfacing only when the temporary file is closed.
        os.close(file.fileno())

    monkeypatch.setattr("labelme._label_file.json.dump", _fail_during_close)

    with pytest.raises(LabelFileWriteError, match="failed to write"):
        write_label_file(
            filename=str(existing_label_file),
            annotation=annotation_to_write,
            image_height=None,
            image_width=None,
            save_image_data=False,
        )

    assert existing_label_file.read_text(encoding="utf-8") == "last good"
    assert list(existing_label_file.parent.iterdir()) == [existing_label_file]


def test_write_label_file_replacement_failure_preserves_existing_file(
    annotation_to_write: Annotation,
    existing_label_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_replace(_src: str, _dst: str) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("labelme._label_file.os.replace", _fail_replace)

    with pytest.raises(LabelFileWriteError, match="replace failed"):
        write_label_file(
            filename=str(existing_label_file),
            annotation=annotation_to_write,
            image_height=None,
            image_width=None,
            save_image_data=False,
        )

    assert existing_label_file.read_text(encoding="utf-8") == "last good"
    assert list(existing_label_file.parent.iterdir()) == [existing_label_file]


@pytest.mark.parametrize(
    "reserved_key",
    [
        "version",
        "imagePath",
        "imageData",
        "shapes",
        "flags",
        "imageHeight",
        "imageWidth",
    ],
)
def test_write_label_file_rejects_reserved_other_data_key(
    tmp_path: Path, reserved_key: str
) -> None:
    annotation = Annotation(
        image_path="foo.jpg",
        image_data=b"",
        shapes=[],
        flags={},
        other_data={reserved_key: "x"},
    )
    with pytest.raises(LabelFileWriteError, match=f"reserved key.*{reserved_key}"):
        write_label_file(
            filename=str(tmp_path / "out.json"),
            annotation=annotation,
            image_height=None,
            image_width=None,
            save_image_data=False,
        )


def test_write_label_file_raises_on_dimension_mismatch(
    data_path: Path, tmp_path: Path
) -> None:
    src = read_label_file(filename=str(data_path / "annotated" / "2011_000003.json"))
    annotation = Annotation(
        image_path="foo.jpg",
        image_data=src.image_data,
        shapes=[],
        flags={},
        other_data={},
    )

    with pytest.raises(LabelFileWriteError, match="imageHeight mismatch"):
        write_label_file(
            filename=str(tmp_path / "out.json"),
            annotation=annotation,
            image_height=1,
            image_width=None,
            save_image_data=True,
        )


def test_write_label_file_raises_write_error_on_io_failure(tmp_path: Path) -> None:
    bad_path = tmp_path / "missing_dir" / "out.json"
    annotation = Annotation(
        image_path="foo.jpg",
        image_data=b"",
        shapes=[],
        flags={},
        other_data={},
    )

    with pytest.raises(LabelFileWriteError, match="failed to write"):
        write_label_file(
            filename=str(bad_path),
            annotation=annotation,
            image_height=None,
            image_width=None,
            save_image_data=False,
        )


def test_normalize_to_uint8_scales_finite_range() -> None:
    result = _normalize_to_uint8(np.array([[0.0, 50.0, 100.0]]))
    assert result.dtype == np.uint8
    np.testing.assert_array_equal(result, [[0, 127, 255]])


def test_normalize_to_uint8_constant_array_returns_zeros() -> None:
    result = _normalize_to_uint8(np.full((2, 2), 42.0))
    np.testing.assert_array_equal(result, np.zeros((2, 2), dtype=np.uint8))


def test_normalize_to_uint8_all_non_finite_returns_zeros() -> None:
    result = _normalize_to_uint8(np.full((2, 2), np.nan))
    np.testing.assert_array_equal(result, np.zeros((2, 2), dtype=np.uint8))


def test_normalize_to_uint8_maps_non_finite_pixels_deterministically() -> None:
    """Regression: an inf pixel made the max inf, so finite/inf == 0 turned every
    finite pixel black. Non-finite pixels must saturate instead: +inf -> 255,
    -inf -> 0, nan -> 0, leaving finite pixels scaled over the finite range.
    """
    result = _normalize_to_uint8(
        np.array([[0.0, 50.0, 100.0, np.inf, -np.inf, np.nan]])
    )
    np.testing.assert_array_equal(result, [[0, 127, 255, 255, 0, 0]])


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("foo.json", True),
        ("FOO.JSON", True),
        ("/a/b/c.Json", True),
        ("foo.jpg", False),
        ("foo", False),
        ("dir.json/foo.png", False),
    ],
)
def test_is_label_file_path(filename: str, expected: bool) -> None:
    assert is_label_file_path(filename) is expected


@pytest.fixture()
def sample_image_data(data_path: Path) -> bytes:
    return read_label_file(
        filename=str(data_path / "annotated" / "2011_000003.json")
    ).image_data


def test_check_image_dimensions_both_none_is_noop(sample_image_data: bytes) -> None:
    result = _check_image_dimensions(
        image_data=sample_image_data,
        expected_height=None,
        expected_width=None,
    )
    assert result is None


def test_check_image_dimensions_accepts_matching_dimensions(
    sample_image_data: bytes,
) -> None:
    # The image embedded in 2011_000003.json is 500x338.
    _check_image_dimensions(
        image_data=sample_image_data,
        expected_height=338,
        expected_width=500,
    )


@pytest.mark.parametrize(
    ("expected_height", "expected_width", "error_match"),
    [
        (1, None, "imageHeight mismatch"),
        (None, 1, "imageWidth mismatch"),
    ],
    ids=["height_mismatch", "width_mismatch"],
)
def test_check_image_dimensions_raises_on_mismatch(
    sample_image_data: bytes,
    expected_height: int | None,
    expected_width: int | None,
    error_match: str,
) -> None:
    with pytest.raises(ValueError, match=error_match):
        _check_image_dimensions(
            image_data=sample_image_data,
            expected_height=expected_height,
            expected_width=expected_width,
        )
