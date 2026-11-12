# Polygon Detail is relative to a Shape's thickness

Polygon Detail sets how far a polygon may stray from the Shape it comes from,
as a fraction of that Shape's thickness: its area divided by its perimeter.
The IoU a polygon loses grows with that fraction, so one Polygon Detail keeps
alike a Shape of any size on an Image of any resolution. The same rule serves
Mask Polygonization, for AI Assist and for Shape Conversion, and circle →
polygon, where the thickness is half the radius.

Polygon Detail 100 keeps the exact outline. At 0 the fraction is 0.15, the
largest that keeps every shape tried at an IoU of 0.95: past it a circle
drops to an octagon (IoU 0.90). A circle therefore never gets fewer than 12
vertices.

A mask with several lands takes one thickness: each land's area / perimeter,
weighted by its area, so specks and pepper noise don't thin it out. Both are
counted from pixels, so tens of thousands of specks cost no trace each. Lands are
omitted with that same deviation, so a land much thinner than the mask goes,
while a thin mask alone, such as a wire, stays.

A mask's outline is only accurate to half a pixel, so below Polygon Detail 100
the deviation is never less than the pixel stair steps, up to half a pixel.
This is the one place pixels enter the rule.

## Considered options

- **Image pixels** (the previous rule): at Polygon Detail 34 the same dog
  mask got 13 vertices on an Image a sixth the size and 236 on one four times
  as large, and a 4-pixel-wide wire was omitted. Thickness gives 31, 31, and
  33 vertices, and keeps the wire.
- **Screen pixels at the current zoom**, as drawing by drag simplifies a
  stroke: the saved polygon would depend on how far the user had zoomed in,
  so the accuracy of the data would follow the view. Drawing by drag keeps
  screen pixels, because what it removes is hand jitter, which happens on the
  screen.
- **The mask's bounding-box diagonal or the square root of its area**: both
  follow the Shape's size but not its thickness, so thin Shapes such as poles
  and wires lost their width or were omitted.
- **A vertex count**: too many vertices for simple Shapes and too few for
  complex ones.
- **Searching for the smallest polygon that keeps a target IoU**: the most
  direct, but it simplifies many times per Polygon Detail. Thickness gets
  close in one pass.

## Consequences

- A Polygon Detail saved before this change gives different polygons after
  it: coarser on large, high-resolution Shapes, finer on small ones.
- The fraction 0.15 and the 12-vertex minimum come from the circle's octagon
  limit. Changing the curve needs that check again.
