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
- Repeated auto-save failures show one error until a save succeeds or the target
  path changes, instead of interrupting every edit.
- Loading and validation use staged state; the visible session changes only
  after the replacement Image and Annotation are ready.
- A corrupt adjacent Annotation File blocks opening its Image instead of
  silently opening an empty Annotation that could overwrite recoverable data.
- Successful saves do not leave persistent backup files. Recovery history, its
  retention, and its cleanup belong to a separate feature.
