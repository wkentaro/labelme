# Labelme GUI QA scenarios

## Contents

- [Coverage rules](#coverage-rules)
- [Environment matrix](#environment-matrix)
- [Startup and opening](#startup-and-opening)
- [Annotation creation](#annotation-creation)
- [Selection and editing](#selection-and-editing)
- [Navigation and viewport](#navigation-and-viewport)
- [Saving, recovery, and destructive actions](#saving-recovery-and-destructive-actions)
- [Settings, themes, and native chrome](#settings-themes-and-native-chrome)
- [Accessibility and visual quality](#accessibility-and-visual-quality)
- [AI Assist, opt-in network lane](#ai-assist-opt-in-network-lane)
- [Exploratory charter](#exploratory-charter)

## Coverage rules

Scenario IDs are stable. Add an ID when a distinct user risk appears; preserve old IDs in
reports. `S` is smoke, `N` nightly, `W` weekly, and `R` release. A higher profile includes
all lower profiles.

The matrix is deliberately risk-based rather than a Cartesian product. Run the named
combinations, then add scenarios for changed code. Pairwise coverage is acceptable for
low-risk combinations; data integrity, destructive actions, recovery, and first-run paths
receive direct coverage.

## Environment matrix

| Dimension     | Smoke           | Nightly                              | Weekly                        | Release                               |
| ------------- | --------------- | ------------------------------------ | ----------------------------- | ------------------------------------- |
| Lane          | source          | source                               | source + available package    | packaged on each target OS            |
| Profile state | clean           | clean                                | clean + returning             | clean + returning                     |
| Theme         | system          | light + dark                         | system + light + dark         | system + light + dark                 |
| Locale        | system          | system                               | system + one non-English      | system + one non-English per OS       |
| Window        | default         | default + small                      | default + small + full screen | native sizes and scale factors        |
| Input         | raw + annotated | raw + annotated + sequence + corrupt | all prepared + stress         | all prepared + target-native paths    |
| Network       | off             | off                                  | AI lane opt-in                | offline + AI lane when release-scoped |

Record display scale. Weekly covers at least one non-100% scale where the OS supports it.

## Startup and opening

| ID  | Tier | Journey                                                                 | Required oracle                                                                   |
| --- | ---- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| S01 | S    | Launch with a clean profile and no path                                 | One usable main window; empty state explains the next action; no unexpected modal |
| S02 | S    | Launch on a raw image directory                                         | First image, file count, enabled tools, and status are coherent                   |
| S03 | S    | Launch on an annotated JSON or directory                                | Shapes, labels, visibility, title, and file selection agree                       |
| S04 | N    | Open an image with the toolbar and native dialog                        | Dialog path, cancel behavior, loaded image, and recent directory are coherent     |
| S05 | N    | Open a directory, cancel once, then choose it                           | Cancel preserves the current session; success populates a navigable file list     |
| S06 | N    | Drag an image and then a label JSON into the app                        | Each supported drop target opens without losing the last good state on failure    |
| S07 | W    | Launch with a path containing spaces and non-ASCII characters           | Title, file list, save path, and restart preserve the exact path                  |
| S08 | R    | Launch the packaged artifact from the native shell and file association | Bundle identity, icon, app name, menus, and initial path are native and correct   |

## Annotation creation

| ID  | Tier | Journey                                                               | Required oracle                                                                          |
| --- | ---- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| A01 | S    | On a raw image, create the first rectangle, accept a label, then undo | Active mode is understandable; undo removes the first shape visually and from saved JSON |
| A02 | N    | Cancel the first point and cancel the label dialog                    | No partial shape, label, dirty marker, or output survives                                |
| A03 | N    | Create a polygon and finish by every advertised method                | Vertices, completion affordance, dialog, and saved polygon agree                         |
| A04 | N    | Create a rectangle by the visible/expected gesture and with Shift     | Gesture guidance is clear; normal rectangle and constrained square save correctly        |
| A05 | N    | Create circle, point, line, and line strip                            | Each mode advertises completion and saves the correct shape type and points              |
| A06 | W    | Create an oriented rectangle, rotate it, and cross image bounds       | Handles, rotation feedback, clipping policy, undo, and saved points agree                |
| A07 | W    | Reuse a label from Label List with the popup on and off               | Selection, popup behavior, label history, and saved labels are predictable               |
| A08 | W    | Create with flags, group ID, and description                          | Dialog fields are named, keyboard reachable, preserved after edit, and serialized        |
| A09 | W    | Attempt an invalid exact-validated label                              | Prevention explains the constraint and preserves the in-progress work safely             |
| A10 | R    | Create every shape type with mouse and keyboard-supported completion  | Packaged behavior and shortcuts match the source contract                                |

## Selection and editing

| ID  | Tier | Journey                                                | Required oracle                                                                          |
| --- | ---- | ------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| E01 | S    | Select a shape on canvas and in Annotation List        | Canvas highlight, list selection, handles, and action enablement agree                   |
| E02 | N    | Move and resize a shape, then undo                     | Preview is smooth; saved geometry changes; undo restores exact geometry                  |
| E03 | N    | Multi-select, move, hide, and show shapes              | Selection is preserved where promised and every surface reports visibility consistently  |
| E04 | N    | Copy, paste, duplicate, and delete a selection         | Action states, offsets, labels, undo, and serialized shape count agree                   |
| E05 | N    | Add and remove a polygon edge point                    | Hit target, cursor, shape validity, undo, and saved vertices agree                       |
| E06 | W    | Change label, flags, group ID, and description         | Edit dialog reflects current values and updates all visible and saved surfaces           |
| E07 | W    | Reorder annotation rows                                | Canvas stacking, selection, saved ordering, and undo behavior agree                      |
| E08 | W    | Right-click canvas and list with and without selection | Context actions match state, menus dismiss normally, and destructive actions are guarded |

## Navigation and viewport

| ID  | Tier | Journey                                                              | Required oracle                                                                            |
| --- | ---- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| N01 | S    | Move to next and previous images with toolbar and shortcuts          | Image, title counter, row selection, annotations, and focus advance together               |
| N02 | N    | Filter files, navigate filtered results, then clear the query        | Search semantics are discoverable; selection and session survive filtering                 |
| N03 | N    | Zoom with controls, wheel shortcut, fit window, fit width, and reset | Zoom value, canvas position, enabled state, and image sharpness remain coherent            |
| N04 | N    | Pan with middle drag and scroll bars at multiple zooms               | Cursor, direction, bounds, and post-drag click behavior are predictable                    |
| N05 | N    | Adjust brightness/contrast, cancel, apply, and navigate              | Preview, reset/cancel, keep-previous setting, and annotation geometry remain intact        |
| N06 | W    | Resize to the minimum practical window and restore                   | Essential actions remain reachable; overflow affordances, docks, and status do not overlap |
| N07 | W    | Toggle docks, float one, enter full screen, and reset layout         | State is visible, reversible, and persists only in the isolated profile                    |

## Saving, recovery, and destructive actions

| ID  | Tier | Journey                                                                  | Required oracle                                                                                         |
| --- | ---- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| P01 | S    | Auto-save one annotation, quit, and reopen in a clean process            | Output exists, JSON is valid, shape is visible after restart, and no save prompt appears                |
| P02 | N    | Disable auto-save, edit, save manually, and Save As                      | Dirty title, enabled Save, chosen path, clean title, and reopened data agree                            |
| P03 | N    | Close or navigate with unsaved changes; choose Cancel, Save, and Discard | Default button, copy, focus, session preservation, and each outcome are correct                         |
| P04 | N    | Change output directory and annotate several images                      | Source images stay untouched; every JSON lands in the selected directory                                |
| P05 | N    | Delete a label file and cancel once before confirming                    | Cancel is the safe default; image remains; confirmed deletion is explicit and undo semantics are honest |
| P06 | N    | Open corrupt JSON while a good session is active                         | Error names the problem and the last good image, shapes, selection, and title remain usable             |
| P07 | N    | Open JSON whose image is missing                                         | Recovery guidance is actionable; cancel and alternate-image paths preserve data                         |
| P08 | W    | Trigger an unwritable output path during manual and auto-save            | Error is visible once per useful retry, dirty state stays honest, and no corrupt partial file remains   |
| P09 | W    | Save with and without embedded image data and reopen both                | Toggle state, file size expectation, image path, and rendered annotation agree                          |
| P10 | R    | Interrupt the packaged app after a save and relaunch                     | Last completed write is valid; startup has no crash loop or misleading recovery state                   |

## Settings, themes, and native chrome

| ID  | Tier | Journey                                                                                                        | Required oracle                                                                                       |
| --- | ---- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| U01 | N    | Open every top-level menu in loaded and empty states                                                           | Names, grouping, shortcuts, check states, destructive wording, and enablement match the UI            |
| U02 | N    | Open Settings by menu and shortcut, change one reversible option, and reopen                                   | Control is reachable, applies as described, writes isolated config, and stays synchronized with menus |
| U03 | N    | Start in light and dark themes and inspect main window, dialogs, menus, icons, selections, and disabled states | Content remains legible; semantic colors and icons update; annotation colors do not mutate            |
| U04 | N    | Traverse the primary journey with keyboard only                                                                | Focus is visible and ordered; no trap; dialogs restore focus; shortcuts work from expected contexts   |
| U05 | W    | Switch system/light/dark live and restart                                                                      | Immediate and persisted theme match; no stale icons or mixed-theme surfaces remain                    |
| U06 | W    | Run one non-English locale through startup, annotation, errors, and settings                                   | No clipped critical copy, untranslated action in the journey, or locale-sensitive data corruption     |
| U07 | R    | Inspect packaged app name, About, Preferences/Settings, Hide, Quit, window controls, file dialogs, and icons   | Native platform conventions and product identity are correct                                          |

## Accessibility and visual quality

| ID  | Tier | Journey                                                                                                    | Required oracle                                                                                |
| --- | ---- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| X01 | N    | Capture the accessibility tree for empty, loaded, drawing, label dialog, error dialog, and Settings states | Every actionable control exposes a meaningful name, role, value/state, and enabled state       |
| X02 | N    | Follow focus through annotation, cancel, error recovery, and settings                                      | Focus starts usefully, moves logically, is visible, and returns to the invoking context        |
| X03 | N    | Inspect default, hover, pressed, selected, active-mode, disabled, dirty, and error states                  | Each state is visually distinguishable without relying only on color                           |
| X04 | W    | Inspect light/dark screenshots at default and small window sizes                                           | No clipping, overlap, accidental scroll, low-contrast text, stale icon, or ambiguous hierarchy |
| X05 | W    | Increase OS text/display scale where supported                                                             | Critical text and controls remain readable and reachable; hit targets do not collapse          |
| X06 | W    | Time cold start, first image load, file filtering, zoom/pan, and a 100-shape edit                          | No unexplained freeze or sustained input lag; report measured thresholds and hardware          |

## AI Assist, opt-in network lane

Run these only when the request authorizes downloads/network use and the model cache is
isolated or intentionally reused. Record model name, version, cache state, and latency.

| ID   | Tier | Journey                                                       | Required oracle                                                                           |
| ---- | ---- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| AI01 | W    | Inspect mode/model compatibility before download or inference | Incompatible choices are disabled or rejected with guidance and no model Setting change   |
| AI02 | W    | Cancel a required model download and retry                    | Progress, cancel, cleanup, and retry are clear; ordinary annotation remains usable        |
| AI03 | W    | Use AI-Points positive/negative prompts and finish            | Prompt state, feedback, generated shape, suppression, undo, and serialized result agree   |
| AI04 | W    | Use AI-Box and an empty-result case                           | Busy/error/empty states are distinct, recoverable, and preserve the current annotation    |
| AI05 | R    | Run the packaged artifact offline with an uncached model      | No hang or crash; offline guidance is actionable and no partial model is treated as ready |

## Exploratory charter

Reserve at least 20% of a weekly or release run for unscripted use. Follow surprising
states, repeated backtracking, ambiguous words, hidden controls, and mismatches between
canvas, lists, menus, status, title, and disk. Add a scenario when the risk is repeatable;
record one-off observations without inflating them into verified defects.
