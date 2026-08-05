from __future__ import annotations

import io

import pytest
from ruamel.yaml import YAMLError

from labelme import _yaml


def test_safe_load_parses_string_into_nested_structure() -> None:
    assert _yaml.safe_load("a: 1\nb:\n  - 2\n  - 3\n") == {"a": 1, "b": [2, 3]}


def test_safe_load_accepts_file_like_stream() -> None:
    assert _yaml.safe_load(io.StringIO("x: hello\n")) == {"x": "hello"}


def test_safe_load_returns_none_for_empty_string() -> None:
    assert _yaml.safe_load("") is None


@pytest.mark.parametrize(
    "payload",
    [
        '!!python/object/apply:os.system ["echo hi"]',
        '!!python/object/new:os.system ["echo hi"]',
        "!!python/name:os.system",
        "!!python/module:os",
    ],
)
def test_safe_load_rejects_unsafe_python_tag(payload: str) -> None:
    with pytest.raises(YAMLError):
        _yaml.safe_load(payload)
