# Annotation points may extend beyond the image extent

Historically every interactive canvas path clamped a Shape's points to the image
rectangle, so a committed point was guaranteed to lie within the Image. The
opt-in Setting `canvas.allow_out_of_bounds_points` (default `false`, preserving
the clamp) relaxes that guarantee: when on, drawing, vertex editing, whole-shape
dragging, oriented-rectangle reprojection, and the crosshair all let points sit
outside the image. This lets an annotator place corners at a partially-visible
object's true extent (e.g. an object cut off by the camera's field of view),
which the visible-only box cannot represent.

The on-disk format needs no change: points already serialize as plain floats, so
negative or larger-than-image coordinates round-trip, and loading already
preserves them (the old clamp only fired on *edit*, never on load).

## Considered options

- **Always clamp; treat partial visibility as unsupported** (rejected): the
  visible-only box is wrong ground truth for detection datasets where the object
  extent is known, which is the reported use case.
- **Allow out-of-bounds unconditionally** (rejected): silently changes behavior
  for every existing user and lets stray points escape the image by accident. An
  opt-in Setting keeps the safe default and confines the new behavior to users
  who want it.

## Consequences

- The canvas no longer guarantees in-image points when the Setting is on. A
  future refactor must not re-introduce a blanket clamp "for safety", which
  silently breaks this feature. The clamps are gated, not removed.
- Rasterization and export tooling (`shape_to_mask`, the labelme2coco /
  labelme2voc examples) clip to the image canvas rather than reject
  out-of-bounds coordinates, so masks and exports keep working; pixels outside
  the image simply do not exist to rasterize.
