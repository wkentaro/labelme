# Changelog fragments

Each user-facing change ships as one file here instead of editing
`CHANGELOG.md` directly, so concurrent pull requests never conflict.

Name the file `<PR number>.<type>.md`, where `<type>` is one of `added`,
`changed`, `deprecated`, `removed`, `fixed`, or `security`. A second fragment
for the same PR and type takes a counter suffix: `1234.fixed.2.md`. Add the
fragment after opening the PR, when its number is known.

Write the entry as a single line without a bullet or PR link; towncrier adds
the link from the filename. Prefix `**Breaking:**` for changes that bump the
major version.

Release a minor version for any ready backward-compatible improvement and a
patch for backward-compatible fixes; there is no minimum release size.

To release version `X.Y.Z`:

1. Run `uv run towncrier build --yes --version X.Y.Z`.
2. Commit the updated changelog and deleted fragments, then tag that commit.

Pushing the tag publishes to PyPI and creates the GitHub release from the
matching `CHANGELOG.md` section.
