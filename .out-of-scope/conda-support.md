# Conda / conda-forge Support

labelme does not officially support or maintain a conda / conda-forge
distribution. The only recommended installation paths are `uv` and `pip`
(see https://labelme.io/docs/install-labelme-terminal). The
`conda-forge/labelme-feedstock` package exists but is community-maintained and
not endorsed; its version lag is not something this project will own.

## Why this is out of scope

The conda package does not live in this repository. conda-forge packages are
maintained in separate `conda-forge/<name>-feedstock` repos, and the maintainer
of labelme has no access to `conda-forge/labelme-feedstock`. There is nothing in
this codebase to change that would fix the lag — the work is entirely in a repo
we do not control.

conda-forge already automates the part that can be automated for free:
`regro-cf-autotick-bot` opens a version-bump PR on the feedstock within hours of
each PyPI release. The lag exists only because those bot PRs are not being
merged (inactive feedstock maintainer), not because of anything upstream.

Making it truly zero-touch would require a one-time, externally-gated human
action that an agent cannot perform: getting added to the feedstock's
maintainer list (approved by an existing maintainer or conda-forge core), then
enabling `bot: {automerge: true}` in `conda-forge.yml` so the bot's version PRs
self-merge on green CI. That is ongoing custodianship of a third-party package
for a distribution channel we never recommended.

The technical motivation raised (MKL-accelerated NumPy/SciPy via conda-forge)
does not apply: labelme does not depend on scipy, and `uv`/`pip` install of the
labelme stack does not need conda for performance.

## If this is ever revisited

The path is a one-time setup, not a code change in this repo:

1. Open a PR on `conda-forge/labelme-feedstock` adding the maintainer to
   `recipe/meta.yaml` `extra.recipe-maintainers`.
1. Once merged, enable conda-forge bot automerge so future
   `regro-cf-autotick-bot` version PRs merge automatically.

After that it is genuinely zero-effort. Until someone wants to take on that
custodianship, conda stays unsupported and `uv`/`pip` remain the single
recommended path.

## Prior requests

- #1567 — "Outdated Version on Conda Forge"
- #2207 — "Automate conda-forge release bump to stop version lag"
