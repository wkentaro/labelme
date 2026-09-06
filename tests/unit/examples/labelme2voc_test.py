from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Final

import numpy as np
import PIL.Image
import pytest

_REPO_ROOT: Final = Path(__file__).resolve().parents[3]


def _write_annotation(directory: Path, /) -> None:
    img = PIL.Image.new("RGB", (8, 8), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    record = {
        "version": "5.0.0",
        "flags": {},
        "shapes": [
            {
                "label": "cat",
                "points": [[1, 1], [6, 6]],
                "group_id": None,
                "shape_type": "rectangle",
                "flags": {},
            }
        ],
        "imagePath": "0001.png",
        "imageData": base64.b64encode(buf.getvalue()).decode("ascii"),
        "imageHeight": 8,
        "imageWidth": 8,
    }
    (directory / "0001.json").write_text(json.dumps(record))


def _run(
    *extra_args: str, input_dir: Path, output_dir: Path, labels_file: Path
) -> None:
    script = _REPO_ROOT / "examples" / "instance_segmentation" / "labelme2voc.py"
    subprocess.run(
        [
            sys.executable,
            str(script),
            str(input_dir),
            str(output_dir),
            "--labels",
            str(labels_file),
            *extra_args,
        ],
        check=True,
        cwd=_REPO_ROOT,
    )


@pytest.fixture(name="annotated_dir")
def _annotated_dir(*, tmp_path: Path) -> Path:
    directory = tmp_path / "data_annotated"
    directory.mkdir()
    _write_annotation(directory)
    return directory


@pytest.fixture(name="labels_file")
def _labels_file(*, tmp_path: Path) -> Path:
    path = tmp_path / "labels.txt"
    path.write_text("__ignore__\n_background_\ncat\n")
    return path


@pytest.mark.parametrize("noobject", [False, True])
@pytest.mark.parametrize("nonpy", [False, True])
@pytest.mark.parametrize("noviz", [False, True])
def test_labelme2voc_writes_only_requested_outputs(
    *,
    annotated_dir: Path,
    labels_file: Path,
    tmp_path: Path,
    noobject: bool,
    nonpy: bool,
    noviz: bool,
) -> None:
    output_dir = tmp_path / "dataset"
    flags = []
    if noobject:
        flags.append("--noobject")
    if nonpy:
        flags.append("--nonpy")
    if noviz:
        flags.append("--noviz")
    _run(
        *flags, input_dir=annotated_dir, output_dir=output_dir, labels_file=labels_file
    )

    expected = {"class_names.txt", "JPEGImages/0001.jpg", "SegmentationClass/0001.png"}
    if not nonpy:
        expected.add("SegmentationClassNpy/0001.npy")
    if not noviz:
        expected.add("SegmentationClassVisualization/0001.jpg")
    if not noobject:
        expected.add("SegmentationObject/0001.png")
        if not nonpy:
            expected.add("SegmentationObjectNpy/0001.npy")
        if not noviz:
            expected.add("SegmentationObjectVisualization/0001.jpg")
    assert {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    } == expected
    assert {path.name for path in output_dir.iterdir() if path.is_dir()} == {
        path.split("/")[0] for path in expected if "/" in path
    }


def test_labelme2voc_merges_grouped_shapes_and_keeps_ungrouped_shapes_separate(
    *, annotated_dir: Path, labels_file: Path, tmp_path: Path
) -> None:
    annotation = annotated_dir / "0001.json"
    record = json.loads(annotation.read_text())
    record["shapes"] = [
        dict(label="cat", points=points, group_id=group_id, shape_type="rectangle")
        for points, group_id in [
            ([[1, 1], [2, 2]], 7),
            ([[5, 5], [6, 6]], 7),
            ([[5, 1], [6, 2]], None),
            ([[1, 5], [2, 6]], None),
        ]
    ]
    annotation.write_text(json.dumps(record))
    output_dir = tmp_path / "dataset"
    _run(
        "--noviz",
        input_dir=annotated_dir,
        output_dir=output_dir,
        labels_file=labels_file,
    )

    expected = np.zeros((8, 8), dtype=np.uint8)
    expected[1:3, 1:3] = 1
    expected[5:7, 5:7] = 1
    expected[1:3, 5:7] = 2
    expected[5:7, 1:3] = 3
    np.testing.assert_array_equal(
        np.load(output_dir / "SegmentationObjectNpy/0001.npy"), expected
    )
    with PIL.Image.open(output_dir / "SegmentationObject/0001.png") as image:
        np.testing.assert_array_equal(np.asarray(image), expected)
    np.testing.assert_array_equal(
        np.load(output_dir / "SegmentationClassNpy/0001.npy"), expected > 0
    )
