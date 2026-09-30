# Annotation transitions preserve the last good state

Saving and navigation replace an Annotation only after the replacement is
complete and valid. Saving writes a complete temporary file in the target
directory and atomically replaces the previous Annotation File without forcing
an `fsync` on every auto-save; failed navigation keeps the current Image,
Annotation, and File List selection active. This favors protection from partial
writes and failed loads without adding physical-storage latency to every edit.

## Consequences

- A failed save leaves the previous Annotation File intact and the in-memory
  Annotation dirty.
- Auto-save failures remain visible in the status bar with Retry, without
  interrupting editing. The next edit or an explicit retry attempts another save;
  there is no retry timer.
- Loading and validation use staged state; the visible session changes only
  after the replacement Image and Annotation are ready.
- A corrupt adjacent Annotation File blocks opening its Image instead of
  silently opening an empty Annotation that could overwrite recoverable data.
- Successful saves do not leave persistent backup files. Recovery history, its
  retention, and its cleanup belong to a separate feature.

## Background auto-save

Auto-save captures owned annotation values on the GUI thread, then uses one
worker thread for encoding and the existing atomic write. A newer pending
snapshot replaces an older pending snapshot; undo history remains independent.
Only successful completion of the latest edit revision clears the dirty marker.

A thread keeps the worker small and avoids copying embedded image bytes between
processes. Encoding can still hold the Python GIL briefly; a process worker is
reserved for measured event-loop stalls that exceed the interaction budget.

Navigation, close, and output-directory changes wait for queued saves, then use
the existing Save/Discard/Cancel decision if the latest save failed. Manual Save
and Save As discard superseded pending work and wait for the active write before
writing the latest snapshot. Delete waits for the active writer before unlinking,
so a late completion cannot recreate the deleted Annotation File. Save As sets
the auto-save destination for the current document.

The status bar distinguishes Saving, Saved, and Save failed. A failure retries
only on another edit or explicit Retry. The pending interval is not crash
durability; no recovery journal or per-edit fsync is added.
