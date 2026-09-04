from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Final

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
    script = _REPO_ROOT / "examples" / "semantic_segmentation" / "labelme2voc.py"
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


def test_labelme2voc_default_writes_visualization_outputs(
    *, annotated_dir: Path, labels_file: Path, tmp_path: Path
) -> None:
    output_dir = tmp_path / "dataset"
    _run(input_dir=annotated_dir, output_dir=output_dir, labels_file=labels_file)

    assert (output_dir / "SegmentationClass" / "0001.png").is_file()
    assert (output_dir / "SegmentationClassNpy" / "0001.npy").is_file()
    assert (output_dir / "SegmentationClassVisualization" / "0001.jpg").is_file()
    assert (output_dir / "SegmentationObject" / "0001.png").is_file()
    assert (output_dir / "SegmentationObjectVisualization" / "0001.jpg").is_file()


def test_labelme2voc_noviz_omits_visualization_outputs_only(
    *, annotated_dir: Path, labels_file: Path, tmp_path: Path
) -> None:
    output_dir = tmp_path / "dataset"
    _run(
        "--noviz",
        input_dir=annotated_dir,
        output_dir=output_dir,
        labels_file=labels_file,
    )

    assert not (output_dir / "SegmentationClassVisualization").exists()
    assert not (output_dir / "SegmentationObjectVisualization").exists()
    # The visualization flag must not affect the other output groups.
    assert (output_dir / "SegmentationClass" / "0001.png").is_file()
    assert (output_dir / "SegmentationClassNpy" / "0001.npy").is_file()
    assert (output_dir / "SegmentationObject" / "0001.png").is_file()
