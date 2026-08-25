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
3. **With multiple Shapes selected, the Convert menu offers the intersection of
   targets valid for every selected Shape and converts them all in one undoable
   step.** Union-and-skip-invalid offers more entries but makes the outcome
   ("converted 3, skipped 2") unpredictable.

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
