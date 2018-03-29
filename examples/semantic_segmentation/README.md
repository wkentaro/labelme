# Semantic Segmentation Example

## Annotation

```bash
labelme data_annotated --labels="$(tr '\n' , < labels.txt)" --nodata
```

![](.readme/annotation.jpg)


## Convert to VOC-like Dataset

```bash
# It generates:
#   - data_dataset_voc/JPEGImages
#   - data_dataset_voc/SegmentationClass
#   - data_dataset_voc/SegmentationClassVisualization
./labelme2voc.py labels.txt data_annotated data_dataset_voc
```

<img src="data_dataset_voc/JPEGImages/2011_000003.jpg" width="33%" /> <img src="data_dataset_voc/SegmentationClass/2011_000003.png" width="33%" /> <img src="data_dataset_voc/SegmentationClassVisualization/2011_000003.jpg" width="33%" />

Fig 1. JPEG image (left), PNG label (center), JPEG label visualization (right)  
*Note that the reason why the label file is mostly black is it contains only very low label values (ex. `-1, 0, 4, 14`).*
