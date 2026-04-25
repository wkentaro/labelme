#!/usr/bin/env python

import argparse
from pathlib import Path

import imgviz
import numpy as np
import PIL.Image
from loguru import logger
from numpy.typing import NDArray

from labelme import utils
from labelme._label_file import LabelFile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file")
    parser.add_argument("-o", "--out", default=None)
    args = parser.parse_args()

    json_file = args.json_file

    out_dir = Path(json_file).with_suffix("") if args.out is None else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    label_file: LabelFile = LabelFile(filename=json_file)

    assert label_file.imageData is not None
    image: NDArray[np.uint8] = utils.img_data_to_arr(label_file.imageData)

    label_name_to_value: dict[str, int] = {"_background_": 0}
    for shape in sorted(label_file.shapes, key=lambda x: x["label"]):
        label_name = shape["label"]
        if label_name in label_name_to_value:
            label_value = label_name_to_value[label_name]
        else:
            label_value = len(label_name_to_value)
            label_name_to_value[label_name] = label_value
    lbl, _ = utils.shapes_to_label(image.shape, label_file.shapes, label_name_to_value)

    label_names: list[str] = [""] * (max(label_name_to_value.values()) + 1)
    for name, value in label_name_to_value.items():
        label_names[value] = name

    lbl_viz = imgviz.label2rgb(
        lbl,
        imgviz.asgray(image),  # type: ignore[arg-type]  # imgviz stub too narrow
        label_names=label_names,
        loc="rb",
    )

    PIL.Image.fromarray(image).save(out_dir / "img.png")
    imgviz.io.lblsave(out_dir / "label.png", lbl.astype(np.uint8))
    PIL.Image.fromarray(lbl_viz).save(out_dir / "label_viz.png")

    with open(out_dir / "label_names.txt", "w") as f:
        for lbl_name in label_names:
            f.write(f"{lbl_name}\n")

    logger.info(f"Saved to: {out_dir}")


if __name__ == "__main__":
    main()
