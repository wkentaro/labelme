#!/usr/bin/env python


import argparse
import sys
from pathlib import Path

import imgviz
import numpy as np
from numpy.typing import NDArray

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import utils  # noqa: E402  # examples/utils.py, vendored alongside this script


def _create_output_directories(
    output_dir: Path,
    /,
    *,
    include_npy: bool,
    include_visualizations: bool,
    include_objects: bool,
) -> None:
    output_dir.mkdir(parents=True)
    (output_dir / "JPEGImages").mkdir()
    (output_dir / "SegmentationClass").mkdir()
    if include_npy:
        (output_dir / "SegmentationClassNpy").mkdir()
    if include_visualizations:
        (output_dir / "SegmentationClassVisualization").mkdir()
    if not include_objects:
        return
    (output_dir / "SegmentationObject").mkdir()
    if include_npy:
        (output_dir / "SegmentationObjectNpy").mkdir()
    if include_visualizations:
        (output_dir / "SegmentationObjectVisualization").mkdir()


def _save_label_layer(
    *,
    output_dir: Path,
    layer: str,
    base: str,
    label: NDArray[np.int32],
    gray_img: NDArray[np.uint8],
    label_names: list[str],
    include_npy: bool,
    include_visualization: bool,
) -> None:
    imgviz.io.lblsave(output_dir / layer / f"{base}.png", label.astype(np.uint8))
    if include_npy:
        np.save(output_dir / f"{layer}Npy" / f"{base}.npy", label)
    if include_visualization:
        viz = imgviz.label2rgb(
            label, gray_img, label_names=label_names, font_size=15, loc="rb"
        )
        imgviz.io.imsave(output_dir / f"{layer}Visualization" / f"{base}.jpg", viz)


def _load_class_names(labels_arg: str, /) -> tuple[list[str], dict[str, int]]:
    if Path(labels_arg).exists():
        with open(labels_arg) as f:
            labels = [label.strip() for label in f if label]
    else:
        labels = [label.strip() for label in labels_arg.split(",")]

    class_names: list[str] = []
    class_name_to_id: dict[str, int] = {}
    for i, label in enumerate(labels):
        class_id = i - 1  # starts with -1
        class_name = label.strip()
        class_name_to_id[class_name] = class_id
        if class_id == -1:
            assert class_name == "__ignore__"
            continue
        elif class_id == 0:
            assert class_name == "_background_"
        class_names.append(class_name)
    return class_names, class_name_to_id


def main() -> None:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("input_dir", help="Input annotated directory")
    parser.add_argument("output_dir", help="Output dataset directory")
    parser.add_argument(
        "--labels", help="Labels file or comma separated text", required=True
    )
    parser.add_argument(
        "--noobject", help="Flag not to generate object label", action="store_true"
    )
    parser.add_argument(
        "--nonpy", help="Flag not to generate .npy files", action="store_true"
    )
    parser.add_argument(
        "--noviz", help="Flag to disable visualization", action="store_true"
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if output_dir.exists():
        print("Output directory already exists:", output_dir)
        sys.exit(1)
    include_npy = not args.nonpy
    include_visualizations = not args.noviz
    include_objects = not args.noobject
    _create_output_directories(
        output_dir,
        include_npy=include_npy,
        include_visualizations=include_visualizations,
        include_objects=include_objects,
    )
    print("Creating dataset:", output_dir)

    class_names, class_name_to_id = _load_class_names(args.labels)
    print("class_names:", class_names)
    out_class_names_file = output_dir / "class_names.txt"
    with open(out_class_names_file, "w") as f:
        f.writelines("\n".join(class_names))
    print("Saved class_names:", out_class_names_file)

    for path in sorted(Path(args.input_dir).glob("*.json")):
        print("Generating dataset from:", path)

        label_file = utils.load_label_file(str(path))
        base = path.stem

        img = utils.decode_img_data_as_rgb(label_file.image_data)
        imgviz.io.imsave(output_dir / "JPEGImages" / f"{base}.jpg", img)

        cls, ins = utils.shapes_to_label(
            img_shape=img.shape,
            shapes=label_file.shapes,
            label_name_to_value=class_name_to_id,
        )
        ins[cls == -1] = 0  # ignore it.
        gray_img = imgviz.rgb2gray(img)

        _save_label_layer(
            output_dir=output_dir,
            layer="SegmentationClass",
            base=base,
            label=cls,
            gray_img=gray_img,
            label_names=class_names,
            include_npy=include_npy,
            include_visualization=include_visualizations,
        )

        if not include_objects:
            continue

        instance_ids = np.unique(ins)
        instance_names = [str(i) for i in range(max(instance_ids) + 1)]
        _save_label_layer(
            output_dir=output_dir,
            layer="SegmentationObject",
            base=base,
            label=ins,
            gray_img=gray_img,
            label_names=instance_names,
            include_npy=include_npy,
            include_visualization=include_visualizations,
        )


if __name__ == "__main__":
    main()
