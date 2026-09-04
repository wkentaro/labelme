from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import TypedDict

from PIL import Image
from PIL import ImageDraw


class _FixtureShape(TypedDict):
    label: str
    points: list[list[float]]
    group_id: None
    description: str
    shape_type: str
    flags: dict[str, bool]
    mask: None


def make_shape(
    *, label: str, points: list[list[float]], shape_type: str = "polygon"
) -> _FixtureShape:
    return {
        "label": label,
        "points": points,
        "group_id": None,
        "description": "",
        "shape_type": shape_type,
        "flags": {},
        "mask": None,
    }


def render_scene(*, size: tuple[int, int], shapes: list[_FixtureShape]) -> bytes:
    image = Image.new("RGB", size, "#f4f1e8")
    draw = ImageDraw.Draw(image)
    colors = ["#e3a33d", "#4e91c4", "#63a66f", "#d76558", "#8a69ad"]
    for shape, color in zip(shapes, colors):
        points = [(point[0], point[1]) for point in shape["points"]]
        if shape["shape_type"] == "rectangle":
            assert len(points) == 2
            draw.rectangle(
                (points[0], points[1]), fill=color, outline="#263238", width=4
            )
        else:
            draw.polygon(points, fill=color, outline="#263238", width=4)

    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, subsampling=0, optimize=False)
    return output.getvalue()


def write_annotation(
    *,
    path: Path,
    image_name: str,
    image_bytes: bytes,
    size: tuple[int, int],
    shapes: list[_FixtureShape],
    embed_image: bool,
) -> None:
    width, height = size
    data = {
        "version": "6.0.0",
        "flags": {},
        "shapes": shapes,
        "imagePath": image_name,
        "imageData": (
            base64.b64encode(image_bytes).decode("ascii") if embed_image else None
        ),
        "imageHeight": height,
        "imageWidth": width,
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def generate_fixtures() -> None:
    fixture_dir = Path(__file__).parent
    scenes = [
        (
            "2011_000003.jpg",
            (500, 338),
            [
                make_shape(
                    label="amber_kite",
                    points=[
                        [55.0, 65.0],
                        [155.0, 45.0],
                        [195.0, 125.0],
                        [120.0, 185.0],
                        [45.0, 125.0],
                    ],
                ),
                make_shape(
                    label="blue_block",
                    points=[[245.0, 45.0], [355.0, 135.0]],
                    shape_type="rectangle",
                ),
                make_shape(
                    label="green_hexagon",
                    points=[
                        [80.0, 225.0],
                        [120.0, 195.0],
                        [170.0, 215.0],
                        [180.0, 275.0],
                        [135.0, 305.0],
                        [85.0, 285.0],
                    ],
                ),
                make_shape(
                    label="red_triangle",
                    points=[[270.0, 295.0], [325.0, 190.0], [385.0, 295.0]],
                ),
                make_shape(
                    label="purple_diamond",
                    points=[
                        [430.0, 170.0],
                        [480.0, 230.0],
                        [430.0, 300.0],
                        [380.0, 230.0],
                    ],
                ),
            ],
        ),
        (
            "2011_000006.jpg",
            (500, 375),
            [
                make_shape(
                    label="orange_pentagon",
                    points=[
                        [60.0, 80.0],
                        [145.0, 45.0],
                        [210.0, 110.0],
                        [170.0, 205.0],
                        [75.0, 190.0],
                    ],
                ),
                make_shape(
                    label="blue_trapezoid",
                    points=[
                        [280.0, 70.0],
                        [425.0, 90.0],
                        [390.0, 210.0],
                        [300.0, 205.0],
                    ],
                ),
                make_shape(
                    label="green_diamond",
                    points=[
                        [250.0, 235.0],
                        [320.0, 290.0],
                        [250.0, 345.0],
                        [180.0, 290.0],
                    ],
                ),
            ],
        ),
        (
            "2011_000025.jpg",
            (500, 375),
            [
                make_shape(
                    label="amber_arch",
                    points=[
                        [55.0, 300.0],
                        [85.0, 95.0],
                        [175.0, 45.0],
                        [260.0, 105.0],
                        [285.0, 300.0],
                    ],
                ),
                make_shape(
                    label="blue_marker",
                    points=[
                        [330.0, 80.0],
                        [440.0, 80.0],
                        [460.0, 180.0],
                        [385.0, 245.0],
                        [315.0, 180.0],
                    ],
                ),
            ],
        ),
    ]

    for image_name, size, shapes in scenes:
        image_bytes = render_scene(size=size, shapes=shapes)
        for directory in (fixture_dir / "annotated", fixture_dir / "raw"):
            directory.mkdir(parents=True, exist_ok=True)
            (directory / image_name).write_bytes(image_bytes)
        write_annotation(
            path=fixture_dir / "annotated" / Path(image_name).with_suffix(".json"),
            image_name=image_name,
            image_bytes=image_bytes,
            size=size,
            shapes=shapes,
            embed_image=False,
        )

    labels = sorted({shape["label"] for _, _, shapes in scenes for shape in shapes})
    (fixture_dir / "labels.txt").write_text(
        "\n".join(["__ignore__", "_background_", *labels, ""]),
        encoding="utf-8",
    )

    embedded_shapes = [
        make_shape(
            label="cyan_rectangle",
            points=[[30.0, 35.0], [145.0, 35.0], [145.0, 120.0], [30.0, 120.0]],
        ),
        make_shape(
            label="violet_triangle",
            points=[[190.0, 190.0], [245.0, 55.0], [295.0, 190.0]],
        ),
    ]
    embedded_size = (320, 240)
    embedded_bytes = render_scene(size=embedded_size, shapes=embedded_shapes)
    embedded_dir = fixture_dir / "annotated_with_data"
    embedded_dir.mkdir(parents=True, exist_ok=True)
    embedded_name = "apc2016_obj3.jpg"
    (embedded_dir / embedded_name).write_bytes(embedded_bytes)
    write_annotation(
        path=embedded_dir / Path(embedded_name).with_suffix(".json"),
        image_name=embedded_name,
        image_bytes=embedded_bytes,
        size=embedded_size,
        shapes=embedded_shapes,
        embed_image=True,
    )


def check_fixtures() -> None:
    fixture_dir = Path(__file__).parent
    for annotation_path in sorted(fixture_dir.glob("*/*.json")):
        data = json.loads(annotation_path.read_text(encoding="utf-8"))
        image_bytes = (
            base64.b64decode(data["imageData"])
            if data["imageData"] is not None
            else (annotation_path.parent / data["imagePath"]).read_bytes()
        )
        with Image.open(io.BytesIO(image_bytes)) as image:
            assert image.size == (data["imageWidth"], data["imageHeight"])
        assert data["shapes"]


if __name__ == "__main__":
    generate_fixtures()
    check_fixtures()
