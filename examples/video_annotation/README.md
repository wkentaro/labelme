# Video Annotation Example


## Annotation

```bash
labelme data_annotated --labels labels.txt --nodata --keep-prev --config '{shift_auto_shape_color: -2}'
```

<img src=".readme/00000100.jpg" width="49%" /> <img src=".readme/00000101.jpg" width="49%" />

*Fig 1. Video annotation example. A frame (left), The next frame (right).*


<img src=".readme/data_annotated.gif" width="98%" />

*Fig 2. Visualization of video semantic segmentation.*


## How to Convert a Video File to Images for Annotation?

```bash
pip install video-cli

video-toimg your_video.mp4  # this creates your_video/ directory
ls your_video/

labelme your_video/
```
