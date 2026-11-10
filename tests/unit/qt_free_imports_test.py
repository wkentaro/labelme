from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize("module", ["labelme._shape", "labelme._label_file"])
def test_module_imports_without_qt(*, module: str) -> None:
    # A fresh interpreter: this process has usually imported PySide6 already.
    code = f"import sys, {module}; sys.exit('PySide6' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], check=False)
    assert result.returncode == 0
