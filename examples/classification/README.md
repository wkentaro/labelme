# Image classification

Image-level flags can represent classes or review states. Put one flag name per line
in `flags.txt`, then open a directory containing your own images:

```bash
labelme images/ --flags flags.txt
```

The checked values are stored in the top-level `flags` object of each annotation.
