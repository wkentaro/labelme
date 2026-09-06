# Semantic-segmentation conversion

Annotate closed regions in a directory of your own images, then convert them:

```bash
labelme images/ --labels labels.txt --validate-label exact
./labelme2voc.py images/ dataset/ --labels labels.txt --noobject
```

The converter writes class masks, NumPy arrays, copied images, and visualization
images. Pass `--nonpy` to omit NumPy arrays or `--noviz` to omit visualizations.

Label PNG files use unsigned bytes. The ignore class is stored as `255` in PNG output
and `-1` in NumPy output.
