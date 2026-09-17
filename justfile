set shell := ["bash", "-eu", "-o", "pipefail", "-c"]
set script-interpreter := ["bash", "-eu", "-o", "pipefail"]
set positional-arguments
set default-list
set minimum-version := "1.58.0"

# Setup the development environment
setup:
    uv sync

# Lint code
lint:
    uv run ruff format --check
    uv run ruff check
    uv run gruff check .
    uv run ty check --no-progress
    git ls-files "*.toml" | xargs uv run taplo fmt --check
    git ls-files "*.md" | xargs uv run mdformat --check
    git ls-files "*.yml" "*.yaml" | xargs uv run yamlfix --check
    uv run typos

# Format code
format:
    uv run ruff format
    uv run ruff check --fix
    git ls-files "*.toml" | xargs uv run taplo fmt
    git ls-files "*.md" | xargs uv run mdformat
    git ls-files "*.yml" "*.yaml" | xargs uv run yamlfix

# Run tests
test args=env("PYTEST_ARGS", "--numprocesses=auto"):
    uv run pytest -v tests/ {{ args }}

# Regenerate the translation catalogs
update_translate:
    uv run tools/update_translate.py

# Fail if the translation catalogs are stale or incomplete
check_translate:
    uv run tools/update_translate.py --check

# Replay released configs (requires full release tags)
check_config_migrations:
    uv run python -m tools.check_config_migrations

# Run tests with coverage
coverage: (test "--cov=labelme --cov-report=term-missing")

# Prepare a release
[script]
release version=env("VERSION", ""):
    version="$1"
    if test -z "$version"; then
        fragments=$(find changelog.d -maxdepth 1 -type f \( \
            -name "*.added.md" -o -name "*.changed.md" -o \
            -name "*.deprecated.md" -o -name "*.removed.md" -o \
            -name "*.fixed.md" -o -name "*.security.md" \))
        latest=$(git tag --sort=-v:refname |
            grep -Em1 "^v[0-9]+\.[0-9]+\.[0-9]+$" || true)
        if test -n "$fragments" && test -n "$latest"; then
            latest_version=${latest#v}
            major=${latest_version%%.*}
            remainder=${latest_version#*.}
            minor=${remainder%%.*}
            patch=${remainder#*.}
            if grep -q '\*\*Breaking:\*\*' $fragments; then
                next=$((major + 1)).0.0
            elif find changelog.d -maxdepth 1 -type f \( \
                -name "*.added.md" -o -name "*.changed.md" -o \
                -name "*.deprecated.md" -o -name "*.removed.md" \) \
                -print -quit | grep -q .; then
                next=$major.$((minor + 1)).0
            else
                next=$major.$minor.$((patch + 1))
            fi
            echo "suggested: just release $next" >&2
        else
            echo "usage: just release X.Y.Z" >&2
        fi
        echo "recent releases:" >&2
        git tag --sort=-v:refname | sed -n "1,5{s/^/  /;p}" >&2
        exit 1
    fi
    uv run towncrier build --yes --version "$version"
    uv run mdformat CHANGELOG.md
    git add CHANGELOG.md
    printf "\n\033[1;32mNext steps\033[0m\n"
    echo "  git commit -am \"chore: prep $version release\""
    echo "  git tag v$version"
    echo "  git push origin main v$version"
