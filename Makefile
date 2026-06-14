ifneq ($(OS),Windows_NT)
	SHELL := bash
endif

.PHONY: help setup format lint test coverage update_translate
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
	$(call exec,uv run ty check --no-progress)
	$(call exec,git ls-files "*.toml" | xargs uv run taplo fmt --check)
	$(call exec,git ls-files "*.md" | xargs uv run mdformat --check)
	$(call exec,git ls-files "*.yml" "*.yaml" | xargs uv run yamlfix --check)
	$(call exec,uv run typos)
	$(call exec,git diff --exit-code labelme/translate)
	@if grep -r 'type="unfinished"' labelme/translate/*.ts; then \
		printf '\033[1;31mError: unfinished translations found\033[0m\n'; \
		exit 1; \
	fi

format:  # Format code
	$(call exec,uv run ruff format)
	$(call exec,uv run ruff check --fix)
	$(call exec,git ls-files "*.toml" | xargs uv run taplo fmt)
	$(call exec,git ls-files "*.md" | xargs uv run mdformat)
	$(call exec,git ls-files "*.yml" "*.yaml" | xargs uv run yamlfix)

test:  # Run tests
	$(call exec,uv run pytest -v tests/ $(PYTEST_ARGS))

update_translate:
	$(call exec,uv run tools/update_translate.py)

coverage:  # Run tests with coverage
	$(call exec,uv run pytest -v tests/ --numprocesses=auto --cov=labelme --cov-report=term-missing)
