# Menu conventions

Menu items, toolbar buttons, and dialogs follow one set of rules, and
`tests/e2e/menu_conventions_test.py` enforces the ones that can be checked
mechanically.

1. An action has one name everywhere it appears: menu, toolbar, empty state,
   and the title of the dialog it opens.
2. Menu items, buttons, and window titles use title case. Tooltips, messages,
   and labels use sentence case.
3. An item that asks for more input before it acts ends with "…" (Open File…,
   Save As…, Edit Label…).
4. Commands carry an icon. Checkable settings carry none, because the
   checkmark shows their state. Fit to Window and Fit to Selection keep their
   icons because they are also toolbar buttons. Each icon belongs to one
   action.
5. Action text has no line breaks. Toolbar buttons get theirs from the icon
   text that `new_action` derives.
6. Tooltips build modifier hints from `QKeySequence` native text, so macOS
   shows ⌘ where Qt maps Ctrl to Command.
7. User-visible terms follow `GLOSSARY.md`.
8. The View menu ends with a separator. macOS appends Enter Full Screen to any
   menu titled View, and its SF Symbol image makes AppKit indent the icon-less
   items of whatever section it joins. Qt hands Labelme's icons to AppKit as
   bitmaps, which do not trigger that indent, so without the separator only the
   last section of the menu is indented.

The test keeps an allowlist of known violations per rule. A fix removes its
entry, and an entry that no longer violates fails the test, so the list only
shrinks.

## Considered options

- **An icon on every item, including toggles** (macOS 26 style). Rejected:
  Qt cannot hand AppKit SF Symbols, so toggles would get bitmap icons that sit
  beside a checkmark column, and the menus would still not match native apps.
