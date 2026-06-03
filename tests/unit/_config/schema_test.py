from __future__ import annotations

import typing

import pytest

from labelme._config import load_config
from labelme._config.schema import SETTINGS
from labelme._config.schema import Section
from labelme._config.schema import Setting


@pytest.fixture
def default_config() -> dict:
    return load_config(config_file=None, config_overrides={})


def _resolve(config: dict, key_path: tuple[str, ...]) -> object:
    node: object = config
    for key in key_path:
        assert isinstance(node, dict), key_path
        assert key in node, key_path
        node = node[key]
    return node


def _ids() -> list[str]:
    return [".".join(setting.key_path) for setting in SETTINGS]


@pytest.mark.parametrize("setting", SETTINGS, ids=_ids())
def test_key_path_resolves_in_default_config(
    setting: Setting, default_config: dict
) -> None:
    # raises if the key_path does not exist in default_config.yaml
    _resolve(config=default_config, key_path=setting.key_path)


def test_no_duplicate_key_paths() -> None:
    key_paths = [setting.key_path for setting in SETTINGS]
    assert len(set(key_paths)) == len(key_paths)


def test_every_section_is_used() -> None:
    used = {setting.section for setting in SETTINGS}
    assert used == set(typing.get_args(Section))


@pytest.mark.parametrize(
    "setting",
    [s for s in SETTINGS if s.kind == "enum"],
    ids=[".".join(s.key_path) for s in SETTINGS if s.kind == "enum"],
)
def test_enum_default_is_a_choice(setting: Setting, default_config: dict) -> None:
    assert setting.choices is not None
    assert len(setting.choices) >= 1
    default = _resolve(config=default_config, key_path=setting.key_path)
    assert default in setting.choices


def test_bool_defaults_are_bool(default_config: dict) -> None:
    for setting in SETTINGS:
        if setting.kind != "bool":
            continue
        default = _resolve(config=default_config, key_path=setting.key_path)
        assert isinstance(default, bool), setting.key_path
