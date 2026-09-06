# Video-frame annotation

Extract a video into an ordered image directory with a tool of your choice, then open
that directory in Labelme:

```bash
labelme frames/ --labels labels.txt --keep-prev
```

`--keep-prev` seeds an unannotated frame with shapes from the preceding frame. Review
and adjust every carried shape before saving.
