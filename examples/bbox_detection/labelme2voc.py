#!/usr/bin/env python


import argparse
import sys
from pathlib import Path

import imgviz

import labelme

try:
    import lxml.builder  # type: ignore
    import lxml.etree  # type: ignore
except ImportError:
    print("Please install lxml:\n\n    pip install lxml\n")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("input_dir", help="input annotated directory")
    parser.add_argument("output_dir", help="output dataset directory")
    parser.add_argument("--labels", help="labels file", required=True)
    parser.add_argument("--noviz", help="no visualization", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if output_dir.exists():
        print("Output directory already exists:", output_dir)
        sys.exit(1)
    output_dir.mkdir(parents=True)
    (output_dir / "JPEGImages").mkdir(parents=True)
    (output_dir / "Annotations").mkdir(parents=True)
    if not args.noviz:
        (output_dir / "AnnotationsVisualization").mkdir(parents=True)
    print("Creating dataset:", output_dir)

    class_names = []
    class_name_to_id = {}
    for i, line in enumerate(open(args.labels).readlines()):
        class_id = i - 1  # starts with -1
        class_name = line.strip()
        class_name_to_id[class_name] = class_id
        if class_id == -1:
            assert class_name == "__ignore__"
            continue
        elif class_id == 0:
            assert class_name == "_background_"
        class_names.append(class_name)
    class_names = tuple(class_names)
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
        out_xml_file = output_dir / "Annotations" / f"{base}.xml"
        if not args.noviz:
            out_viz_file = output_dir / "AnnotationsVisualization" / f"{base}.jpg"

        assert label_file.image_data is not None
        img = labelme.utils.img_data_to_arr(label_file.image_data)
        imgviz.io.imsave(out_img_file, img)

        maker = lxml.builder.ElementMaker()
        xml = maker.annotation(
            maker.folder(),
            maker.filename(f"{base}.jpg"),
            maker.database(),  # e.g., The VOC2007 Database
            maker.annotation(),  # e.g., Pascal VOC2007
            maker.image(),  # e.g., flickr
            maker.size(
                maker.height(str(img.shape[0])),
                maker.width(str(img.shape[1])),
                maker.depth(str(img.shape[2])),
            ),
            maker.segmented(),
        )

        bboxes: list[list[float]] = []
        labels = []
        for shape in label_file.shapes:
            if shape["shape_type"] != "rectangle":
                print(
                    "Skipping shape: label={label}, shape_type={shape_type}".format(
                        **shape
                    )
                )
                continue

            class_name = shape["label"]
            class_id = class_names.index(class_name)

            (xmin, ymin), (xmax, ymax) = shape["points"]
            # swap if min is larger than max.
            xmin, xmax = sorted([xmin, xmax])
            ymin, ymax = sorted([ymin, ymax])

            bboxes.append([ymin, xmin, ymax, xmax])
            labels.append(class_id)

            xml.append(
                maker.object(
                    maker.name(shape["label"]),
                    maker.pose(),
                    maker.truncated(),
                    maker.difficult(),
                    maker.bndbox(
                        maker.xmin(str(xmin)),
                        maker.ymin(str(ymin)),
                        maker.xmax(str(xmax)),
                        maker.ymax(str(ymax)),
                    ),
                )
            )

        if not args.noviz:
            captions: list[str] = [class_names[label] for label in labels]
            viz = imgviz.instances2rgb(
                image=img,
                labels=labels,
                bboxes=bboxes,
                captions=captions,
                font_size=15,
            )
            imgviz.io.imsave(out_viz_file, viz)

        with open(out_xml_file, "wb") as f:
            f.write(lxml.etree.tostring(xml, pretty_print=True))


if __name__ == "__main__":
    main()
