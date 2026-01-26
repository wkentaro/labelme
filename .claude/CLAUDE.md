# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Labelme is a graphical image annotation tool built with Python and PyQt5. It supports polygon, rectangle, circle, line, and point annotations, with AI-assisted annotation features using SAM and YOLOWorld models.

## Development Commands

```bash
make setup            # Install dependencies (uses uv sync)
make format           # Format code with ruff
make lint             # Run linting (ruff) and type checking (ty)
make test             # Run all tests
make check            # Run lint + translation checks
make update_translate # Update .ts and compile .qm translation files
```

### Running Individual Tests

```bash
uv run pytest tests/e2e/smoke_test.py -v              # Single test file
uv run pytest tests/e2e/smoke_test.py::test_MainWindow_open -v  # Single test
uv run pytest tests/unit/ -v                          # Unit tests only
uv run pytest tests/e2e/ -v                           # E2E tests only
```

## Architecture

### Core Modules

- `labelme/app.py` - Main application window (`MainWindow` class)
- `labelme/shape.py` - Shape class handling all annotation types
- `labelme/_label_file.py` - JSON annotation file serialization
- `labelme/widgets/canvas.py` - Drawing canvas with shape manipulation
- `labelme/widgets/` - PyQt5 UI components (dialogs, toolbars, lists)
- `labelme/_automation/` - AI-assisted annotation (SAM, YOLOWorld integration)
- `labelme/cli/` - Command-line tools for export and visualization

### Entry Points

- `labelme` - Main GUI application
- `labelme_draw_json` - Visualize annotations
- `labelme_draw_label_png` - Export label masks
- `labelme_export_json` - Convert annotations to various formats

## Testing Patterns

### Test Organization

- `tests/e2e/` - GUI tests using pytest-qt
- `tests/unit/` - Unit tests for utilities and components
- `tests/data/` - Test fixtures (images, JSON annotations)

### Key Test Fixtures

- `data_path` (root conftest) - Provides isolated copy of test data in tmp directory
- `_isolated_qtsettings` (e2e conftest, autouse) - Isolates QSettings to prevent test pollution
- `show_window_and_wait_for_imagedata()` - Helper to show window and wait for image loading

### Writing GUI Tests

```python
@pytest.mark.gui
def test_example(qtbot: QtBot, data_path: Path) -> None:
    win = labelme.app.MainWindow(filename=str(data_path / "annotated" / "apc.json"))
    qtbot.addWidget(win)
    show_window_and_wait_for_imagedata(qtbot, win)
    # ... test logic ...
    win.close()
```

## Code Style

- Uses ruff for formatting and linting
- Uses ty for type checking
- Force single-line imports (isort)
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `perf:`, `ci:`, `i18n:`

## Translations

- Translation files are in `labelme/translate/` (`.ts` source, `.qm` compiled)
- After editing `.ts` files, run `make update_translate` to compile them
- Do not run `pyside6-lrelease` or `lrelease` directly
