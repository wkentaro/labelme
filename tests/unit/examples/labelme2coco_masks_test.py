from __future__ import annotations

import base64
import importlib
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import PIL.Image
import pytest
from numpy.typing import NDArray

mask_api = pytest.importorskip("pycocotools.mask")
labelme2coco = importlib.import_module("examples.instance_segmentation.labelme2coco")


def _mask_shape(
    *,
    patch: NDArray[np.uint8],
    points: list[list[float]],
    label: str,
    group_id: int | None,
) -> dict[str, Any]:
    buffer = io.BytesIO()
    PIL.Image.fromarray(patch * 255).save(buffer, format="PNG")
    return dict(
        label=label,
        shape_type="mask",
        points=points,
        group_id=group_id,
        mask=base64.b64encode(buffer.getvalue()).decode("ascii"),
    )


def _export_annotations(
    *, tmp_path: Path, shapes: list[dict[str, Any]], noviz: bool
) -> list[dict[str, Any]]:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    PIL.Image.new("RGB", (32, 24), color=(20, 40, 60)).save(input_dir / "image.png")
    (input_dir / "image.json").write_text(
        json.dumps({"imagePath": "image.png", "shapes": shapes})
    )
    labels_file = tmp_path / "labels.txt"
    labels_file.write_text("__ignore__\ncat\n")
    output_dir = tmp_path / "output"
    args = [
        sys.executable,
        str(Path(labelme2coco.__file__)),
        str(input_dir),
        str(output_dir),
        "--labels",
        str(labels_file),
    ]
    if noviz:
        args.append("--noviz")
    subprocess.run(args, check=True, capture_output=True, text=True)

    exported = json.loads((output_dir / "annotations.json").read_text())
    assert len(exported["images"]) == 1
    assert (output_dir / "Visualization" / "image.jpg").exists() is not noviz
    return exported["annotations"]


def _assert_rle_matches_mask(
    *, annotation: dict[str, Any], expected: NDArray[np.uint8]
) -> None:
    segmentation = annotation["segmentation"]
    assert isinstance(segmentation, dict)
    assert isinstance(segmentation["counts"], str)
    assert segmentation["size"] == list(expected.shape)
    np.testing.assert_array_equal(mask_api.decode(segmentation), expected)
    assert annotation["area"] == int(expected.sum())
    ys, xs = expected.nonzero()
    assert annotation["bbox"] == [
        int(xs.min()),
        int(ys.min()),
        int(xs.max() - xs.min() + 1),
        int(ys.max() - ys.min() + 1),
    ]
    assert annotation["category_id"] == 0
    assert annotation["iscrowd"] == 0


@pytest.mark.parametrize(
    "case", ["solid", "hole", "disconnected", "clipped", "fractional"]
)
@pytest.mark.parametrize("noviz", [False, True])
def test_labelme2coco_exports_bitmap_mask(
    *, tmp_path: Path, case: str, noviz: bool
) -> None:
    patch = np.ones((5, 7), dtype=np.uint8)
    if case == "hole":
        patch[2, 3] = 0
    elif case == "disconnected":
        patch[:, 3] = 0

    expected = np.zeros((24, 32), dtype=np.uint8)
    if case == "clipped":
        points = [[-2.0, -1.0], [4.0, 3.0]]
        expected[:4, :5] = patch[1:, 2:]
    elif case == "fractional":
        points = [[4.7, 3.7], [10.3, 7.3]]
        expected[4:9, 5:12] = patch
    else:
        points = [[4.0, 3.0], [10.0, 7.0]]
        expected[3:8, 4:11] = patch

    (annotation,) = _export_annotations(
        tmp_path=tmp_path,
        shapes=[_mask_shape(patch=patch, points=points, label="cat", group_id=None)],
        noviz=noviz,
    )
    _assert_rle_matches_mask(annotation=annotation, expected=expected)


@pytest.mark.parametrize("with_polygon", [False, True])
@pytest.mark.parametrize("noviz", [False, True])
def test_labelme2coco_merges_grouped_bitmap_shapes(
    *, tmp_path: Path, with_polygon: bool, noviz: bool
) -> None:
    patch = np.ones((5, 7), dtype=np.uint8)
    patch[2, 3] = 0
    shapes = [
        _mask_shape(
            patch=patch, points=[[4.0, 3.0], [10.0, 7.0]], label="cat", group_id=7
        )
    ]
    if with_polygon:
        shapes.append(
            dict(
                label="cat",
                shape_type="polygon",
                points=[[8, 5], [14, 5], [14, 9], [8, 9]],
                group_id=7,
            )
        )
    else:
        shapes.append(
            _mask_shape(
                patch=np.ones((5, 7), dtype=np.uint8),
                points=[[8.0, 5.0], [14.0, 9.0]],
                label="cat",
                group_id=7,
            )
        )
    expected = np.zeros((24, 32), dtype=np.uint8)
    expected[3:8, 4:11] = patch
    expected[5:10, 8:15] = 1

    (annotation,) = _export_annotations(tmp_path=tmp_path, shapes=shapes, noviz=noviz)
    _assert_rle_matches_mask(annotation=annotation, expected=expected)


@pytest.mark.parametrize("noviz", [False, True])
def test_labelme2coco_keeps_polygon_output_next_to_bitmap_mask(
    *, tmp_path: Path, noviz: bool
) -> None:
    shapes = [
        _mask_shape(
            patch=np.ones((5, 7), dtype=np.uint8),
            points=[[4.0, 3.0], [10.0, 7.0]],
            label="cat",
            group_id=1,
        ),
        dict(
            label="cat",
            shape_type="polygon",
            points=[[18, 10], [24, 10], [24, 14], [18, 14]],
            group_id=2,
        ),
    ]
    bitmap, polygon = _export_annotations(tmp_path=tmp_path, shapes=shapes, noviz=noviz)
    expected = np.zeros((24, 32), dtype=np.uint8)
    expected[3:8, 4:11] = 1
    _assert_rle_matches_mask(annotation=bitmap, expected=expected)
    assert polygon["segmentation"] == [[18, 10, 24, 10, 24, 14, 18, 14]]


@pytest.mark.parametrize("label", ["__ignore__", "unlisted"])
@pytest.mark.parametrize("noviz", [False, True])
def test_labelme2coco_skips_filtered_bitmap_masks(
    *, tmp_path: Path, label: str, noviz: bool
) -> None:
    annotations = _export_annotations(
        tmp_path=tmp_path,
        shapes=[
            _mask_shape(
                patch=np.ones((5, 7), dtype=np.uint8),
                points=[[4.0, 3.0], [10.0, 7.0]],
                label=label,
                group_id=None,
            )
        ],
        noviz=noviz,
    )
    assert annotations == []
