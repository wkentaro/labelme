# Bounding-box conversion

Create a directory of images, annotate each object with a rectangle, and keep the
allowed class names in `labels.txt`:

```bash
labelme images/ --labels labels.txt
uv run --with lxml ./labelme2voc.py images/ dataset/ --labels labels.txt
```

The converter writes JPEG copies, VOC XML annotations, and optional visualization
images below `dataset/`.
