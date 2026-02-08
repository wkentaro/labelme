# AGENTS.md

Guidelines for AI coding agents working in this repository.

## Project Overview

Labelme is a graphical image annotation tool built with Python 3.10+ and PyQt5.
It supports polygon, rectangle, circle, line, point, and mask annotations, with
AI-assisted annotation via SAM2 and YOLOWorld models.

## Build & Development Commands

Package manager is **uv** (not pip/poetry/conda). All commands use `uv run`.

```bash
make setup            # Install dependencies (uv sync)
make format           # Auto-format with ruff + auto-fix lint issues
make lint             # Check formatting (ruff) + linting (ruff) + type checking (ty)
make check            # lint + translation file consistency check
make test             # Run all tests (uv run pytest -v tests/)
```

### Running Individual Tests

```bash
uv run pytest tests/unit/ -v                                    # Unit tests only
uv run pytest tests/e2e/ -v                                     # E2E tests only
uv run pytest tests/unit/config_test.py -v                      # Single test file
uv run pytest tests/e2e/smoke_test.py::test_MainWindow_open -v  # Single test function
uv run pytest tests/ -k "test_canvas" -v                        # Tests matching pattern
```

### Linting & Type Checking Individually

```bash
uv run ruff format --check   # Check formatting (no changes)
uv run ruff format           # Apply formatting
uv run ruff check            # Lint check
uv run ruff check --fix      # Lint check with auto-fix
uv run ty check --no-progress  # Type checking
```

## Architecture

| Module | Purpose |
|--------|---------|
| `labelme/app.py` | Main `MainWindow` class, central orchestration |
| `labelme/shape.py` | `Shape` data class for all annotation types |
| `labelme/_label_file.py` | JSON annotation file I/O (`LabelFile`, `ShapeDict`) |
| `labelme/widgets/canvas.py` | Drawing canvas, shape rendering and interaction |
| `labelme/widgets/` | PyQt5 UI components (dialogs, toolbars, lists) |
| `labelme/_automation/` | AI-assisted annotation (SAM2, YOLOWorld) |
| `labelme/cli/` | CLI tools (`draw_json`, `draw_label_png`, `export_json`) |
| `labelme/config/` | Config loading and `default_config.yaml` |
| `labelme/utils/` | Image conversion, shape math, Qt helpers |

## Code Style

### Formatter & Linter

- **ruff** for formatting (black-compatible) and linting (pycodestyle, pyflakes, isort, pyupgrade)
- **ty** for type checking (not mypy)
- Config is in `pyproject.toml` under `[tool.ruff.*]`

### Imports

Force single-line imports, sorted by ruff isort. One import per line, no multi-imports.

```python
from __future__ import annotations      # If needed for forward refs, always first

import functools                         # 1. stdlib
import json
from pathlib import Path
from typing import Literal

import numpy as np                       # 2. third-party
from PyQt5 import QtCore
from PyQt5 import QtWidgets

from labelme._label_file import LabelFile  # 3. local absolute
from labelme.utils import shape_to_mask
```

`__init__.py` files may have unused imports (re-exports); these are suppressed via
`"__init__.py" = ["F401"]` in ruff config.

### Naming Conventions

- **Classes**: `PascalCase` (`MainWindow`, `LabelFile`, `Shape`)
- **Public methods**: `camelCase` (legacy Qt convention): `addLabel()`, `saveFile()`
- **New private methods**: `_snake_case` with leading underscore: `_load_file()`, `_update_shape_color()`
- **Variables**: `snake_case` (`label_file`, `image_data`)
- **Constants**: `UPPER_SNAKE_CASE` (`CURSOR_DEFAULT`, `PEN_WIDTH`)
- **Private attributes/modules**: leading underscore (`_config`, `_label_file.py`)

When adding new methods, prefer `_snake_case`. Existing `camelCase` methods should
not be renamed without reason.

### Type Hints

- Use modern union syntax: `str | None` (not `Optional[str]`)
- Use `from __future__ import annotations` when forward references are needed
- Numpy arrays: `NDArray[np.uint8]`, `NDArray[np.bool_]`
- Structured dicts: `TypedDict`
- Constrained strings: `Literal["polygon", "rectangle", "mask"]`
- Add `# type: ignore[specific-code]` with specific error codes, not bare `# type: ignore`

### String Formatting

- Use f-strings for interpolation
- Use `self.tr(...)` for user-facing strings that need i18n translation
- Loguru uses positional formatting: `logger.info("Loaded {} shapes", count)`

### Error Handling

- `assert` for internal invariants and preconditions (not user input validation)
- `ValueError` for invalid configuration or unexpected inputs
- `LabelFileError` for annotation file I/O errors
- **loguru** for logging (not stdlib `logging`): `from loguru import logger`
- Qt `QMessageBox` for user-facing error dialogs

### General Patterns

- `functools.partial` for action callbacks in the GUI
- `types.SimpleNamespace` for `self.actions` and `self.menus`
- Properties with setters for validation (`Shape.shape_type`, `Canvas.createMode`)
- No unnecessary comments; code should be self-explanatory

## Testing

### Framework

pytest + pytest-qt. Config in `pyproject.toml`: `qt_api = "pyqt5"`.

### File Naming

Test files: `*_test.py` (not `test_*.py`). Test functions: `test_*`.

### Structure

```
tests/
  conftest.py       # data_path fixture (copies tests/data/ to tmp_path)
  data/             # Test fixtures (images, JSON annotations)
  e2e/              # GUI tests using pytest-qt
    conftest.py     # _isolated_qtsettings fixture, show_window_and_wait_for_imagedata()
  unit/             # Unit tests
```

### Key Fixtures

- `data_path` (root conftest, function-scoped): copies `tests/data/` to `tmp_path`
- `_isolated_qtsettings` (e2e conftest, autouse): isolates QSettings between tests
- `show_window_and_wait_for_imagedata(qtbot, win)`: shows window and waits for async image load

### Writing Tests

```python
@pytest.mark.gui
def test_example(qtbot: QtBot, data_path: Path) -> None:
    win = labelme.app.MainWindow(filename=str(data_path / "annotated" / "apc.json"))
    qtbot.addWidget(win)
    show_window_and_wait_for_imagedata(qtbot, win)
    assert win.imageData is not None
    win.close()
```

Type-annotate test functions. Use `-> None` return type. Mark GUI tests with
`@pytest.mark.gui`. Tests run in CI on Ubuntu only (requires Xvfb for headless Qt).

## Translations

- Translation files: `labelme/translate/` (`.ts` source, `.qm` compiled)
- After editing `.ts` files: `make update_translate`
- Do not run `pyside6-lrelease` or `lrelease` directly

## Commit Convention

Use conventional commits:

```
feat: add polygon splitting tool
fix: correct shape color when label changes
refactor: extract config validation to separate function
test: add canvas zoom unit tests
docs: update annotation format documentation
chore: bump ruff to 0.12.11
perf: cache label colormap lookups
ci: add Windows build to CI matrix
i18n: add Korean translation
```

## CI

GitHub Actions (`.github/workflows/ci.yml`):
- **check** job: `make check` (lint + type check + translation consistency)
- **build** job: matrix across Windows/macOS/Ubuntu; tests run on Ubuntu only with Xvfb
