ifneq ($(OS),Windows_NT)
	# On Unix-based systems, use ANSI codes
	BLUE = \033[36m
	BOLD_BLUE = \033[1;36m
	BOLD_GREEN = \033[1;32m
	RED = \033[31m
	YELLOW = \033[33m
	BOLD = \033[1m
	NC = \033[0m
endif

escape = $(subst $$,\$$,$(subst ",\",$(subst ',\',$(1))))

define exec
	@echo "$(BOLD_BLUE)$(call escape,$(1))$(NC)"
	@$(1)
endef

help:
	@echo "$(BOLD_GREEN)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-].+:.*?# .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?# "}; \
		{printf "  $(BOLD_BLUE)%-20s$(NC) %s\n", $$1, $$2}'

PACKAGE_NAME:=labelme

setup:  # Setup the development environment
	$(call exec,uv sync --dev)

format:  # Format code
	$(call exec,uv run ruff format)
	$(call exec,uv run ruff check --fix)

lint:
	$(call exec,uv run ruff format --check)
	$(call exec,uv run ruff check)
	$(call exec,uv run ty check --no-progress)

mypy:
	$(call exec,uv run mypy --package $(PACKAGE_NAME))

check_translate: update_translate
	$(call exec,git diff --exit-code labelme/translate)

check: lint check_translate # Run checks

test:  # Run tests
	$(call exec,uv run pytest -v tests/)

build:  # Build the package
	$(call exec,uv build)

update_translate:
	$(call exec,uv run --no-sync tools/update_translate.py)
