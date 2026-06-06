# Settings architecture

The user Config stays a single human-readable YAML file (`~/.labelmerc`), edited
both by a GUI Settings dialog and by hand. The dialog writes changes through
ruamel.yaml as sparse, comment-preserving Overrides (only non-default keys, each
pruned when reset to its default) and applies them immediately, with no
OK/Apply/Cancel. Window geometry and dock layout stay in a separate Qt QSettings
store (Window State), which is not part of the Config.

## Considered options

- **QSettings for all preferences** — rejected: an opaque per-platform binary
  store that is not diffable, portable, or version-controllable, and would
  create a second writable source of truth alongside the YAML file.
- **Migrate the Config to JSON (or QSettings) with a one-time conversion** —
  rejected: it forces a risky migration of every existing `~/.labelmerc`, and
  comment preservation needs a round-trip parser either way, so YAML wins
  without a storage-format conversion. Key renames are still applied in place by
  `_migrate_config_from_file`; only a whole-file format conversion is avoided.
- **OK/Apply/Cancel dialog** — rejected in favor of immediate-apply to match
  modern settings UIs (macOS System Settings, VS Code); Settings are reversible
  by re-editing, so a Cancel button buys little.

## Consequences

- Comment-preserving sparse writes require ruamel.yaml, now the project's only
  YAML library (PyYAML was dropped).
- The dialog edits the effective Config File, so it is disabled only when
  `--config` supplies a YAML expression (no file to write to) or when per-session
  CLI override flags are present. A custom `--config <file>` path (e.g. a
  `labelmerc` beside a standalone build) is editable.
