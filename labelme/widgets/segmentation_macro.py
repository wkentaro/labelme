from qtpy.QtWidgets import *
import glob
import labelme
import imgviz
import os.path as osp
import os
import numpy as np
import datetime
import collections
import json
import uuid


class GenerateSegmentedData(QWidget):
    def __init__(self):
        super(GenerateSegmentedData, self).__init__()
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.input_directory = LineEntry("labeled data directory", QFileDialog.DirectoryOnly)
        self.output_directory = LineEntry("output directory", QFileDialog.DirectoryOnly)
        self.labels_file = LineEntry("labels file", QFileDialog.ExistingFile)
        self.output_visualization = QRadioButton('Create visualization output')
        self.output_visualization.setChecked(True)

        button_layout = QHBoxLayout()
        button_widget = QWidget()
        button_widget.setLayout(button_layout)
        voc_semantic_seg_btn = QPushButton('VOC Semantic\nSegmentation')
        voc_semantic_seg_btn.pressed.connect(self.do_semantic_segmentation_voc)
        button_layout.addWidget(voc_semantic_seg_btn)
        voc_instance_seg_btn = QPushButton('VOC Instance\nSegmentation')
        voc_instance_seg_btn.pressed.connect(self.do_instance_segmentation_voc)
        button_layout.addWidget(voc_instance_seg_btn)
        coco_instance_seg_btn = QPushButton('COCO Instance\nSegmentation')
        coco_instance_seg_btn.pressed.connect(self.do_instance_segmentation_coco)
        button_layout.addWidget(coco_instance_seg_btn)

        layout.addWidget(self.input_directory)
        layout.addWidget(self.labels_file)
        layout.addWidget(self.output_directory)
        layout.addWidget(self.output_visualization)
        layout.addWidget(button_widget)

    def retrieve_labels(self, file):
        labels = open(file).readlines()
        # ensure that the labels start with ignore and background
        try:
            labels.remove('__ignore__')
        except ValueError:
            pass
        try:
            labels.remove('_background_')
        except ValueError:
            pass
        new_labels = ['__ignore__', '_background_']
        new_labels.extend(labels)
        class_names = []
        class_name_to_id = {}
        for i, line in enumerate(new_labels):
            class_id = i - 1  # starts with -1
            class_name = line.strip()
            class_name_to_id[class_name] = class_id
            if class_id == -1:
                assert class_name == "__ignore__"
                continue
            elif class_id == 0:
                assert class_name == "_background_"
            class_names.append(class_name)

        return tuple(class_names), class_name_to_id

    def do_semantic_segmentation_voc(self):
        output_dir = self.output_directory.line_edit.text()
        input_dir = self.input_directory.line_edit.text()
        labels = self.labels_file.line_edit.text()
        noviz = not self.output_visualization.isChecked()

        if '' in [output_dir, input_dir, labels]:
            return
        if len(os.listdir(output_dir)) > 0:
            diag = QMessageBox()
            diag.setText("Output directory must be empty")
            diag.exec()
            return

        os.makedirs(osp.join(output_dir, "JPEGImages"))
        os.makedirs(osp.join(output_dir, "SegmentationClass"))
        os.makedirs(osp.join(output_dir, "SegmentationClassPNG"))
        if not noviz:
            os.makedirs(
                osp.join(output_dir, "SegmentationClassVisualization")
            )

        class_names, class_name_to_id = self.retrieve_labels(labels)
        out_class_names_file = osp.join(output_dir, "class_names.txt")
        with open(out_class_names_file, "w") as f:
            f.writelines("\n".join(class_names))

        for filename in glob.glob(osp.join(input_dir, "*.json")):
            label_file = labelme.LabelFile(filename=filename)
            base = osp.splitext(osp.basename(filename))[0]
            out_img_file = osp.join(output_dir, "JPEGImages", base + ".jpg")
            out_lbl_file = osp.join(
                output_dir, "SegmentationClass", base + ".npy"
            )
            out_png_file = osp.join(
                output_dir, "SegmentationClassPNG", base + ".png"
            )
            if not noviz:
                out_viz_file = osp.join(
                    output_dir,
                    "SegmentationClassVisualization",
                    base + ".jpg",
                )

            with open(out_img_file, "wb") as f:
                f.write(label_file.imageData)
            img = labelme.utils.img_data_to_arr(label_file.imageData)

            lbl, _ = labelme.utils.shapes_to_label(
                img_shape=img.shape,
                shapes=label_file.shapes,
                label_name_to_value=class_name_to_id,
            )
            labelme.utils.lblsave(out_png_file, lbl)

            np.save(out_lbl_file, lbl)

            if not noviz:
                viz = imgviz.label2rgb(
                    label=lbl,
                    img=imgviz.rgb2gray(img),
                    font_size=15,
                    label_names=class_names,
                    loc="rb",
                )
                imgviz.io.imsave(out_viz_file, viz)

        self.hide()

    def do_instance_segmentation_voc(self):
        output_dir = self.output_directory.line_edit.text()
        input_dir = self.input_directory.line_edit.text()
        labels = self.labels_file.line_edit.text()
        noviz = not self.output_visualization.isChecked()

        if '' in [output_dir, input_dir, labels]:
            return
        if len(os.listdir(output_dir)) > 0:
            diag = QMessageBox()
            diag.setText("Output directory must be empty")
            diag.exec()
            return
        
        os.makedirs(osp.join(output_dir, "JPEGImages"))
        os.makedirs(osp.join(output_dir, "SegmentationClass"))
        os.makedirs(osp.join(output_dir, "SegmentationClassPNG"))
        if not noviz:
            os.makedirs(
                osp.join(output_dir, "SegmentationClassVisualization")
            )
        os.makedirs(osp.join(output_dir, "SegmentationObject"))
        os.makedirs(osp.join(output_dir, "SegmentationObjectPNG"))
        if not noviz:
            os.makedirs(
                osp.join(output_dir, "SegmentationObjectVisualization")
            )

        class_names, class_name_to_id = self.retrieve_labels(labels)
        out_class_names_file = osp.join(output_dir, "class_names.txt")
        with open(out_class_names_file, "w") as f:
            f.writelines("\n".join(class_names))

        for filename in glob.glob(osp.join(input_dir, "*.json")):
            label_file = labelme.LabelFile(filename=filename)
            base = osp.splitext(osp.basename(filename))[0]
            out_img_file = osp.join(output_dir, "JPEGImages", base + ".jpg")
            out_cls_file = osp.join(
                output_dir, "SegmentationClass", base + ".npy"
            )
            out_clsp_file = osp.join(
                output_dir, "SegmentationClassPNG", base + ".png"
            )
            if not noviz:
                out_clsv_file = osp.join(
                    output_dir,
                    "SegmentationClassVisualization",
                    base + ".jpg",
                )
            out_ins_file = osp.join(
                output_dir, "SegmentationObject", base + ".npy"
            )
            out_insp_file = osp.join(
                output_dir, "SegmentationObjectPNG", base + ".png"
            )
            if not noviz:
                out_insv_file = osp.join(
                    output_dir,
                    "SegmentationObjectVisualization",
                    base + ".jpg",
                )

            img = labelme.utils.img_data_to_arr(label_file.imageData)
            imgviz.io.imsave(out_img_file, img)

            cls, ins = labelme.utils.shapes_to_label(
                img_shape=img.shape,
                shapes=label_file.shapes,
                label_name_to_value=class_name_to_id,
            )
            ins[cls == -1] = 0  # ignore it.

            # class label
            labelme.utils.lblsave(out_clsp_file, cls)
            np.save(out_cls_file, cls)
            if not noviz:
                clsv = imgviz.label2rgb(
                    label=cls,
                    img=imgviz.rgb2gray(img),
                    label_names=class_names,
                    font_size=15,
                    loc="rb",
                )
                imgviz.io.imsave(out_clsv_file, clsv)

            # instance label
            labelme.utils.lblsave(out_insp_file, ins)
            np.save(out_ins_file, ins)
            if not noviz:
                instance_ids = np.unique(ins)
                instance_names = [str(i) for i in range(max(instance_ids) + 1)]
                insv = imgviz.label2rgb(
                    label=ins,
                    img=imgviz.rgb2gray(img),
                    label_names=instance_names,
                    font_size=15,
                    loc="rb",
                )
                imgviz.io.imsave(out_insv_file, insv)
        self.hide()
    
    def do_instance_segmentation_coco(self):
        try:
            import pycocotools.mask
        except ImportError:
            diag = QMessageBox()
            diag.setText("Please install pycocotools:\n\n    pip install pycocotools\n")
            diag.exec()
            return

        output_dir = self.output_directory.line_edit.text()
        input_dir = self.input_directory.line_edit.text()
        labels = self.labels_file.line_edit.text()
        noviz = not self.output_visualization.isChecked()

        if '' in [output_dir, input_dir, labels]:
            return
        if len(os.listdir(output_dir)) > 0:
            diag = QMessageBox()
            diag.setText("Output directory must be empty")
            diag.exec()
            return
        os.makedirs(osp.join(output_dir, "JPEGImages"))
        if not noviz:
            os.makedirs(osp.join(output_dir, "Visualization"))
        print("Creating dataset:", output_dir)

        now = datetime.datetime.now()

        data = dict(
            info=dict(
                description=None,
                url=None,
                version=None,
                year=now.year,
                contributor=None,
                date_created=now.strftime("%Y-%m-%d %H:%M:%S.%f"),
            ),
            licenses=[dict(url=None, id=0, name=None, )],
            images=[
                # license, url, file_name, height, width, date_captured, id
            ],
            type="instances",
            annotations=[
                # segmentation, area, iscrowd, image_id, bbox, category_id, id
            ],
            categories=[
                # supercategory, id, name
            ],
        )

        labels = open(labels).readlines()
        # ensure that the labels start with ignore and background
        try:
            labels.remove('__ignore__')
        except ValueError:
            pass
        try:
            labels.remove('_background_')
        except ValueError:
            pass
        new_labels = ['__ignore__', '_background_']
        new_labels.extend(labels)
        class_name_to_id = {}
        for i, line in enumerate(new_labels):
            class_id = i - 1  # starts with -1
            class_name = line.strip()
            if class_id == -1:
                assert class_name == "__ignore__"
                continue
            class_name_to_id[class_name] = class_id
            data["categories"].append(
                dict(supercategory=None, id=class_id, name=class_name, )
            )

        out_ann_file = osp.join(output_dir, "annotations.json")
        label_files = glob.glob(osp.join(input_dir, "*.json"))
        for image_id, filename in enumerate(label_files):
            print("Generating dataset from:", filename)

            label_file = labelme.LabelFile(filename=filename)

            base = osp.splitext(osp.basename(filename))[0]
            out_img_file = osp.join(output_dir, "JPEGImages", base + ".jpg")

            img = labelme.utils.img_data_to_arr(label_file.imageData)
            imgviz.io.imsave(out_img_file, img)
            data["images"].append(
                dict(
                    license=0,
                    url=None,
                    file_name=osp.relpath(out_img_file, osp.dirname(out_ann_file)),
                    height=img.shape[0],
                    width=img.shape[1],
                    date_captured=None,
                    id=image_id,
                )
            )

            masks = {}  # for area
            segmentations = collections.defaultdict(list)  # for segmentation
            for shape in label_file.shapes:
                points = shape["points"]
                label = shape["label"]
                group_id = shape.get("group_id")
                shape_type = shape.get("shape_type", "polygon")
                mask = labelme.utils.shape_to_mask(
                    img.shape[:2], points, shape_type
                )

                if group_id is None:
                    group_id = uuid.uuid1()

                instance = (label, group_id)

                if instance in masks:
                    masks[instance] = masks[instance] | mask
                else:
                    masks[instance] = mask

                if shape_type == "rectangle":
                    (x1, y1), (x2, y2) = points
                    x1, x2 = sorted([x1, x2])
                    y1, y2 = sorted([y1, y2])
                    points = [x1, y1, x2, y1, x2, y2, x1, y2]
                else:
                    points = np.asarray(points).flatten().tolist()

                segmentations[instance].append(points)
            segmentations = dict(segmentations)

            for instance, mask in masks.items():
                cls_name, group_id = instance
                if cls_name not in class_name_to_id:
                    continue
                cls_id = class_name_to_id[cls_name]

                mask = np.asfortranarray(mask.astype(np.uint8))
                mask = pycocotools.mask.encode(mask)
                area = float(pycocotools.mask.area(mask))
                bbox = pycocotools.mask.toBbox(mask).flatten().tolist()

                data["annotations"].append(
                    dict(
                        id=len(data["annotations"]),
                        image_id=image_id,
                        category_id=cls_id,
                        segmentation=segmentations[instance],
                        area=area,
                        bbox=bbox,
                        iscrowd=0,
                    )
                )

            if not noviz:
                try:
                    labels, captions, masks = zip(
                        *[
                            (class_name_to_id[cnm], cnm, msk)
                            for (cnm, gid), msk in masks.items()
                            if cnm in class_name_to_id
                        ]
                    )
                    viz = imgviz.instances2rgb(
                        image=img,
                        labels=labels,
                        masks=masks,
                        captions=captions,
                        font_size=15,
                        line_width=2,
                    )
                    out_viz_file = osp.join(
                        output_dir, "Visualization", base + ".jpg"
                    )
                    imgviz.io.imsave(out_viz_file, viz)
                except ValueError as e:
                    print(f'Failed to create visualization for {base}.jpg')

        with open(out_ann_file, "w") as f:
            json.dump(data, f)
        self.hide()


class LineEntry(QWidget):
    def __init__(self, label, dialogue_type):
        super(LineEntry, self).__init__()
        self.dialogue_type = dialogue_type
        if dialogue_type == QFileDialog.DirectoryOnly:
            btn_text = 'Select Folder'
        else:
            btn_text = 'Select File'
        layout = QHBoxLayout()
        self.label = QLabel()
        self.label.setText(label)
        self.line_edit = QLineEdit()
        self.line_edit.setMinimumWidth(300)
        self.select_folder_btn = QPushButton(btn_text)
        self.select_folder_btn.pressed.connect(self.select_folder_dialogue)
        layout.addWidget(self.label)
        layout.addWidget(self.line_edit)
        layout.addWidget(self.select_folder_btn)
        self.setLayout(layout)

    def select_folder_dialogue(self):
        dialogue = QFileDialog()
        dialogue.setFileMode(self.dialogue_type)
        accepted = dialogue.exec()
        if accepted == QDialog.Accepted:
            self.line_edit.setText(dialogue.selectedFiles()[0])