from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

SkillScriptLoader = Callable[[str], ModuleType]


@pytest.fixture(name="repo_root")
def get_repo_root() -> Path:
    return Path(__file__).parents[5]


@pytest.fixture()
def load_skill_script(repo_root: Path) -> SkillScriptLoader:
    def load(script_name: str) -> ModuleType:
        script_path = (
            repo_root / ".agents/skills/test-labelme-gui/scripts" / f"{script_name}.py"
        )
        spec = importlib.util.spec_from_file_location(
            f"test_labelme_gui_{script_name}", script_path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"could not load skill script: {script_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return load
