# Single Image Example

## Annotation

```bash
labelme apc2016_obj3.jpg -O apc2016_obj3.json
```

![](.readme/annotation.jpg)


## Visualization

To view the json file quickly, you can use utility script:

```bash
labelme_draw_json examples/single_image/apc2016_obj3.json
```

<img src="examples/single_image/.readme/draw_json.jpg" width="70%" />


## Convert to Dataset

To convert the json to set of image and label, you can run following:


```bash
labelme_json_to_dataset examples/single_image/apc2016_obj3.json -o examples/single_image/apc2016_obj3_json
```

It generates standard files from the JSON file.

- [img.png](examples/single_image/apc2016_obj3_json/img.png): Image file.
- [label.png](examples/single_image/apc2016_obj3_json/label.png): Int32 label file.
- [label_viz.png](examples/single_image/apc2016_obj3_json/label_viz.png): Visualization of `label.png`.
- [label_names.txt](examples/single_image/apc2016_obj3_json/label_names.txt): Label names for values in `label.png`.

Note that loading `label.png` is a bit difficult
(`scipy.misc.imread`, `skimage.io.imread` may not work correctly),
and please use `PIL.Image.open` to avoid unexpected behavior:

```python
# see examples/single_image/load_label_png.py also.
>>> import numpy as np
>>> import PIL.Image

>>> label_png = 'examples/single_image/apc2016_obj3_json/label.png'
>>> lbl = np.asarray(PIL.Image.open(label_png))
>>> print(lbl.dtype)
dtype('int32')
>>> np.unique(lbl)
array([0, 1, 2, 3], dtype=int32)
>>> lbl.shape
(907, 1210)
```

