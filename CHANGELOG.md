# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Fixed a crash when a `label_flags` config entry contains an invalid regular expression (e.g. `person-(`); such a pattern raised an uncaught `re.error` when loading a labeled shape or typing in the label dialog, and is now skipped instead (the load path logs a warning naming the offending pattern) ([#2350](https://github.com/wkentaro/labelme/pull/2350))

## [7.0.4] - 2026-07-12

### Fixed

- Fixed AI Assist / AI Box crashing with `ValueError: incorrect coordinate type` when suppressing detections that overlap an existing polygon or oriented-rectangle shape on Pillow older than 11.2.1; the overlap check rasterized the existing shape by passing a list-of-lists (`ndarray.tolist()`) to `PIL.ImageDraw.polygon`, which older Pillow rejects, so it now passes the documented list-of-tuples form as elsewhere in the codebase ([#2331](https://github.com/wkentaro/labelme/pull/2331))

## [7.0.3] - 2026-07-11

### Fixed

- Fixed a crash when registering a shape after deleting one via the annotation-list context menu (`RuntimeError: Internal C++ object (LabelListWidgetItem) already deleted`); the list snapshots the selection on mouse press to support multi-selection checkbox toggles, and a context menu or drag can consume the matching release, so the snapshot outlived deleted items and is now tracked with persistent model indexes that drop removed rows ([#2318](https://github.com/wkentaro/labelme/pull/2318))
- Fixed `read_label_file` silently accepting a non-dict image-level `flags` value in an annotation file; the top-level flags are now validated as a `dict[str, bool]` on load, exactly as per-shape flags already were, so a malformed file surfaces a clear read error instead of loading a bad value that crashes later ([#2305](https://github.com/wkentaro/labelme/pull/2305))
- Fixed AI Assist / AI Text Prompt in polygon output mode emitting a degenerate 2-point "polygon" for thin, near-collinear detections; such a shape is not a valid polygon and later crashed mask conversion (`shape_to_mask` asserts more than 2 points), so it is now dropped like other empty detections ([#2298](https://github.com/wkentaro/labelme/pull/2298))
- Fixed two warning log messages rendering literal `%r`/`%d` placeholders instead of their values (the no-op point-removal warning and the empty save-path warning); loguru formats with brace-style placeholders, so the diagnostic values were silently dropped ([#2293](https://github.com/wkentaro/labelme/pull/2293))
- Fixed a startup crash when the config file contains an empty section such as a bare `shortcuts:` or `ai:`; empty sections now keep their defaults instead of raising an uncaught `AttributeError` ([#2295](https://github.com/wkentaro/labelme/pull/2295))
- Fixed a startup crash when a config section is set to a non-mapping value such as `shortcuts: oops`; the malformed section now surfaces in the configuration-error dialog (with an Ignore-and-use-defaults option) instead of crashing ([#2300](https://github.com/wkentaro/labelme/pull/2300))
- Fixed noisy Qt log lines flooding the terminal (notably the macOS per-keypress `qt.qpa.keymapper: Mismatch between Cocoa and Carbon` warning); Qt logging is now routed through the app logger with these harmless lines filtered out while genuine Qt warnings still surface ([#2292](https://github.com/wkentaro/labelme/pull/2292))

## [7.0.2] - 2026-07-03

### Fixed

- Fixed Undo (Ctrl+Z) not triggering auto-save; undoing a shape edit now marks the file dirty, so with auto-save on the restored state is written to disk instead of leaving the previous edit saved ([#2288](https://github.com/wkentaro/labelme/pull/2288))

## [7.0.1] - 2026-07-03

### Changed

- Changed the label dialog popup to anchor its content corner at the cursor; previously the window frame was anchored there, leaving the content a title-bar height below the pointer ([#2286](https://github.com/wkentaro/labelme/pull/2286))

### Fixed

- Fixed the label dialog visibly jumping right after opening; the post-show screen-edge correction now only nudges the dialog when it actually overflows the screen ([#2286](https://github.com/wkentaro/labelme/pull/2286))

## [7.0.0] - 2026-07-03

### Added

- Added a user-selectable color theme (System / Light / Dark) in the Settings dialog; System follows the OS appearance, and Dark mode is now supported where the app previously forced light mode ([#2260](https://github.com/wkentaro/labelme/pull/2260))
- Added support for placing annotation points outside the image boundary ([#2223](https://github.com/wkentaro/labelme/pull/2223))
- Added a schema-driven Settings dialog (replaces the "open YAML in editor" preference), with immediate live-apply and comment-preserving writes to ~/.labelmerc ([#2120](https://github.com/wkentaro/labelme/pull/2120))
- Added a Language picker to the Settings dialog so the UI language can be changed without editing the config file ([#2140](https://github.com/wkentaro/labelme/pull/2140))
- Added a `show_labels` toggle in Settings to draw each shape's label text on the canvas at its top-left anchor, live-applied without restart ([#2182](https://github.com/wkentaro/labelme/pull/2182))
- Added a BETA badge in the Settings dialog beside preview features (Show shape labels on canvas, Allow points outside the image boundary) to signal they are shipped for early use and to invite issue reports ([#2275](https://github.com/wkentaro/labelme/pull/2275))
- Added image flags to the Settings dialog with live dock refresh — newly added flags appear without reloading the image ([#2169](https://github.com/wkentaro/labelme/pull/2169))
- Added inline display of enabled shape flags in the annotation list (e.g. `car [occluded, truncated]`) so the full annotation state is visible at a glance ([#2134](https://github.com/wkentaro/labelme/pull/2134))
- Added Indonesian (id_ID) localization ([#2143](https://github.com/wkentaro/labelme/pull/2143))
- Added 0.1% precision to the zoom widget (e.g. `150.5 %`) for smoother stepping on large images ([#2165](https://github.com/wkentaro/labelme/pull/2165))

### Changed

- **Breaking:** Migrated the GUI from PyQt5 (Qt5) to PySide6 (Qt6) ([#2158](https://github.com/wkentaro/labelme/pull/2158))
- **Breaking:** Dropped Python 3.10 and 3.11 support; the minimum is now Python 3.12, following SPEC 0 now that numpy and scipy require 3.12. Users on 3.10 or 3.11 should stay on the v6.3.x maintenance line ([#2218](https://github.com/wkentaro/labelme/pull/2218), [#2280](https://github.com/wkentaro/labelme/pull/2280))
- **Breaking:** Privatized the Python import surface — `labelme.app`, `labelme.utils`, and `labelme.widgets` moved to `labelme._app`, `labelme._utils`, and `labelme._widgets`; labelme no longer exposes a supported Python API (use the CLI and the JSON label format) ([#2253](https://github.com/wkentaro/labelme/pull/2253))
- Fixed `UnicodeEncodeError` on non-UTF-8 locales (e.g. Windows cp1252) when labels contain non-ASCII characters by always reading and writing the config file in UTF-8 encoding ([#2136](https://github.com/wkentaro/labelme/pull/2136))
- **Breaking:** Switched config file parsing from PyYAML to ruamel.yaml; comments and formatting in `~/.labelmerc` are now preserved across Settings edits. Note: YAML 1.2 is now used, so boolean spellings `yes`/`no`/`on`/`off` are read as strings rather than booleans ([#2114](https://github.com/wkentaro/labelme/pull/2114))
- Changed the delete confirmation dialog to default to Cancel (not Delete) and use verb labels (Delete / Cancel) to reduce accidental data loss ([#2197](https://github.com/wkentaro/labelme/pull/2197))
- Updated predefined labels in the label dialog in place when changed via Settings, preserving labels typed during the current session ([#2164](https://github.com/wkentaro/labelme/pull/2164))
- Changed point shapes to be selected by clicking the marker as a whole rather than grabbing its single vertex ([#2158](https://github.com/wkentaro/labelme/pull/2158))

### Removed

- **Breaking:** Removed the public `LabelFile` class (`labelme.LabelFile`); use the `read_label_file` / `write_label_file` functions and the `LabelFileError` hierarchy in `labelme._label_file` instead ([#2246](https://github.com/wkentaro/labelme/pull/2246))
- **Breaking:** Removed the deprecated `labelme.utils` compatibility shims: `labelme.utils.lblsave` (use `imgviz.io.lblsave`) and the camelCase aliases `addActions`, `distancetoline`, `fmtShortcut`, `labelValidator`, `newAction`, `newButton`, `newIcon` (use their snake_case names). The `from labelme import utils` top-level re-export is also dropped ([#2249](https://github.com/wkentaro/labelme/pull/2249))
- **Breaking:** Removed the deprecated `--autosave` and `--nodata` CLI flags; use `--no-auto-save` and `--with-image-data` instead. The remaining legacy aliases `--nosortlabels`, `--labelflags`, and `--validatelabel` now emit a `FutureWarning` ([#2245](https://github.com/wkentaro/labelme/pull/2245))

### Fixed

- Fixed a hidden shape staying hover-interactive (highlight, cursor, click-to-select) when it was the hovered shape at the moment it was hidden ([#2276](https://github.com/wkentaro/labelme/pull/2276))
- Fixed the standalone-executable build instructions forcing `numpy<2.0` (a stale PyQt5-era PyInstaller workaround), which broke builds on Python 3.12+ where numpy 2.x is the default ([#2279](https://github.com/wkentaro/labelme/pull/2279))
- Fixed annotation label text being clipped or invisible in the label list on some desktop styles (e.g. GNOME/Adwaita) by widening the delegate's text clip rect to the rendered width ([#2273](https://github.com/wkentaro/labelme/pull/2273))
- Fixed `line` and two-point `linestrip` shapes being unselectable by click ([#2107](https://github.com/wkentaro/labelme/pull/2107))
- Fixed the canvas going blank after "Delete File" (Delete File now removes only the label JSON and keeps the image on screen) ([#2138](https://github.com/wkentaro/labelme/pull/2138))
- Fixed notch artifacts at interior vertices of linestrip masks by using PIL's `joint="curve"` rasterization ([#2163](https://github.com/wkentaro/labelme/pull/2163))
- Fixed deleting a polygon vertex dragging the adjacent vertex on the next mouse move ([#2194](https://github.com/wkentaro/labelme/pull/2194))
- Fixed canvas not repainting immediately after adding or removing a polygon point via keyboard shortcut ([#2174](https://github.com/wkentaro/labelme/pull/2174))
- Fixed grab-pan overscroll causing an image snap/jump at the zoom threshold by ramping the scroll slack continuously ([#2101](https://github.com/wkentaro/labelme/pull/2101))
- Fixed a confusing bare `KeyError` when a shape label is absent from the provided labels mapping; now raises a descriptive `ValueError` naming all missing labels at once ([#2173](https://github.com/wkentaro/labelme/pull/2173))
- Fixed AI Text-to-Annotation silently producing nothing when a detection-only model (e.g. YOLO-World) is paired with a mask output format; a warning now directs users to SAM or Rectangle output ([#2196](https://github.com/wkentaro/labelme/pull/2196))
- Fixed AI Text-to-Annotation aborting with an assertion when a detection model returned no mask; it now raises a descriptive error ([#2256](https://github.com/wkentaro/labelme/pull/2256))
- Fixed AI-assisted polygons being offset from their mask by aligning `compute_polygon_from_mask` with image coordinates ([#2239](https://github.com/wkentaro/labelme/pull/2239))
- Fixed the app crashing when an AI model errored during inference; the error is now surfaced instead of aborting ([#2247](https://github.com/wkentaro/labelme/pull/2247))
- Fixed TIFF images with non-finite (NaN/Inf) pixels rendering incorrectly by normalizing the display over finite pixels only ([#2255](https://github.com/wkentaro/labelme/pull/2255))
- Fixed shape flag checkboxes re-enabling on label text change when they should stay disabled ([#2243](https://github.com/wkentaro/labelme/pull/2243))
- Fixed the vertex remaining selected after removing a polygon point ([#2175](https://github.com/wkentaro/labelme/pull/2175))
- Fixed the label dialog overflowing the screen when a label has many flags by making the flag list scrollable and keeping the popup on screen ([#2263](https://github.com/wkentaro/labelme/pull/2263))
- Fixed the Edit Label dialog opening away from the cursor instead of at the context-menu origin ([#2264](https://github.com/wkentaro/labelme/pull/2264))

## [6.3.1] - 2026-05-27

### Fixed

- Fixed a crash when switching drawing modes while a shape was partially drawn; the in-progress shape is now retyped when both modes accept a single click as a starting point, and cancelled otherwise. Degenerate shapes (zero-area rectangle, zero-length line, polygon with fewer than 3 distinct vertices) are now rejected at the point of completion ([#2103](https://github.com/wkentaro/labelme/pull/2103))

## [6.3.0] - 2026-05-19

### Added

- Added mask-aware suppression that collapses redundant SAM detections at multiple granularities into a single shape per region ([#2088](https://github.com/wkentaro/labelme/pull/2088))
- Added suppression of AI detections whose mask overlaps an already-annotated shape (mask overlap >= 0.5), preventing duplicate annotations when prompting over existing labels ([#2087](https://github.com/wkentaro/labelme/pull/2087))

### Fixed

- Fixed missing status bar feedback and disabled edit-mode button when AI inference produces no new shapes ([#2083](https://github.com/wkentaro/labelme/pull/2083))
- Fixed AI detections with empty segmentation masks being emitted as transparent shapes; they are now dropped ([#2094](https://github.com/wkentaro/labelme/pull/2094))
- Fixed vertex-drag handles appearing on mask shapes, which previously shifted the bounding box without moving the underlying bitmap ([#2095](https://github.com/wkentaro/labelme/pull/2095))

## [6.2.0] - 2026-05-10

### Added

- Added oriented rectangle shape type for rotated bounding box annotation, available in the toolbar and via keyboard shortcut ([#1980](https://github.com/wkentaro/labelme/pull/1980))
- Added AI-assisted oriented rectangle: SAM masks can now be emitted as an oriented rectangle, fitting the minimum-area rotated bounding box to the predicted mask ([#2078](https://github.com/wkentaro/labelme/pull/2078))
- Added rectangle and circle as AI-assisted output formats: AI-Points and AI-Box can now output `rectangle` or `circle` derived from the predicted mask, in addition to `polygon` and `mask` ([#2064](https://github.com/wkentaro/labelme/pull/2064))
- Added right-click "Add Point to Edge" context menu action to insert a vertex at the cursor position on the nearest edge of the selected shape ([#2029](https://github.com/wkentaro/labelme/pull/2029))
- Made hide/show shape undoable via the undo stack ([#2034](https://github.com/wkentaro/labelme/pull/2034))
- Propagated hide/show toggle across all shapes in a multi-selection ([#2035](https://github.com/wkentaro/labelme/pull/2035))

### Changed

- Redesigned AI-Points and AI-Box toolbar icons to represent the input action (click vs. drag-box) with a sparkle accent, replacing the previous output-named polygon/mask icons ([#1985](https://github.com/wkentaro/labelme/pull/1985))
- Improved Turkish (tr_TR) translations for correctness, natural phrasing, and consistency with Apple/Microsoft Turkish UI conventions ([#1967](https://github.com/wkentaro/labelme/pull/1967))
- Retranslated Turkish (tr_TR) with corrected domain terminology and grammar ([#1963](https://github.com/wkentaro/labelme/pull/1963))
- Retranslated Simplified Chinese (zh_CN) to use standard CV/ML domain terms and idiomatic phrasing, including unifying "annotation" as `标注` ([#1965](https://github.com/wkentaro/labelme/pull/1965))

### Fixed

- Fixed incorrect AI-Box predictions when the bounding box was drawn right-to-left or bottom-to-top by normalizing the corner points before sending to the model ([#2032](https://github.com/wkentaro/labelme/pull/2032))
- Fixed color indicator on annotation list rows disappearing after editing a shape's group ID ([#2015](https://github.com/wkentaro/labelme/pull/2015))
- Fixed Shift+wheel to scroll horizontally on Linux and Windows, matching macOS behavior ([#2014](https://github.com/wkentaro/labelme/pull/2014))
- Fixed oriented rectangle being lost when cancelling the label dialog after drawing ([#2079](https://github.com/wkentaro/labelme/pull/2079))
- Fixed `validate_label: null` not skipping validation as documented

## [6.1.3] - 2026-04-24

### Fixed

- Stale snap highlight no longer stays on canvas after scroll, zoom, or resize ([#1975](https://github.com/wkentaro/labelme/pull/1975))

## [6.1.2] - 2026-04-21

### Fixed

- Restored first-vertex snap highlight when closing a polygon ([#1974](https://github.com/wkentaro/labelme/pull/1974))

## [6.1.1] - 2026-04-19

### Fixed

- Fixed Ctrl/Cmd+A (Edit > Select All) not working when the canvas has focus ([#1964](https://github.com/wkentaro/labelme/pull/1964))

## [6.1.0] - 2026-04-16

### Added

- Added SAM3 to the AI model list with AI-Box support, producing multiple shapes from a single bounding box annotation ([#1917](https://github.com/wkentaro/labelme/pull/1917))
- Unified AI annotation tools into two modes: AI Points -> Shape and AI Box -> Shape, each with a polygon/mask output toggle; added a visual separator between manual and AI tools in the toolbar ([#1914](https://github.com/wkentaro/labelme/pull/1914), [#1915](https://github.com/wkentaro/labelme/pull/1915), [#1916](https://github.com/wkentaro/labelme/pull/1916))
- Added a progress bar with cancellation support during AI model downloads ([#1948](https://github.com/wkentaro/labelme/pull/1948))
- Added auto-import of sibling images from the same directory when opening a single image file ([#1924](https://github.com/wkentaro/labelme/pull/1924))
- Added highlighting of AI toolbar buttons when hovering the disabled AI-Assisted Annotation widget to help new users find them ([#1961](https://github.com/wkentaro/labelme/pull/1961))
- Switched canvas repainting from synchronous to asynchronous rendering, avoiding blocking redraws ([#1869](https://github.com/wkentaro/labelme/pull/1869))
- Added Greek (el_GR) translation ([#1893](https://github.com/wkentaro/labelme/pull/1893))
- Added Ukrainian (uk_UA) translation ([#1892](https://github.com/wkentaro/labelme/pull/1892))
- Added Russian (ru_RU) translation ([#1891](https://github.com/wkentaro/labelme/pull/1891))

### Changed

- Shortened toolbar button labels by removing the redundant "Create" prefix (e.g., "Create Polygon" becomes "Polygon") ([#1914](https://github.com/wkentaro/labelme/pull/1914))
- Disabled the file list dock with an explanatory tooltip when a label `.json` file is opened directly; re-enabled it when a directory or image is opened ([#1924](https://github.com/wkentaro/labelme/pull/1924))
- Added support for cropped masks returned by osam 0.4.0 (SAM3) for accurate annotation on large images ([#1919](https://github.com/wkentaro/labelme/pull/1919))

### Deprecated

- Deprecated `labelme.utils.lblsave`; use `imgviz.io.lblsave` instead. The old import will be removed in a future release ([#1911](https://github.com/wkentaro/labelme/pull/1911), [#1959](https://github.com/wkentaro/labelme/pull/1959))

### Removed

- Removed the "Open Recent" submenu from the File menu; use the file list dock (which now auto-populates with sibling images) or the OS file dialog instead ([#1921](https://github.com/wkentaro/labelme/pull/1921))

### Fixed

- Fixed single undo to fully restore a deleted shape; previously two undos were required ([#1932](https://github.com/wkentaro/labelme/pull/1932))
- Disabled SAM3 in the model selector during AI-Points mode and showed a warning, as SAM3 does not support point prompts ([#1918](https://github.com/wkentaro/labelme/pull/1918))
- Fixed AI mode tooltip names to match the renamed menu labels ([#1928](https://github.com/wkentaro/labelme/pull/1928))
- Equalized button widths in the vertical toolbar ([#1961](https://github.com/wkentaro/labelme/pull/1961))

## [6.0.2] - 2026-04-16

### Fixed

- Fixed broken images on the PyPI project page by rewriting relative image paths to absolute GitHub raw URLs at build time ([#1954](https://github.com/wkentaro/labelme/pull/1954))

## [6.0.1] - 2026-04-16

### Fixed

- Fixed the "Save Automatically" checkbox having no effect after v6.0.0 changed its default to enabled ([#1953](https://github.com/wkentaro/labelme/pull/1953))

## [6.0.0] - 2026-03-28

### Added

- Added support for multispectral and float32 TIFF images via tifffile (e.g., satellite imagery) ([#1812](https://github.com/wkentaro/labelme/pull/1812))
- Added Polish (pl_PL) translation ([#1809](https://github.com/wkentaro/labelme/pull/1809))
- Added Thai (th_TH) translation ([#1886](https://github.com/wkentaro/labelme/pull/1886))
- Added Turkish language support for AI-assisted annotation features ([#1805](https://github.com/wkentaro/labelme/pull/1805))
- Created sparse ~/.labelmerc containing only user-changed settings instead of copying the full default config ([#1796](https://github.com/wkentaro/labelme/pull/1796))

### Changed

- **Breaking:** Changed auto-save default to on; use `--no-auto-save` or `auto_save: false` in config to disable ([#1815](https://github.com/wkentaro/labelme/pull/1815))
- **Breaking:** Changed the default so image data is no longer embedded in JSON files; JSON now references image paths instead of base64. Use `--with-image-data` or `with_image_data: true` in config to embed ([#1814](https://github.com/wkentaro/labelme/pull/1814))
- **Breaking:** Renamed the CLI positional argument from `filename` to `path`; it now accepts image files, label files, or directories ([#1825](https://github.com/wkentaro/labelme/pull/1825))
- **Breaking:** Changed `--output` to always expect a directory path (no longer accepts `.json` file paths) ([#1813](https://github.com/wkentaro/labelme/pull/1813))
- **Breaking:** Standardized CLI flags to hyphenated style: `--autosave` -> `--no-auto-save`, `--nosortlabels` -> `--no-sort-labels`, `--labelflags` -> `--label-flags`, `--validatelabel` -> `--validate-label`; old forms kept as hidden aliases until v7 ([#1823](https://github.com/wkentaro/labelme/pull/1823))
- Renamed the "Shape Labels" dock widget to "Annotation List" ([#1828](https://github.com/wkentaro/labelme/pull/1828))
- Renamed "polygon" to "shape" in shortcuts and UI labels ([#1822](https://github.com/wkentaro/labelme/pull/1822))
- Prioritized vertices over shape bodies in hover detection, making vertex editing easier ([#1867](https://github.com/wkentaro/labelme/pull/1867))
- Improved large image loading performance by skipping re-encoding for JPEG/PNG without EXIF rotation ([#1811](https://github.com/wkentaro/labelme/pull/1811))

### Deprecated

- Deprecated `--autosave` flag; use `--no-auto-save` instead (will be removed in v7)
- Deprecated `--nodata` flag; use `--with-image-data` instead (will be removed in v7)
- Deprecated config key `store_data`; automatically migrated to `with_image_data`

### Removed

- **Breaking:** Removed `labelme_draw_json`, `labelme_draw_label_png`, and `labelme_export_json` CLI entry points; moved to `examples/tutorial/` as standalone scripts ([#1846](https://github.com/wkentaro/labelme/pull/1846))
- **Breaking:** Removed `labelme_on_docker` CLI entry point ([#1821](https://github.com/wkentaro/labelme/pull/1821))
- **Breaking:** Removed deprecated `labelme.utils.polygons_to_mask()` and `labelme.utils.labelme_shapes_to_label()` (deprecated since v4) ([#1821](https://github.com/wkentaro/labelme/pull/1821))

### Fixed

- Fixed point shapes not being clickable ([#1860](https://github.com/wkentaro/labelme/pull/1860))
- Fixed window position not recovering when the saved screen is no longer available ([#1859](https://github.com/wkentaro/labelme/pull/1859))
- Fixed out-of-bounds crash when highlighting AI-generated masks ([#1858](https://github.com/wkentaro/labelme/pull/1858))
- Fixed pasted shapes not being selected after cross-file paste ([#1876](https://github.com/wkentaro/labelme/pull/1876))
- Fixed RGBA/transparent images not rendering correctly in the brightness/contrast dialog ([#1872](https://github.com/wkentaro/labelme/pull/1872))
- Fixed crosshair guide lines extending beyond image bounds ([#1870](https://github.com/wkentaro/labelme/pull/1870))
- Fixed a crash when the previously selected shape was removed from the annotation list ([#1871](https://github.com/wkentaro/labelme/pull/1871))
- Fixed a crash on malformed JSON in the file dialog preview ([#1900](https://github.com/wkentaro/labelme/pull/1900))
- Fixed a hang with `@` symbols in file paths on macOS with Unicode paths ([#1904](https://github.com/wkentaro/labelme/pull/1904))
- Fixed rectangle drawn right-to-left producing incorrect masks ([#1817](https://github.com/wkentaro/labelme/pull/1817))
- Fixed a crash when moving a vertex beyond valid range on the canvas ([#1818](https://github.com/wkentaro/labelme/pull/1818))
- Fixed RGBA PNG conversion in `labelme2coco` ([#1830](https://github.com/wkentaro/labelme/pull/1830))
- Fixed deprecated NumPy boolean type usage ([#1831](https://github.com/wkentaro/labelme/pull/1831))
- Fixed silent failure when an image file fails to open; an error dialog is now shown ([#1810](https://github.com/wkentaro/labelme/pull/1810))
- Fixed display issues by forcing light mode (dark mode not yet supported) ([#1808](https://github.com/wkentaro/labelme/pull/1808))
- Fixed points on the edge of the image being rejected; edge placement is now allowed ([#1801](https://github.com/wkentaro/labelme/pull/1801))

## [5.11.4] - 2026-03-10

### Added

- Added a "Reset Layout" action to reset the window layout to default ([#1864](https://github.com/wkentaro/labelme/pull/1864))

### Fixed

- Fixed window state reset for users upgrading from older versions ([#1863](https://github.com/wkentaro/labelme/pull/1863))

## [5.11.3] - 2026-02-20

### Fixed

- Forced light mode since dark mode is not yet supported

## [5.11.2] - 2026-01-31

### Fixed

- Fixed mask being set and drawn for non-mask shapes (e.g. polygon) ([#1797](https://github.com/wkentaro/labelme/pull/1797))

## [5.11.1] - 2026-01-28

_No user-facing changes._

## [5.11.0] - 2026-01-28

### Added

- Added support for square drawing in Create Rectangle mode ([#1748](https://github.com/wkentaro/labelme/pull/1748))
- Applied the "Fusion" style for consistent appearance across platforms ([#1751](https://github.com/wkentaro/labelme/pull/1751))
- Added model selection display to the AI Prompt widget ([#1752](https://github.com/wkentaro/labelme/pull/1752))
- Added an info button to the AI-Assisted Annotation widget ([#1764](https://github.com/wkentaro/labelme/pull/1764))
- Added a tooltip for the AI Text-to-Annotation info button ([#1766](https://github.com/wkentaro/labelme/pull/1766))
- Introduced SAM3 (smart) model for text-to-rectangle annotation ([#1762](https://github.com/wkentaro/labelme/pull/1762))
- Added support for "polygon" and "mask" output types in AI text-to-annotation ([#1774](https://github.com/wkentaro/labelme/pull/1774))
- Added a "Preferences..." menu item for editing the config file (macOS: Cmd+,; Win/Linux: Ctrl+Shift+,) ([#1781](https://github.com/wkentaro/labelme/pull/1781))
- Added Traditional Chinese (zh_TW) translation ([#1727](https://github.com/wkentaro/labelme/pull/1727))
- Added French (fr_FR) translation ([#1730](https://github.com/wkentaro/labelme/pull/1730))
- Added Japanese (ja_JP) translation ([#1732](https://github.com/wkentaro/labelme/pull/1732))
- Added Hungarian (hu_HU) translation ([#1734](https://github.com/wkentaro/labelme/pull/1734))
- Added German (de_DE) translation ([#1735](https://github.com/wkentaro/labelme/pull/1735))
- Added Persian (fa_IR) translation ([#1737](https://github.com/wkentaro/labelme/pull/1737))
- Added Korean (ko_KR) translation ([#1738](https://github.com/wkentaro/labelme/pull/1738))
- Added Spanish (es_ES) translation ([#1739](https://github.com/wkentaro/labelme/pull/1739))
- Added Portuguese (pt_BR) translation ([#1749](https://github.com/wkentaro/labelme/pull/1749))
- Added Dutch (nl_NL) translation ([#1750](https://github.com/wkentaro/labelme/pull/1750))
- Added Italian (it_IT) translation ([#1776](https://github.com/wkentaro/labelme/pull/1776))
- Added Vietnamese (vi_VN) translation ([#1779](https://github.com/wkentaro/labelme/pull/1779))

### Changed

- Disabled the AI-Assisted Annotation widget when not in an AI mode ([#1767](https://github.com/wkentaro/labelme/pull/1767))
- Disabled the AI Prompt widget when not in rectangle-create mode ([#1753](https://github.com/wkentaro/labelme/pull/1753))
- Restricted label editing from the label list to edit mode only ([#1769](https://github.com/wkentaro/labelme/pull/1769))

### Removed

- **Breaking:** Dropped Python 3.9 support ([#1746](https://github.com/wkentaro/labelme/pull/1746))

### Fixed

- Fixed a crash when loading a new image by clearing the shape selection state ([#1717](https://github.com/wkentaro/labelme/pull/1717))
- Fixed import conflicts by loading onnxruntime before PyQt5 ([#1723](https://github.com/wkentaro/labelme/pull/1723))
- Fixed double-click shape finalization not respecting the close-shape check ([#1724](https://github.com/wkentaro/labelme/pull/1724))
- Fixed a typo in a variable name in the shape module ([#1733](https://github.com/wkentaro/labelme/pull/1733))
- Fixed a crash when bounding-box non-maximum suppression receives empty input ([#1761](https://github.com/wkentaro/labelme/pull/1761))
- Fixed unnecessary AI model initialization by loading the AI session lazily ([#1775](https://github.com/wkentaro/labelme/pull/1775))
- Fixed Windows-style paths not being handled correctly in label files ([#1784](https://github.com/wkentaro/labelme/pull/1784))
- Fixed a NumPy compatibility issue by replacing the cross-product helper with a manual 2D implementation ([#1785](https://github.com/wkentaro/labelme/pull/1785))
- Fixed the file list not being filtered immediately when opening a directory with a file_search config filter ([#1788](https://github.com/wkentaro/labelme/pull/1788))
- Fixed Japanese (ja_JP) menu and toolbar labels wrapping incorrectly by adding explicit newlines ([#1768](https://github.com/wkentaro/labelme/pull/1768))

## [5.10.1] - 2025-11-29

### Fixed

- Fixed a crash when loading a new image while shapes were selected on the canvas
- Fixed a crash on double-click shape finalization by correctly checking whether the shape was closeable
- Fixed a startup crash on some systems by importing onnxruntime before PyQt5

## [5.10.0] - 2025-11-25

### Added

- Added canvas mode display to the status bar ([#1682](https://github.com/wkentaro/labelme/pull/1682))
- Added a sidebar toolbar for shape creation tools ([#1685](https://github.com/wkentaro/labelme/pull/1685))
- Added image index display to the window title ([#1692](https://github.com/wkentaro/labelme/pull/1692))
- Added middle-mouse-button drag to pan the canvas ([#1622](https://github.com/wkentaro/labelme/pull/1622))
- Improved vertex selection to prioritize the highlighted shape's vertex ([#1691](https://github.com/wkentaro/labelme/pull/1691))
- Refreshed the application icons ([#1701](https://github.com/wkentaro/labelme/pull/1701))
- Added mouse-wheel zoom toward canvas center ([#1704](https://github.com/wkentaro/labelme/pull/1704))

### Changed

- Compacted the toolbar layout ([#1684](https://github.com/wkentaro/labelme/pull/1684))
- Changed zoom centering to use the visible region center instead of the canvas origin ([#1705](https://github.com/wkentaro/labelme/pull/1705))

### Fixed

- Fixed the Edit Mode button being incorrectly enabled on startup (it is already in Edit mode by default) ([#1683](https://github.com/wkentaro/labelme/pull/1683))
- Fixed font size inconsistency in the toolbar on macOS ([#1713](https://github.com/wkentaro/labelme/pull/1713))
- Fixed high-DPI display scaling on HiDPI screens ([#1687](https://github.com/wkentaro/labelme/pull/1687))
- Fixed a crash when no image is loaded during canvas repaint ([#1695](https://github.com/wkentaro/labelme/pull/1695))
- Fixed an error when a file is closed while the image list is not empty ([#1700](https://github.com/wkentaro/labelme/pull/1700))
- Fixed current image index display to reflect the file list position ([#1708](https://github.com/wkentaro/labelme/pull/1708))
- Fixed the AI prompt receiving focus after a file is closed ([#1699](https://github.com/wkentaro/labelme/pull/1699))
- Fixed a spurious scrollbar appearing when fitting the image to width ([#1702](https://github.com/wkentaro/labelme/pull/1702))
- Fixed canvas layout shifting caused by non-ASCII bullet characters in status messages ([#1712](https://github.com/wkentaro/labelme/pull/1712))
- Fixed shapes remaining visible on the canvas after a reset ([#1690](https://github.com/wkentaro/labelme/pull/1690))
- Fixed excessive VRAM usage by removing the cache on the SAM model ([#1715](https://github.com/wkentaro/labelme/pull/1715))
- Fixed a duplicate unsaved-changes confirmation dialog when navigating between images ([#1693](https://github.com/wkentaro/labelme/pull/1693))

## [5.9.1] - 2025-10-17

### Fixed

- Fixed canvas cursor so changes take effect immediately without flickering ([#1681](https://github.com/wkentaro/labelme/pull/1681))

## [5.9.0] - 2025-10-16

### Added

- Validated shape JSON objects in annotation files, catching malformed annotations earlier ([#1624](https://github.com/wkentaro/labelme/pull/1624))
- Added spacebar shortcut to finalize a shape while drawing ([#1474](https://github.com/wkentaro/labelme/pull/1474))
- Added drawing and editing status messages to the status bar ([#1673](https://github.com/wkentaro/labelme/pull/1673))
- Added a progress dialog when downloading an AI model ([#1677](https://github.com/wkentaro/labelme/pull/1677))
- Added an option to keep previous brightness/contrast settings across images ([#1678](https://github.com/wkentaro/labelme/pull/1678))
- Added a download dialog for the text-to-bbox AI model ([#1679](https://github.com/wkentaro/labelme/pull/1679))
- Added an About Labelme menu item and dialog showing the version and links ([#1680](https://github.com/wkentaro/labelme/pull/1680))

### Fixed

- Fixed the brightness/contrast slider label not updating correctly ([#1613](https://github.com/wkentaro/labelme/pull/1613))
- Fixed linestrip shapes incorrectly filling their internal area ([#1628](https://github.com/wkentaro/labelme/pull/1628))
- Fixed missing fill drawing in polygon mode ([#1627](https://github.com/wkentaro/labelme/pull/1627))
- Fixed label list rendering inconsistency on Windows ([#1646](https://github.com/wkentaro/labelme/pull/1646))
- Fixed cursor flickering on Windows ([#1647](https://github.com/wkentaro/labelme/pull/1647))
- Fixed label list items being overwritten when dragging and dropping ([#1651](https://github.com/wkentaro/labelme/pull/1651))
- Fixed the brightness/contrast dialog failing on non-RGB images (e.g. PNG with alpha channel) ([#1655](https://github.com/wkentaro/labelme/pull/1655))
- Fixed the Save Automatically checkmark not appearing on Windows ([#1657](https://github.com/wkentaro/labelme/pull/1657))

## [5.8.3] - 2025-07-13

### Fixed

- Fixed a crash when clicking on a polygon (float coordinates caused a type error in the Qt point constructor on Python 3.12) ([#1606](https://github.com/wkentaro/labelme/pull/1606))
- Fixed the AI mask feature crashing due to a missing file-handle attribute on the logger's output stream ([#1603](https://github.com/wkentaro/labelme/pull/1603))
- Fixed Python 3.12 compatibility when loading Docker by replacing the deprecated executable-search function with the standard `shutil.which` ([#1589](https://github.com/wkentaro/labelme/pull/1589))

## [5.8.2] - 2025-06-21

### Changed

- Deferred SAM image-embedding computation to the first click on an image instead of on image load, making image navigation faster when AI annotation is active ([#1593](https://github.com/wkentaro/labelme/pull/1593))
- Initialized the AI (SAM) model lazily only when first needed, removing unnecessary initialization on mode switches ([#1596](https://github.com/wkentaro/labelme/pull/1596))

### Fixed

- Captured unhandled exceptions globally so crashes are recorded in the log file when running the packaged app ([#1601](https://github.com/wkentaro/labelme/pull/1601))
- Fixed a crash when switching from AI polygon mode to polygon mode after the AI model was initialized ([#1588](https://github.com/wkentaro/labelme/pull/1588))
- Fixed shape flags staying disabled in the label dialog after group-editing flags on multiple shapes

## [5.8.1] - 2025-03-24

### Fixed

- Fixed missing check for AI segmentation model in canvas finalization ([#1566](https://github.com/wkentaro/labelme/pull/1566))

## [5.8.0] - 2025-03-16

### Added

- Added SAM2 as the default AI model for faster and more accurate AI-polygon and AI-mask annotations ([#1557](https://github.com/wkentaro/labelme/pull/1557))
- Added support for `shape_type="mask"` in conversion tools (`labelme_draw_json`, `labelme2voc.py`, `labelme_export_json`) ([#1560](https://github.com/wkentaro/labelme/pull/1560))

### Removed

- **Breaking:** Removed `labelme_json_to_dataset` command (deprecated in favor of `labelme_export_json`) ([#1561](https://github.com/wkentaro/labelme/pull/1561))

### Fixed

- Fixed a crash when finishing a shape in AI-mask or AI-polygon mode ([#1558](https://github.com/wkentaro/labelme/pull/1558))
- Fixed a crash caused by a null bounding box in AI-mask mode response ([#1556](https://github.com/wkentaro/labelme/pull/1556))

## [5.7.0] - 2025-03-04

### Changed

- **Breaking:** Dropped qtpy and PySide2 support; PyQt5 is now the primary supported Qt binding ([#1540](https://github.com/wkentaro/labelme/pull/1540))

### Fixed

- Fixed a crash when a shape's flags field is None, which occurred when using AI text-to-rectangle ([#1536](https://github.com/wkentaro/labelme/pull/1536))
- Fixed a crash in the packaged app caused by missing stderr when downloading AI models via gdown ([#1549](https://github.com/wkentaro/labelme/pull/1549))

## [5.6.1] - 2025-01-23

### Fixed

- Fixed an encoding error on Windows when reading annotation files ([#1525](https://github.com/wkentaro/labelme/pull/1525))
- Fixed a crash on startup caused by an undefined logging method when using loguru ([#1530](https://github.com/wkentaro/labelme/pull/1530))

## [5.6.0] - 2024-12-30

### Added

- Added "AI Text to Rectangles" AI feature ([#1469](https://github.com/wkentaro/labelme/pull/1469))

### Changed

- Changed point manipulation shortcuts: ALT+Click adds a point, ALT+SHIFT+Click deletes a point ([#1496](https://github.com/wkentaro/labelme/pull/1496))

### Fixed

- Fixed slight position shift when duplicating a shape ([#1499](https://github.com/wkentaro/labelme/pull/1499))
- Fixed the group ID field not being clearable by re-selecting the already-set value ([#1498](https://github.com/wkentaro/labelme/pull/1498))
- Fixed group ID editing when the text field is disabled ([#1497](https://github.com/wkentaro/labelme/pull/1497))
- Fixed crosshair and point size rendering to stay consistent regardless of zoom level ([#1471](https://github.com/wkentaro/labelme/pull/1471))

## [5.5.0] - 2024-06-13

### Added

- Added support for editing multiple annotations simultaneously ([#1455](https://github.com/wkentaro/labelme/pull/1455))
- Added XY coordinate display in the status bar ([#1456](https://github.com/wkentaro/labelme/pull/1456))
- Added support for closing an AI polygon by pressing Enter ([#1429](https://github.com/wkentaro/labelme/pull/1429))

### Changed

- Saved masks as 8-bit unsigned integers for better compatibility with other tools ([#1452](https://github.com/wkentaro/labelme/pull/1452))
- Kept shapes selected after duplicating ([#1401](https://github.com/wkentaro/labelme/pull/1401))
- Improved brightness/contrast adjustment speed and usability, adding numeric labels to the sliders ([#1443](https://github.com/wkentaro/labelme/pull/1443))
- Updated the internationalization template and improved the Simplified Chinese translation ([#1411](https://github.com/wkentaro/labelme/pull/1411))

### Fixed

- Fixed slider alignment in the brightness/contrast dialog
- Fixed stride value in the brightness/contrast dialog

## [5.4.1] - 2024-01-06

### Added

- Added copy and paste actions to the Edit menu ([#1392](https://github.com/wkentaro/labelme/pull/1392))

### Fixed

- Fixed an encoding error on Windows caused by emoji characters in output ([#1390](https://github.com/wkentaro/labelme/pull/1390))
- Fixed crashes during annotation caused by empty contours ([#1391](https://github.com/wkentaro/labelme/pull/1391))

## [5.4.0] - 2023-12-31

### Added

- Added an AI mask annotation mode that generates shapes as masks using AI ([#1358](https://github.com/wkentaro/labelme/pull/1358))
- Integrated EfficientSAM as a faster AI model option (claimed ~20x faster than original SAM) ([#1375](https://github.com/wkentaro/labelme/pull/1375))
- Added a menu to toggle visibility of all shapes with keyboard shortcuts ([#1381](https://github.com/wkentaro/labelme/pull/1381))
- Added regex filename search in the file browser ([#1384](https://github.com/wkentaro/labelme/pull/1384))
- Included translation files in the package to enable localization everywhere ([#1383](https://github.com/wkentaro/labelme/pull/1383))
- Added an `ai.default` config key to set the default AI model in `~/.labelmerc`

### Changed

- Increased resolution of polygon approximation for more accurate AI-generated polygons ([#1363](https://github.com/wkentaro/labelme/pull/1363))
- Cleaned up the toolbar: removed less common items and clarified distinction between actions and other controls ([#1356](https://github.com/wkentaro/labelme/pull/1356))
- Resized toolbar icons to 32x32 for consistent alignment ([#1357](https://github.com/wkentaro/labelme/pull/1357))
- Used a tight bounding box to represent the bounding box for mask shapes ([#1379](https://github.com/wkentaro/labelme/pull/1379))
- Exported original VOC format in `labelme2voc.py` ([#1323](https://github.com/wkentaro/labelme/pull/1323))
- Added support for comma-separated text for the `--labels` argument in `labelme2voc.py` ([#1326](https://github.com/wkentaro/labelme/pull/1326))
- Sorted JSON file processing order in `labelme2voc.py` for deterministic output ([#1327](https://github.com/wkentaro/labelme/pull/1327))
- Showed label names and image preview in `draw_label_png.py` ([#1318](https://github.com/wkentaro/labelme/pull/1318))
- Removed custom font override to stop interfering with system font rendering ([#1355](https://github.com/wkentaro/labelme/pull/1355))
- Cleaned up AI-generated masks by removing small noisy objects (smaller than 5% of the mask area) after SAM prediction

### Fixed

- Fixed file paths displaying incorrectly on Windows by normalizing path separators ([#1362](https://github.com/wkentaro/labelme/pull/1362))
- Fixed a crash caused by an incompatible `onnxruntime` version by pinning away from 1.16.0 ([#1364](https://github.com/wkentaro/labelme/pull/1364))
- Fixed a crash when an AI mode was activated before an image was loaded

## [5.3.1] - 2023-08-22

### Fixed

- Fixed `labelme_export_json` CLI to strip only the file extension from the output directory name, so files with multiple dots (e.g. `image.v2.json`) no longer produce a mangled directory name

## [5.3.0] - 2023-08-06

### Added

- Integrated Segment Anything Model (SAM) for AI-assisted polygon annotation (`Create AI-Polygon` mode) ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Added support for positive and negative point clicks (Shift+click to exclude regions) for SAM annotation ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Added support for 1-click annotation in `ai_polygon` mode ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Added real-time polygon preview while placing SAM points ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Added a dropdown to select AI models ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Added an image embedding cache to speed up repeated SAM annotations on the same image ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Added a zoom level label to the UI ([#1262](https://github.com/wkentaro/labelme/pull/1262))

### Changed

- **Breaking:** Renamed command-line tool `labelme_json_to_dataset` to `labelme_export_json` ([#1308](https://github.com/wkentaro/labelme/pull/1308))
- Moved the toolbar to the top by default ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Enabled Ctrl+Shift key combination for annotation interactions ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Set shape fill color to black and enabled fill by default ([#1262](https://github.com/wkentaro/labelme/pull/1262))

### Fixed

- Fixed polygon contour detection at image borders ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Fixed uninitialized AI model image when annotating consecutive images ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Fixed `double_click="close"` behavior requiring fewer than 4 points to close a polygon ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Fixed duplicate last point in polygon computed from AI points ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Treated zero-length lines as lines to avoid unintuitive behavior ([#1262](https://github.com/wkentaro/labelme/pull/1262))
- Fixed portrait-orientation image handling in Segment Anything Model ([#1262](https://github.com/wkentaro/labelme/pull/1262))

## [5.2.1] - 2023-05-16

### Fixed

- Fixed an undefined label description when the label popup is disabled ([#1270](https://github.com/wkentaro/labelme/pull/1270))

## [5.2.0] - 2023-04-06

### Added

- Added a description field to labels ([#1255](https://github.com/wkentaro/labelme/pull/1255))

### Fixed

- Fixed floating-point coordinate handling when moving multiple shapes on the canvas ([#1253](https://github.com/wkentaro/labelme/pull/1253))
- Fixed removing a vertex from a polygon or linestrip that was already at its minimum point count, which would produce a malformed shape ([#1254](https://github.com/wkentaro/labelme/pull/1254))

## [5.1.1] - 2022-11-20

### Fixed

- Removed the overly broad matplotlib version restriction from install requirements; the constraint is only needed when building the standalone executable, so regular installs can now use any matplotlib version

## [5.1.0] - 2022-11-15

### Added

- Added crosshair display alongside cursor on the canvas

### Removed

- **Breaking:** Removed Docker support as it was unstable and Docker Hub policy changed

## [5.0.5] - 2022-10-30

### Fixed

- Fixed a TypeError when using the polygon annotation tool on Python 3.10 caused by an internal point type mismatch

## [5.0.4] - 2022-10-24

### Fixed

- Fixed a crash when opening a directory caused by the label list widget returning a fractional size instead of an integer size
- Fixed a crash when scrolling annotations loaded from older JSON files due to a float value passed to the scroll bar
- Fixed removing the last point of a shape not always marking the annotation as modified

## [5.0.3] - 2022-10-23

### Fixed

- Fixed type errors when annotating on Python 3.10

## [5.0.2] - 2022-09-26

### Fixed

- Fixed a crash when editing a label whose name does not exist in the label list
- Escaped label names so that labels containing angle brackets (e.g. `<cat>`, `<background>`) are displayed and handled correctly

## [5.0.1] - 2022-03-03

_No user-facing changes._

## [5.0.0] - 2022-02-26

### Changed

- Sorted files in the file browser using OS-native natural order ([#990](https://github.com/wkentaro/labelme/pull/990))

### Removed

- **Breaking:** Dropped Python 2 support ([#993](https://github.com/wkentaro/labelme/pull/993))
- **Breaking:** Dropped PyQt4 support ([#994](https://github.com/wkentaro/labelme/pull/994))
- Removed the man page; use `--help` instead ([#996](https://github.com/wkentaro/labelme/pull/996))

## v4.6.0 and earlier

See the [GitHub Releases](https://github.com/wkentaro/labelme/releases) page for changelogs of v4.6.0 and earlier.

[5.0.0]: https://github.com/wkentaro/labelme/compare/v4.6.0...v5.0.0
[5.0.1]: https://github.com/wkentaro/labelme/compare/v5.0.0...v5.0.1
[5.0.2]: https://github.com/wkentaro/labelme/compare/v5.0.1...v5.0.2
[5.0.3]: https://github.com/wkentaro/labelme/compare/v5.0.2...v5.0.3
[5.0.4]: https://github.com/wkentaro/labelme/compare/v5.0.3...v5.0.4
[5.0.5]: https://github.com/wkentaro/labelme/compare/v5.0.4...v5.0.5
[5.1.0]: https://github.com/wkentaro/labelme/compare/v5.0.5...v5.1.0
[5.1.1]: https://github.com/wkentaro/labelme/compare/v5.1.0...v5.1.1
[5.10.0]: https://github.com/wkentaro/labelme/compare/v5.9.1...v5.10.0
[5.10.1]: https://github.com/wkentaro/labelme/compare/v5.10.0...v5.10.1
[5.11.0]: https://github.com/wkentaro/labelme/compare/v5.10.1...v5.11.0
[5.11.1]: https://github.com/wkentaro/labelme/compare/v5.11.0...v5.11.1
[5.11.2]: https://github.com/wkentaro/labelme/compare/v5.11.1...v5.11.2
[5.11.3]: https://github.com/wkentaro/labelme/compare/v5.11.2...v5.11.3
[5.11.4]: https://github.com/wkentaro/labelme/compare/v5.11.3...v5.11.4
[5.2.0]: https://github.com/wkentaro/labelme/compare/v5.1.1...v5.2.0
[5.2.1]: https://github.com/wkentaro/labelme/compare/v5.2.0...v5.2.1
[5.3.0]: https://github.com/wkentaro/labelme/compare/v5.2.1...v5.3.0
[5.3.1]: https://github.com/wkentaro/labelme/compare/v5.3.0...v5.3.1
[5.4.0]: https://github.com/wkentaro/labelme/compare/v5.3.1...v5.4.0
[5.4.1]: https://github.com/wkentaro/labelme/compare/v5.4.0...v5.4.1
[5.5.0]: https://github.com/wkentaro/labelme/compare/v5.4.1...v5.5.0
[5.6.0]: https://github.com/wkentaro/labelme/compare/v5.5.0...v5.6.0
[5.6.1]: https://github.com/wkentaro/labelme/compare/v5.6.0...v5.6.1
[5.7.0]: https://github.com/wkentaro/labelme/compare/v5.6.1...v5.7.0
[5.8.0]: https://github.com/wkentaro/labelme/compare/v5.7.0...v5.8.0
[5.8.1]: https://github.com/wkentaro/labelme/compare/v5.8.0...v5.8.1
[5.8.2]: https://github.com/wkentaro/labelme/compare/v5.8.1...v5.8.2
[5.8.3]: https://github.com/wkentaro/labelme/compare/v5.8.2...v5.8.3
[5.9.0]: https://github.com/wkentaro/labelme/compare/v5.8.3...v5.9.0
[5.9.1]: https://github.com/wkentaro/labelme/compare/v5.9.0...v5.9.1
[6.0.0]: https://github.com/wkentaro/labelme/compare/v5.11.4...v6.0.0
[6.0.1]: https://github.com/wkentaro/labelme/compare/v6.0.0...v6.0.1
[6.0.2]: https://github.com/wkentaro/labelme/compare/v6.0.1...v6.0.2
[6.1.0]: https://github.com/wkentaro/labelme/compare/v6.0.2...v6.1.0
[6.1.1]: https://github.com/wkentaro/labelme/compare/v6.1.0...v6.1.1
[6.1.2]: https://github.com/wkentaro/labelme/compare/v6.1.1...v6.1.2
[6.1.3]: https://github.com/wkentaro/labelme/compare/v6.1.2...v6.1.3
[6.2.0]: https://github.com/wkentaro/labelme/compare/v6.1.3...v6.2.0
[6.3.0]: https://github.com/wkentaro/labelme/compare/v6.2.0...v6.3.0
[6.3.1]: https://github.com/wkentaro/labelme/compare/v6.3.0...v6.3.1
[7.0.0]: https://github.com/wkentaro/labelme/compare/v6.3.1...v7.0.0
[7.0.1]: https://github.com/wkentaro/labelme/compare/v7.0.0...v7.0.1
[7.0.2]: https://github.com/wkentaro/labelme/compare/v7.0.1...v7.0.2
[7.0.3]: https://github.com/wkentaro/labelme/compare/v7.0.2...v7.0.3
[7.0.4]: https://github.com/wkentaro/labelme/compare/v7.0.3...v7.0.4
[unreleased]: https://github.com/wkentaro/labelme/compare/v7.0.4...HEAD
