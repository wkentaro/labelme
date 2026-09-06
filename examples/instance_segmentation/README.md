# Instance-segmentation conversion

Annotate closed object regions in a directory of your own images:

```bash
labelme images/ --labels labels.txt --validate-label exact
```

Generate a VOC-style dataset:

```bash
./labelme2voc.py images/ dataset-voc/ --labels labels.txt
```

The result includes class masks, instance masks, NumPy arrays, and optional preview
images. To omit selected outputs, pass `--noobject`, `--nonpy`, or `--noviz`.

Generate COCO JSON instead:

```bash
uv run --with pycocotools ./labelme2coco.py images/ dataset-coco/ --labels labels.txt
```
