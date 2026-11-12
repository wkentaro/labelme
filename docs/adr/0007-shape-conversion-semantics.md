# Shape Conversion is in-place, undo-revertable, and structure-honest

Shape Conversion replaces a Shape's geometric kind in place while keeping its
identity (Label, Group, Shape Flags, description). Three semantic commitments
were made together, each against a real alternative:

1. **Revert is undo history only.** The Annotation File never stores the
   pre-conversion geometry. Storing originals would make lossy conversions
   revertable across save/reload, but bloats a file that downstream pipelines
   parse and creates stale shadow geometry once the converted Shape is edited.
2. **Mask Polygonization emits one polygon per 4-connected exterior land,
   sharing a Group when there is more than one.** A land is omitted when eroding
   its hole-filled pixels by the boundary deviation leaves no area. A bounded
   raster disk classifies every land without a full-image distance field. This
   removes small or thin lands consistently with Polygon Detail instead of
   introducing an unrelated area threshold. Keyholes were rejected because their
   visible
   seam, extra bridge points, and independently editable coincident vertices
   conflict with the goal of clean hand-editing. Holes are dropped until Polygon
   Shapes support explicit rings;
   largest-land-only was rejected as silent data loss.
3. **The Convert menu lists every Shape kind and enables a target when each
   selected Shape is either already that kind or convertible to it.** Shapes
   already of the target kind stay as they are, so Select All can bring every
   Shape to one kind in one undoable step; the kind the whole selection
   already has is checked. Targets not supported yet, or not possible, stay
   listed but dimmed with the reason, so the menu reads the same for any
   selection. Union-and-skip-invalid was rejected because the outcome
   ("converted 3, skipped 2") is unpredictable. Offering only the intersection
   of targets was rejected because it hid a target that part of the selection
   already has.

## Consequences

- A lossy conversion (e.g. polygon → rectangle) cannot be reverted after the
  undo history is gone; the menu states each lossy conversion's effect at the
  point of use instead of warning in a dialog.
- Conversion can change the Shape count (mask → N Grouped polygons). The
  reverse is 1:1 per Shape — converting Grouped polygons to masks yields one
  mask Shape per polygon; merging a Group into one Shape is a separate feature,
  not a conversion.
- Every conversion pushes its own undo snapshot; the snapshot guard that
  compares only point arrays would miss an in-place `shape_type` change.
- A route with one possible result converts at once. A route with more than
  one (circle → polygon, mask → polygon) first asks for a Polygon Detail in a
  dialog that previews the result on the canvas, and its menu item ends with
  an ellipsis. This dialog collects an input, so it is not the warning dialog
  ruled out above. Its value is remembered apart from the AI Assist Setting,
  so tuning AI-Segment output never changes what Convert To produces.
- A Conversion never deletes a Shape. When a Polygon Detail would omit every
  land of a mask, the mask keeps its exact outline (detail 100) instead. Split
  polygons keep the mask's Group when it had one, and otherwise share a new
  one.
