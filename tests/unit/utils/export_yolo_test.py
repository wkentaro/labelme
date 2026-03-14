# MIT License
# Copyright (c) Kentaro Wada

"""Tests for labelme.utils.export_yolo."""

from __future__ import annotations

import json
import pathlib

import pytest

from labelme.utils.export_yolo import json_to_yolo_dir
from labelme.utils.export_yolo import shape_to_yolo_line

# ---------------------------------------------------------------------------
# shape_to_yolo_line tests
# ---------------------------------------------------------------------------

CLASS_LIST = ["cat", "dog", "bird"]
IMG_W = 640
IMG_H = 480


def _rect_shape(label: str, x0: float, y0: float, x1: float, y1: float) -> dict:
    return {
        "label": label,
        "shape_type": "rectangle",
        "points": [[x0, y0], [x1, y1]],
    }


def _polygon_shape(label: str, points: list[list[float]]) -> dict:
    return {
        "label": label,
        "shape_type": "polygon",
        "points": points,
    }


class TestShapeToYoloLine:
    def test_rectangle_basic(self):
        shape = _rect_shape("cat", 100, 50, 300, 250)
        line = shape_to_yolo_line(shape, IMG_W, IMG_H, CLASS_LIST)
        assert line is not None
        parts = line.split()
        assert parts[0] == "0"  # class_id for "cat"
        cx, cy, bw, bh = map(float, parts[1:])
        assert cx == pytest.approx(200 / 640)
        assert cy == pytest.approx(150 / 480)
        assert bw == pytest.approx(200 / 640)
        assert bh == pytest.approx(200 / 480)

    def test_rectangle_reversed_coords(self):
        """Right-to-left or bottom-to-top rectangles should produce valid boxes."""
        shape_normal = _rect_shape("dog", 100, 100, 300, 300)
        shape_reversed = _rect_shape("dog", 300, 300, 100, 100)
        line_normal = shape_to_yolo_line(shape_normal, IMG_W, IMG_H, CLASS_LIST)
        line_reversed = shape_to_yolo_line(shape_reversed, IMG_W, IMG_H, CLASS_LIST)
        assert line_normal == line_reversed

    def test_rectangle_class_id(self):
        """Class id must match position in class_list."""
        line_cat = shape_to_yolo_line(
            _rect_shape("cat", 0, 0, 10, 10), IMG_W, IMG_H, CLASS_LIST
        )
        line_dog = shape_to_yolo_line(
            _rect_shape("dog", 0, 0, 10, 10), IMG_W, IMG_H, CLASS_LIST
        )
        line_bird = shape_to_yolo_line(
            _rect_shape("bird", 0, 0, 10, 10), IMG_W, IMG_H, CLASS_LIST
        )
        assert line_cat is not None and line_cat.startswith("0 ")
        assert line_dog is not None and line_dog.startswith("1 ")
        assert line_bird is not None and line_bird.startswith("2 ")

    def test_polygon_basic(self):
        points = [[10, 10], [200, 10], [200, 200], [10, 200]]
        shape = _polygon_shape("cat", points)
        line = shape_to_yolo_line(shape, IMG_W, IMG_H, CLASS_LIST)
        assert line is not None
        parts = line.split()
        assert parts[0] == "0"
        # Should have class_id + 4*2 coordinate values
        assert len(parts) == 1 + len(points) * 2

    def test_polygon_minimum_three_points(self):
        """Polygons with fewer than 3 points should return None."""
        shape = _polygon_shape("cat", [[0, 0], [100, 0]])
        assert shape_to_yolo_line(shape, IMG_W, IMG_H, CLASS_LIST) is None

    def test_unknown_label_returns_none(self):
        shape = _rect_shape("unknown_class", 0, 0, 100, 100)
        assert shape_to_yolo_line(shape, IMG_W, IMG_H, CLASS_LIST) is None

    def test_unsupported_shape_type_returns_none(self):
        for shape_type in ("circle", "line", "linestrip", "point"):
            shape = {
                "label": "cat",
                "shape_type": shape_type,
                "points": [[0, 0], [100, 100]],
            }
            assert shape_to_yolo_line(shape, IMG_W, IMG_H, CLASS_LIST) is None, (
                shape_type
            )

    def test_coords_clamped_to_unit_range(self):
        """Coordinates that slightly exceed the image boundary should be clamped."""
        shape = _rect_shape("cat", -10, -10, 650, 490)
        line = shape_to_yolo_line(shape, IMG_W, IMG_H, CLASS_LIST)
        assert line is not None
        parts = line.split()
        for v in map(float, parts[1:]):
            assert 0.0 <= v <= 1.0

    def test_rectangle_wrong_point_count(self):
        shape = {
            "label": "cat",
            "shape_type": "rectangle",
            "points": [[0, 0], [100, 100], [200, 200]],  # 3 points — invalid
        }
        assert shape_to_yolo_line(shape, IMG_W, IMG_H, CLASS_LIST) is None

    def test_normalized_values_between_0_and_1(self):
        shape = _rect_shape("dog", 0, 0, IMG_W, IMG_H)
        line = shape_to_yolo_line(shape, IMG_W, IMG_H, CLASS_LIST)
        assert line is not None
        parts = line.split()
        cx, cy, bw, bh = map(float, parts[1:])
        assert cx == pytest.approx(0.5)
        assert cy == pytest.approx(0.5)
        assert bw == pytest.approx(1.0)
        assert bh == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# json_to_yolo_dir tests
# ---------------------------------------------------------------------------


def _write_labelme_json(
    path: pathlib.Path, shapes: list[dict], w: int = 640, h: int = 480
) -> None:
    data = {
        "imageWidth": w,
        "imageHeight": h,
        "shapes": shapes,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


class TestJsonToYoloDir:
    def test_basic_conversion(self, tmp_path: pathlib.Path):
        json_path = tmp_path / "img.json"
        _write_labelme_json(
            json_path,
            [_rect_shape("cat", 100, 100, 300, 300)],
        )
        out_dir = tmp_path / "labels"
        lines = json_to_yolo_dir(json_path, out_dir, CLASS_LIST)
        assert len(lines) == 1
        assert lines[0].startswith("0 ")
        out_file = out_dir / "img.txt"
        assert out_file.exists()
        assert out_file.read_text(encoding="utf-8").strip() == lines[0]

    def test_multiple_shapes(self, tmp_path: pathlib.Path):
        json_path = tmp_path / "multi.json"
        shapes = [
            _rect_shape("cat", 0, 0, 100, 100),
            _rect_shape("dog", 200, 200, 400, 400),
            _polygon_shape("bird", [[10, 10], [50, 10], [50, 50], [10, 50]]),
        ]
        _write_labelme_json(json_path, shapes)
        lines = json_to_yolo_dir(json_path, tmp_path / "out", CLASS_LIST)
        assert len(lines) == 3

    def test_unknown_labels_skipped(self, tmp_path: pathlib.Path):
        json_path = tmp_path / "img.json"
        _write_labelme_json(
            json_path,
            [
                _rect_shape("cat", 0, 0, 100, 100),
                _rect_shape("zebra", 100, 100, 200, 200),  # not in class_list
            ],
        )
        lines = json_to_yolo_dir(json_path, tmp_path / "out", CLASS_LIST)
        assert len(lines) == 1

    def test_empty_shapes(self, tmp_path: pathlib.Path):
        json_path = tmp_path / "empty.json"
        _write_labelme_json(json_path, [])
        lines = json_to_yolo_dir(json_path, tmp_path / "out", CLASS_LIST)
        assert lines == []
        out_file = tmp_path / "out" / "empty.txt"
        assert out_file.exists()
        assert out_file.read_text() == ""

    def test_output_dir_created(self, tmp_path: pathlib.Path):
        json_path = tmp_path / "img.json"
        _write_labelme_json(json_path, [])
        out_dir = tmp_path / "a" / "b" / "c"
        assert not out_dir.exists()
        json_to_yolo_dir(json_path, out_dir, CLASS_LIST)
        assert out_dir.exists()

    def test_missing_dimensions_raises(self, tmp_path: pathlib.Path):
        json_path = tmp_path / "bad.json"
        json_path.write_text(json.dumps({"shapes": []}), encoding="utf-8")
        with pytest.raises(ValueError, match="imageWidth"):
            json_to_yolo_dir(json_path, tmp_path / "out", CLASS_LIST)

    def test_zero_dimensions_raises(self, tmp_path: pathlib.Path):
        json_path = tmp_path / "bad.json"
        _write_labelme_json(json_path, [], w=0, h=0)
        with pytest.raises(ValueError, match="positive"):
            json_to_yolo_dir(json_path, tmp_path / "out", CLASS_LIST)

    def test_txt_filename_matches_json_stem(self, tmp_path: pathlib.Path):
        json_path = tmp_path / "frame_0042.json"
        _write_labelme_json(json_path, [_rect_shape("cat", 10, 10, 200, 200)])
        out_dir = tmp_path / "out"
        json_to_yolo_dir(json_path, out_dir, CLASS_LIST)
        assert (out_dir / "frame_0042.txt").exists()
