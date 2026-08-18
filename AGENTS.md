# AGENTS.md

## Changelog

Record user-facing changes to the packaged application as towncrier fragments, following `changelog.d/README.md`; never edit `CHANGELOG.md` directly. Changes confined to `examples/` are outside the changelog's scope. Prefix `**Breaking:**` for changes that bump the major version.

## Agent skills

### Issue tracker

Issues are tracked as GitHub issues on `wkentaro/labelme` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles map 1:1 to label strings of the same name (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` and `docs/adr/` at the repo root (created lazily by `/grill-with-docs`). See `docs/agents/domain.md`.

### AI Assist

Treat AI Assist Setting Controls as proactive guidance. Enforce Prompt Compatibility at runtime before model download or inference, and reject an incompatible prompt without changing the model Setting.

### GUI QA

Check human-visible desktop behavior — GUI regression, release acceptance, visual or accessibility inspection — with `.agents/skills/test-labelme-gui/SKILL.md`. Keep deterministic logic in pytest.
