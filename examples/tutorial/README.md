# Annotation-format tutorial

Start with any image you are allowed to use:

```bash
labelme sample.jpg
```

After saving `sample.json`, inspect or render it with the standalone example tools:

```bash
./draw_json.py sample.json
./export_json.py sample.json
```

The export command creates an image, an indexed label PNG, a label-name text file,
and a visualization. Load the indexed PNG directly with Pillow:

```python
import numpy as np
from PIL import Image

labels = np.asarray(Image.open("sample/label.png"))
print(labels.dtype, labels.shape, np.unique(labels))
```

The helper accepts explicit paths for the PNG and label-name file:

```bash
python load_label_png.py sample/label.png sample/label_names.txt
```
