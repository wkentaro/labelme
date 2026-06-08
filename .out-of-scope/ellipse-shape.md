# Ellipse / Rotated Ellipse Shape

labelme does not support an ellipse (or rotated ellipse) annotation shape.
The existing `circle` shape stays a circle; it is not being generalized into
an ellipse.

## Why this is out of scope

The demand is thin and stale. Across the project's lifetime there have been
three requests for an ellipse shape — #298 (2019), #391 (2019), #871 (2021) —
all closed, with none in the years since. PR #909 implemented a working
ellipse-fitting prototype on a branch and left it available for roughly five
years; it attracted a single user comment. Latent demand that does not convert
even when an implementation is sitting right there is weak demand.

The shape is also redundant for the practical cases. The domains that reach for
ellipses (cells, nuclei, some biology/astronomy) are already covered by
`polygon` and `mask`, both of which labelme supports and which most annotation
pipelines consume directly. An ellipse primitive would add a shape type,
serialization, rendering, mask conversion, and rotation UI for a niche that the
existing primitives already serve.

## If this is ever revisited

Do not resurrect PR #909's approach. It used `skimage.measure.EllipseModel`
fitting over a variable number of points with double-click finalize, and it
could not render rotated ellipses because the old `QPainterPath`-based renderer
had no rotated-ellipse path (the author stubbed those code paths with logger
errors).

The cheaper and more consistent direction, if needed, is to promote the
geometry already in the tree rather than fit:

- An ellipse is the inscribed ellipse of a rectangle.
- A rotated ellipse is the inscribed ellipse of an `oriented_rectangle` — which
  already carries all the rotation machinery (`oriented_rectangle_center`,
  `rotate`, `get_rotation_handle`, the direction arrow). The exact problem that
  killed #909 (rendering a rotated ellipse) is already solved by reusing that
  4-point representation.
- `circle` is already a degenerate ellipse: it rasterizes via
  `PIL.ImageDraw.ellipse` (`labelme/utils/shape.py`) and renders via
  `addEllipse(center, radius, radius)` (`labelme/widgets/_shape_render.py`). The
  lowest-cost slice would be an axis-aligned ellipse (unequal radii, no
  rotation), but it should not be built on spec.

## Prior requests

- #298 — "Guideline for adding new label shapes and enabling rotation?"
- #391 — "create rotated ellipse"
- #871 — "[adding an ellipse with rotation]"
- #909 — "Add support for rotated ellipses defined via ellipse fitting method" (PR)
