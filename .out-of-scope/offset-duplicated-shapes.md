# Offset Duplicated / Pasted Shapes

labelme places a duplicated or pasted shape at exactly the source coordinates.
The copy is not nudged, shifted, or otherwise offset to make it visible, and
there is no setting to turn such an offset on.

## Why this is out of scope

An in-place copy is a deliberate workflow, not an oversight. A common pattern
is to duplicate a shape and then edit the copy — change its label, flags, or
group id, or trim a few vertices — while keeping the geometry identical to the
source. Any automatic offset destroys that: the user would have to drag the
copy back onto the source by hand and could never recover the exact
coordinates. Copy/Paste across images relies on the same guarantee to transfer
annotations between frames of one scene.

The cost of the current behavior is discoverability: a copy hidden under its
source can be stacked without the user noticing. That is a visibility problem,
and the acceptable answers to it are ones that do not move the copy — a
selection highlight, a shape-list entry, or a status-bar hint. Making the offset
a setting was considered and rejected too: it adds a mode that changes where
saved geometry lands depending on configuration, for a problem the label list
already surfaces.

PR #2536 implemented a full placement search (zoom-scaled step, in-bounds
clamping, widen-then-narrow search for a free slot) and was closed for this
reason, not for code quality.

## Prior requests

- #2527 — "fix(canvas): offset duplicated and pasted shapes" (QA finding)
- #2536 — "fix: offset duplicated and pasted shapes" (PR, closed)
