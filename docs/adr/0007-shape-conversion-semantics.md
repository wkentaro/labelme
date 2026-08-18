# Shape Conversion is in-place, undo-revertable, and structure-honest

Shape Conversion replaces a Shape's geometric kind in place while keeping its
identity (Label, Group, Shape Flags, description). Three semantic commitments
were made together, each against a real alternative:

1. **Revert is undo history only.** The Annotation File never stores the
   pre-conversion geometry. Storing originals would make lossy conversions
   revertable across save/reload, but bloats a file that downstream pipelines
   parse and creates stale shadow geometry once the converted Shape is edited.
2. **A multi-part mask converts to one polygon per connected region, sharing a
   Group when there is more than one.** The keyhole alternative (one
   self-touching polygon joined by zero-width bridges, as COCO encodes
   multi-part masks) preserves regions and holes but is hostile to hand-editing
   — the primary reason users convert. Largest-region-only was rejected as
   silent data loss. Holes are dropped either way; polygons cannot represent
   them.
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
