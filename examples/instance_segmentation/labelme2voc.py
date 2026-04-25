#!/usr/bin/env python


import argparse
import sys
from pathlib import Path

import imgviz
import numpy as np

import labelme


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
    output_dir.mkdir(parents=True)
    (output_dir / "JPEGImages").mkdir(parents=True)
    (output_dir / "SegmentationClass").mkdir(parents=True)
    if not args.nonpy:
        (output_dir / "SegmentationClassNpy").mkdir(parents=True)
    if not args.noviz:
        (output_dir / "SegmentationClassVisualization").mkdir(parents=True)
    if not args.noobject:
        (output_dir / "SegmentationObject").mkdir(parents=True)
        if not args.nonpy:
            (output_dir / "SegmentationObjectNpy").mkdir(parents=True)
        if not args.noviz:
            (output_dir / "SegmentationObjectVisualization").mkdir(parents=True)
    print("Creating dataset:", output_dir)

    if Path(args.labels).exists():
        with open(args.labels) as f:
            labels = [label.strip() for label in f if label]
    else:
        labels = [label.strip() for label in args.labels.split(",")]

    class_names: list[str] = []
    class_name_to_id = {}
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
    print("class_names:", class_names)
    out_class_names_file = output_dir / "class_names.txt"
    with open(out_class_names_file, "w") as f:
        f.writelines("\n".join(class_names))
    print("Saved class_names:", out_class_names_file)

    for path in sorted(Path(args.input_dir).glob("*.json")):
        print("Generating dataset from:", path)

        label_file = labelme.LabelFile(filename=str(path))

        base = path.stem
        out_img_file = output_dir / "JPEGImages" / f"{base}.jpg"
        out_clsp_file = output_dir / "SegmentationClass" / f"{base}.png"
        if not args.nonpy:
            out_cls_file = output_dir / "SegmentationClassNpy" / f"{base}.npy"
        if not args.noviz:
            out_clsv_file = (
                output_dir / "SegmentationClassVisualization" / f"{base}.jpg"
            )
        if not args.noobject:
            out_insp_file = output_dir / "SegmentationObject" / f"{base}.png"
            if not args.nonpy:
                out_ins_file = output_dir / "SegmentationObjectNpy" / f"{base}.npy"
            if not args.noviz:
                out_insv_file = (
                    output_dir / "SegmentationObjectVisualization" / f"{base}.jpg"
                )

        assert label_file.imageData is not None
        img = labelme.utils.img_data_to_arr(label_file.imageData)
        imgviz.io.imsave(out_img_file, img)

        cls, ins = labelme.utils.shapes_to_label(
            img_shape=img.shape,
            shapes=label_file.shapes,
            label_name_to_value=class_name_to_id,
        )
        ins[cls == -1] = 0  # ignore it.

        # class label
        imgviz.io.lblsave(out_clsp_file, cls.astype(np.uint8))
        if not args.nonpy:
            np.save(out_cls_file, cls)
        if not args.noviz:
            clsv = imgviz.label2rgb(
                cls,
                imgviz.rgb2gray(img),
                label_names=class_names,
                font_size=15,
                loc="rb",
            )
            imgviz.io.imsave(out_clsv_file, clsv)

        if not args.noobject:
            # instance label
            imgviz.io.lblsave(out_insp_file, ins.astype(np.uint8))
            if not args.nonpy:
                np.save(out_ins_file, ins)
            if not args.noviz:
                instance_ids = np.unique(ins)
                instance_names = [str(i) for i in range(max(instance_ids) + 1)]
                insv = imgviz.label2rgb(
                    ins,
                    imgviz.rgb2gray(img),
                    label_names=instance_names,
                    font_size=15,
                    loc="rb",
                )
                imgviz.io.imsave(out_insv_file, insv)


if __name__ == "__main__":
    main()
