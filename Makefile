ifneq ($(OS),Windows_NT)
	SHELL := bash
endif

.PHONY: help setup format lint test
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

format:  # Format code
	$(call exec,uv run ruff format)
	$(call exec,uv run ruff check --fix)
	$(call exec,uv run taplo fmt)
	$(call exec,uv run mdformat $(shell git ls-files "*.md"))

lint:  # Lint code
	$(call exec,uv run ruff format --check)
	$(call exec,uv run ruff check)
	$(call exec,uv run ty check --no-progress)
	$(call exec,uv run taplo fmt --check)
	$(call exec,uv run mdformat --check $(shell git ls-files "*.md"))

check_translate: update_translate
	$(call exec,git diff --exit-code labelme/translate)
	@if grep -r 'type="unfinished"' labelme/translate/*.ts; then \
		echo "$(RED)Error: unfinished translations found$(NC)"; \
		exit 1; \
	fi

check: lint check_translate # Run checks

test:  # Run tests
	$(call exec,QT_QPA_PLATFORM=offscreen uv run pytest -v tests/ --numprocesses=auto)

update_translate:
	$(call exec,uv run --no-sync tools/update_translate.py)
