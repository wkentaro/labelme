ifneq ($(OS),Windows_NT)
	SHELL := bash
endif

.PHONY: help setup format lint test coverage update_translate check_translate release
.DEFAULT_GOAL := help

PYTEST_ARGS ?= --numprocesses=auto

define exec
	@uv run --no-sync python -c "print('\033[1;36m$(1)\033[0m')"
	@$(1)
endef

help:
	@uv run --no-sync python -c "import re; lines=open('Makefile').read().splitlines(); print('\033[1;32mAvailable targets:\033[0m'); [print(f'  \033[1;36m{m.group(1):<20s}\033[0m {m.group(2)}') for l in lines if (m:=re.match(r'^([a-zA-Z_-]+):.*?# (.+)$$',l))]"

setup:  # Setup the development environment
	$(call exec,uv sync)

lint:  # Lint code
	$(call exec,uv run ruff format --check)
	$(call exec,uv run ruff check)
	$(call exec,uv run gruff check .)
	$(call exec,uv run ty check --no-progress)
	$(call exec,git ls-files "*.toml" | xargs uv run taplo fmt --check)
	$(call exec,git ls-files "*.md" | xargs uv run mdformat --check)
	$(call exec,git ls-files "*.yml" "*.yaml" | xargs uv run yamlfix --check)
	$(call exec,uv run typos)

format:  # Format code
	$(call exec,uv run ruff format)
	$(call exec,uv run ruff check --fix)
	$(call exec,git ls-files "*.toml" | xargs uv run taplo fmt)
	$(call exec,git ls-files "*.md" | xargs uv run mdformat)
	$(call exec,git ls-files "*.yml" "*.yaml" | xargs uv run yamlfix)

test:  # Run tests
	$(call exec,uv run pytest -v tests/ $(PYTEST_ARGS))

update_translate:  # Regenerate the translation catalogs
	$(call exec,uv run tools/update_translate.py)

check_translate:  # Fail if the translation catalogs are stale or incomplete (CI and release gate)
	$(call exec,uv run tools/update_translate.py --check)

coverage:  # Run tests with coverage
	$(MAKE) test PYTEST_ARGS="--cov=labelme --cov-report=term-missing"

release:  # Prepare a release: make release VERSION=X.Y.Z
	@test -n "$(VERSION)" || { \
		echo "usage: make release VERSION=X.Y.Z" >&2; \
		echo "recent releases:" >&2; \
		git tag --sort=-v:refname | head -5 | sed "s/^/  /" >&2; \
		exit 1; \
	}
	$(call exec,uv run towncrier build --yes --version $(VERSION))
	$(call exec,uv run mdformat CHANGELOG.md)
	@printf "\n\033[1;32mNext steps\033[0m\n"
	@echo "  git commit -am \"chore: prep $(VERSION) release\""
	@echo "  git tag v$(VERSION)"
	@echo "  git push origin main v$(VERSION)"
