from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from typing import Final

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.comments import CommentedSeq

from .. import _yaml

here = Path(__file__).resolve().parent

_DEFAULT_CONFIG: Final = _yaml.safe_load(
    (here / "default_config.yaml").read_text(encoding="utf-8")
)


def _default_value(key_path: Sequence[str]) -> object:
    node: object = _DEFAULT_CONFIG
    for key in key_path:
        if not isinstance(node, dict) or key not in node:
            raise ValueError(f"Unknown config key: {'.'.join(key_path)}")
        node = node[key]
    return node


def _assign(doc: CommentedMap, key_path: Sequence[str], value: object) -> None:
    node = doc
    for key in key_path[:-1]:
        if key in node and not isinstance(node[key], dict):
            raise ValueError(
                f"Config key {'.'.join(key_path)!r} conflicts with a "
                f"non-mapping value at {key!r}"
            )
        if key not in node:
            node[key] = CommentedMap()
        node = node[key]
    if isinstance(value, list):
        # emit lists inline ([1, 2, 3]) to match default_config.yaml's style
        value = CommentedSeq(value)
        value.fa.set_flow_style()
    node[key_path[-1]] = value


def _prune(doc: CommentedMap, key_path: Sequence[str]) -> None:
    head, *rest = key_path
    if head not in doc:
        return
    if not rest:
        del doc[head]
        return
    if not isinstance(doc[head], dict):
        return
    _prune(doc=doc[head], key_path=rest)
    if len(doc[head]) == 0:
        del doc[head]


def _atomic_write(config_file: Path, content: str) -> None:
    fd, tmp = tempfile.mkstemp(
        dir=config_file.parent, prefix=f"{config_file.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, config_file)
    except BaseException:
        os.unlink(tmp)
        raise


def set_override(config_file: Path, key_path: Sequence[str], value: object) -> None:
    if not key_path:
        raise ValueError("key_path must not be empty")

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    doc = (
        yaml.load(config_file.read_text(encoding="utf-8"))
        if config_file.exists()
        else None
    )
    if not isinstance(doc, CommentedMap):
        doc = CommentedMap()

    if value == _default_value(key_path=key_path):
        _prune(doc=doc, key_path=key_path)
    else:
        _assign(doc=doc, key_path=key_path, value=value)

    content = ""
    if doc:
        buffer = StringIO()
        yaml.dump(doc, buffer)
        content = buffer.getvalue()
    _atomic_write(config_file=config_file, content=content)
