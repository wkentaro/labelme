# AGENTS.md

## Changelog

User-facing changes go in `CHANGELOG.md` under `## [Unreleased]` ([Keep a Changelog](https://keepachangelog.com/) format), filed in the right `### Added/Changed/Removed/Fixed` subsection with the PR number linked. Prefix `**Breaking:**` for changes that bump the major version. At release, the `[Unreleased]` section is promoted to the new version.

## Agent skills

### Issue tracker

Issues are tracked as GitHub issues on `wkentaro/labelme` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles map 1:1 to label strings of the same name (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` and `docs/adr/` at the repo root (created lazily by `/grill-with-docs`). See `docs/agents/domain.md`.
