from __future__ import annotations

import base64
import importlib
import io
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import PIL.Image
import pytest

mask_api = pytest.importorskip("pycocotools.mask")
labelme2coco = importlib.import_module("examples.instance_segmentation.labelme2coco")


def test_circle_to_polygon_segmentation_rejects_zero_radius() -> None:
    with pytest.raises(ValueError, match="Degenerate circle"):
        labelme2coco._circle_to_polygon_segmentation(center=(5.0, 5.0), edge=(5.0, 5.0))


@pytest.mark.parametrize("radius", [0.1, 1.0, 50.0, 100.0, 1_000.0])
def test_labelme2coco_exports_circle_within_one_pixel(
    *, radius: float, tmp_path: Path
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    center = (radius + 3.0, radius + 2.0)
    size = math.ceil(2 * radius + 6)
    PIL.Image.new("RGB", (size, size)).save(input_dir / "circle.png")
    (input_dir / "circle.json").write_text(
        json.dumps(
            {
                "imagePath": "circle.png",
                "shapes": [
                    {
                        "label": "circle",
                        "shape_type": "circle",
                        "points": [center, (center[0] + radius, center[1])],
                    }
                ],
            }
        )
    )
    labels_file = tmp_path / "labels.txt"
    labels_file.write_text("__ignore__\ncircle\n")
    output_dir = tmp_path / "output"
    subprocess.run(
        [
            sys.executable,
            str(Path(labelme2coco.__file__)),
            str(input_dir),
            str(output_dir),
            "--labels",
            str(labels_file),
            "--noviz",
        ],
        check=True,
    )
    exported = json.loads((output_dir / "annotations.json").read_text())
    (annotation,) = exported["annotations"]
    (coords,) = annotation["segmentation"]
    points = np.array(coords).reshape(-1, 2)
    np.testing.assert_allclose(np.linalg.norm(points - center, axis=1), radius)
    assert len(points) >= 12
    # A chord is farthest from the circle at its midpoint; include the closing edge.
    midpoints = (points + np.roll(points, shift=-1, axis=0)) / 2
    assert np.all(radius - np.linalg.norm(midpoints - center, axis=1) <= 1.0)


def _export(
    *, tmp_path: Path, shapes: list[dict[str, Any]], noviz: bool
) -> dict[str, Any]:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    PIL.Image.new("RGB", (32, 32), color=(20, 40, 60)).save(input_dir / "image.png")
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

    assert (output_dir / "Visualization" / "image.jpg").exists() is not noviz
    return json.loads((output_dir / "annotations.json").read_text())


def _polygon_shape(
    *, label: str, points: list[list[int]], group_id: int | None
) -> dict[str, Any]:
    return dict(label=label, shape_type="polygon", points=points, group_id=group_id)


def _mask_shape(
    *,
    label: str,
    points: list[list[float]],
    patch: np.ndarray,
    group_id: int | None,
) -> dict[str, Any]:
    buffer = io.BytesIO()
    PIL.Image.fromarray(patch.astype(np.uint8) * 255).save(buffer, format="PNG")
    return dict(
        label=label,
        shape_type="mask",
        points=points,
        group_id=group_id,
        mask=base64.b64encode(buffer.getvalue()).decode("ascii"),
    )


def _assert_rle_matches(*, annotation: dict[str, Any], expected: np.ndarray) -> None:
    segmentation = annotation["segmentation"]
    assert isinstance(segmentation["counts"], str)
    np.testing.assert_array_equal(mask_api.decode(segmentation), expected)
    assert annotation["area"] == expected.sum()
    ys, xs = expected.nonzero()
    assert annotation["bbox"] == [
        xs.min(),
        ys.min(),
        xs.max() - xs.min() + 1,
        ys.max() - ys.min() + 1,
    ]


@pytest.mark.parametrize(
    ("shape_labels", "expected_count"),
    [
        pytest.param(["__ignore__"], 0, id="ignored-only"),
        pytest.param(["unlisted"], 0, id="unlisted-only"),
        pytest.param([], 0, id="empty"),
        pytest.param(["cat"], 1, id="known-only"),
        pytest.param(["cat", "__ignore__", "unlisted"], 1, id="mixed"),
    ],
)
@pytest.mark.parametrize("shape_type", ["polygon", "mask"])
@pytest.mark.parametrize("noviz", [False, True])
def test_labelme2coco_handles_filtered_visualization(
    *,
    tmp_path: Path,
    shape_labels: list[str],
    expected_count: int,
    shape_type: str,
    noviz: bool,
) -> None:
    shapes = [
        _polygon_shape(
            label=label, points=[[4, 4], [24, 4], [24, 24], [4, 24]], group_id=None
        )
        if shape_type == "polygon"
        else _mask_shape(
            label=label,
            points=[[4.0, 4.0], [24.0, 24.0]],
            patch=np.ones((21, 21)),
            group_id=None,
        )
        for label in shape_labels
    ]
    exported = _export(tmp_path=tmp_path, shapes=shapes, noviz=noviz)

    assert len(exported["images"]) == 1
    assert len(exported["annotations"]) == expected_count
    assert all(annotation["category_id"] == 0 for annotation in exported["annotations"])


@pytest.mark.parametrize("case", ["hole", "disconnected"])
def test_labelme2coco_exports_bitmap_mask_as_rle(*, tmp_path: Path, case: str) -> None:
    patch = np.ones((5, 7), dtype=bool)
    if case == "hole":
        patch[2, 3] = False
    else:
        patch[:, 3] = False
    expected = np.zeros((32, 32), dtype=np.uint8)
    expected[3:8, 4:11] = patch

    (annotation,) = _export(
        tmp_path=tmp_path,
        shapes=[
            _mask_shape(
                label="cat",
                points=[[4.0, 3.0], [10.0, 7.0]],
                patch=patch,
                group_id=None,
            )
        ],
        noviz=True,
    )["annotations"]
    _assert_rle_matches(annotation=annotation, expected=expected)


@pytest.mark.parametrize("second_shape_type", ["polygon", "mask"])
def test_labelme2coco_merges_grouped_bitmap_mask(
    *, tmp_path: Path, second_shape_type: str
) -> None:
    shapes = [
        _mask_shape(
            label="cat",
            points=[[4.0, 3.0], [10.0, 7.0]],
            patch=np.ones((5, 7)),
            group_id=7,
        ),
        _polygon_shape(
            label="cat", points=[[8, 5], [14, 5], [14, 9], [8, 9]], group_id=7
        )
        if second_shape_type == "polygon"
        else _mask_shape(
            label="cat",
            points=[[8.0, 5.0], [14.0, 9.0]],
            patch=np.ones((5, 7)),
            group_id=7,
        ),
    ]
    expected = np.zeros((32, 32), dtype=np.uint8)
    expected[3:8, 4:11] = 1
    expected[5:10, 8:15] = 1

    (annotation,) = _export(tmp_path=tmp_path, shapes=shapes, noviz=True)["annotations"]
    _assert_rle_matches(annotation=annotation, expected=expected)


def test_labelme2coco_keeps_polygon_next_to_bitmap_mask(*, tmp_path: Path) -> None:
    shapes = [
        _mask_shape(
            label="cat",
            points=[[4.0, 3.0], [10.0, 7.0]],
            patch=np.ones((5, 7)),
            group_id=1,
        ),
        _polygon_shape(
            label="cat", points=[[18, 10], [24, 10], [24, 14], [18, 14]], group_id=2
        ),
    ]
    expected = np.zeros((32, 32), dtype=np.uint8)
    expected[3:8, 4:11] = 1

    mask, polygon = _export(tmp_path=tmp_path, shapes=shapes, noviz=True)["annotations"]
    _assert_rle_matches(annotation=mask, expected=expected)
    assert polygon["segmentation"] == [[18, 10, 24, 10, 24, 14, 18, 14]]
