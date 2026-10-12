from __future__ import annotations

import importlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import PIL.Image
import pytest

pytest.importorskip("pycocotools.mask")
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
@pytest.mark.parametrize("noviz", [False, True])
def test_labelme2coco_handles_filtered_visualization(
    *,
    tmp_path: Path,
    shape_labels: list[str],
    expected_count: int,
    noviz: bool,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    PIL.Image.new("RGB", (32, 32), color=(20, 40, 60)).save(input_dir / "image.png")
    (input_dir / "image.json").write_text(
        json.dumps(
            {
                "imagePath": "image.png",
                "shapes": [
                    {
                        "label": label,
                        "shape_type": "polygon",
                        "points": [[4, 4], [24, 4], [24, 24], [4, 24]],
                    }
                    for label in shape_labels
                ],
            }
        )
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
    assert len(exported["annotations"]) == expected_count
    assert all(annotation["category_id"] == 0 for annotation in exported["annotations"])
    assert (output_dir / "Visualization" / "image.jpg").exists() is not noviz
