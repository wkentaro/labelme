# Color theme

labelme exposes a `color_theme` Setting with three values — `system` (default),
`light`, and `dark` — surfaced at the top of the "General" section of the Settings
dialog as an enum control labelled "System default" / "Light" / "Dark" (mirroring
the language picker's "System default"). It is applied by calling
`QStyleHints.setColorScheme(...)`, which lets the pinned Fusion style generate the
matching palette itself (`Unknown` follows the OS, `Light`/`Dark` force a scheme
regardless of the OS). This replaces the previous unconditional force-light
override in `__main__.py`.

Qt swaps the palette, but cached `QIcon` pixmaps do not follow it. The monochrome
toolbar icons are therefore authored as `fill="currentColor"` and tinted to the
active palette's `WindowText` color by a `QIconEngine` that reads the palette at
paint time, so they re-tint live when `colorSchemeChanged` fires (the single
re-theme hook for both user changes and OS flips). Selection is by content, not an
allowlist: `new_icon` tints any SVG containing the `currentColor` token, so a new
monochrome icon authored with `fill="currentColor"` is theme-aware automatically.
The five semantic accent icons (blue `floppy-disk`/`folders`/`folder-open`, red
`trash`/`file-x`) keep their fixed colors, since their color carries meaning and is
legible on both backgrounds; the other 26 are tinted.

Theming is scoped to *chrome*, not annotation *data*. Chrome colors must follow
the palette: the toolbar icons, the AI-button highlight (previously a hardcoded
`#FFFFCC`/`#E6E6A0` in `_app.py`), and the canvas crosshair (previously a
hardcoded `QColor(0, 0, 0)` in `canvas.py`, which is invisible against the dark
margin in out-of-bounds mode). Annotation colors drawn over the image — the shape
line/fill colors and white vertex fills in `_shape_render.py` — are data, not
chrome, and stay fixed across themes. Adding a chrome color must go through a
palette role, not a literal; the audit is a sweep of `_widgets/` and `_app.py`
for color literals, triaged chrome-vs-data, not a single fix.

## Considered options

- **App-owned light/dark `QPalette`s** — rejected: Qt 6.8's `setColorScheme`
  makes Fusion produce good light and dark palettes for free, so hand-maintaining
  ~12 role colors per theme is redundant. The cost is that "System" dark adopts
  the platform palette and so varies slightly per OS; this is an acceptable trade
  for not owning palette tables.
- **Two icon sets (separate light/dark SVGs)** — rejected: doubles the icon
  assets and every future icon, and does not scale to a third theme. Tinting one
  monochrome source (the template-image pattern) is the standard approach.
- **Restart-required theme change** — rejected: it would be the only Setting that
  is not immediate-apply (see ADR-0001) and would make "follow system" sample the
  OS only at launch instead of tracking `colorSchemeChanged` live.
- **A Qt theming library (`qdarktheme`/PyQtDarkTheme, `qdarkstyle`, `qt-material`)**
  — rejected: these are the pre-6.8 way to get dark Qt, each shipping a full QSS
  stylesheet that would fight the pinned Fusion style. `setColorScheme` makes the
  native style produce both palettes with no dependency and no stylesheet to
  maintain, so the library's core value no longer applies. (Recorded here so the
  dependency is not reintroduced later as an apparent simplification.)

## Consequences

- The PySide6 floor moves from `>=6.5` to `>=6.8`, since `setColorScheme` and
  `Qt.ColorScheme` are 6.8 APIs.
- The default changes observable behavior on upgrade: users on a dark-themed OS,
  who were previously forced to light, now get dark labelme. With the icon tinting
  in place this is the intended result, not a regression.
- New icons must be authored with `fill="currentColor"` to participate in
  theming; an icon shipped with a hardcoded dark fill will be invisible on a dark
  background.
- `colorSchemeChanged` is the one place the running app re-themes. Two things do
  not follow Qt's live palette swap on their own and the handler fixes both:
  cached `QIcon` pixmaps (cleared via `QPixmapCache`), and any widget carrying a
  stylesheet — `QStyleSheetStyle` resolves `palette(...)` references and pins the
  widget's palette at polish time, so a styled toolbar (the vertical toolbars use
  `QToolBar::separator { background: palette(mid) }`) stays stuck on the old
  scheme until its stylesheet is re-applied. The handler re-applies each widget's
  stylesheet and repaints all widgets. (`grab()`-based screenshots cannot catch
  this: grab re-renders the tree fresh, so it always shows the new palette even
  when the on-screen widget never repainted.)
