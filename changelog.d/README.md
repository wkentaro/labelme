# Changelog fragments

Each user-facing change ships as one file in this directory instead of editing
`CHANGELOG.md` directly, so concurrent pull requests never conflict.

- Filename: `<PR number>.<type>.md`, where `<type>` is one of `added`,
  `changed`, `deprecated`, `removed`, `fixed`, `security` (the Keep a Changelog
  section the entry belongs in). A second fragment for the same PR and type
  gets a counter suffix: `1234.fixed.2.md`. Add the fragment after opening the
  PR, when its number is known.
- Content: the entry as a single line without a bullet or PR link, e.g.
  `Fixed the thing`. Towncrier adds the link from the filename. Prefix
  `**Breaking:**` for changes that bump the major version.

There is no minimum release size. Release a minor version for any ready
backward-compatible feature or improvement; do not wait to accumulate changes.
Release patches for backward-compatible fixes only.

To release version `X.Y.Z` on `YYYY-MM-DD`:

1. Run `uv run towncrier build --yes --version X.Y.Z --date YYYY-MM-DD`.
2. Add `[X.Y.Z]: https://github.com/wkentaro/labelme/compare/v<previous>...vX.Y.Z`
   to the link list at the bottom of `CHANGELOG.md`.
3. Commit the updated changelog and deleted fragments, then tag that commit.

Prerelease tags render pending fragments without changing files.
