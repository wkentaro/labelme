# Three-point circles on a ring

This synthetic ring demonstrates the inner and outer boundaries discussed in
[Discussion #2724](https://github.com/wkentaro/labelme/discussions/2724).
The image was drawn for this example; it is not a photograph or a calibration
reference.

Open the saved example:

```bash
labelme examples/three_point_circle/ring.json
```

`outer_boundary` and `inner_boundary` are ordinary Circle Shapes in Group 1,
with radii of 128 and 92 image pixels. The Annotation File stores each circle
as its center and a point on its circumference, so existing readers and exports
can consume it.

To try drawing them yourself, open the image with a separate Annotation Folder:

```bash
labelme examples/three_point_circle/ring.png --output /tmp/labelme-ring-demo
```

Select **Three-Point Circle**. Click the rightmost, topmost, and leftmost points
on each boundary. The middle of the ring need not be estimated or clicked.
The second click starts a circle preview; the third finishes the Shape.
