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

from labelme.config._yaml import safe_load

USER_CONFIG_HEADER: Final[str] = (
    "# Labelme config file.\n"
    "# Only add settings you want to override.\n"
    "# For all available options and defaults, see:\n"
    "#   https://github.com/wkentaro/labelme/blob/main/labelme/config/default_config.yaml\n"
    "#\n"
    "# Example:\n"
    "# with_image_data: true\n"
    "# auto_save: false\n"
    "# labels: [cat, dog]\n"
)


def _round_trip_yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def _default_config() -> dict:
    HERE: Final = Path(__file__).resolve().parent
    return safe_load((HERE / "default_config.yaml").read_text())


def _default_value(key_path: Sequence[str]) -> object:
    node: object = _default_config()
    for key in key_path:
        if not isinstance(node, dict) or key not in node:
            raise ValueError(f"Unknown config key: {'.'.join(key_path)}")
        node = node[key]
    return node


def _as_flow(value: object) -> object:
    if isinstance(value, list):
        seq = CommentedSeq(value)
        seq.fa.set_flow_style()
        return seq
    return value


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
    node[key_path[-1]] = _as_flow(value)


def _prune(doc: CommentedMap, key_path: Sequence[str]) -> None:
    ancestors = [doc]
    node = doc
    for key in key_path[:-1]:
        if key not in node or not isinstance(node[key], dict):
            return
        node = node[key]
        ancestors.append(node)

    if key_path[-1] in node:
        del node[key_path[-1]]

    for depth in range(len(key_path) - 2, -1, -1):
        parent = ancestors[depth]
        key = key_path[depth]
        if key in parent and isinstance(parent[key], dict) and len(parent[key]) == 0:
            del parent[key]


def _load(config_file: Path, yaml: YAML) -> tuple[CommentedMap, str | None]:
    if not config_file.exists():
        return CommentedMap(), USER_CONFIG_HEADER

    text = config_file.read_text()
    doc = yaml.load(text)
    if isinstance(doc, CommentedMap):
        return doc, None
    if doc is None:
        header = text if text.strip() else USER_CONFIG_HEADER
        if not header.endswith("\n"):
            header += "\n"
        return CommentedMap(), header
    # load_config ignores non-mapping files, so reseed rather than corrupt.
    return CommentedMap(), USER_CONFIG_HEADER


def _atomic_write(config_file: Path, content: str) -> None:
    fd, tmp = tempfile.mkstemp(
        dir=config_file.parent, prefix=f"{config_file.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, config_file)
    except BaseException:
        os.unlink(tmp)
        raise


def _dump(config_file: Path, doc: CommentedMap, header: str | None, yaml: YAML) -> None:
    buffer = StringIO()
    yaml.dump(doc, buffer)
    body = buffer.getvalue()

    if len(doc) == 0:
        # ruamel emits "{}" for an empty mapping; drop it but keep any comment
        # ruamel preserved, e.g. a note the user wrote above keys they reset.
        body = body.rstrip()
        if body.endswith("{}"):
            body = body[:-2].rstrip()
        body = f"{body}\n" if body else ""

    if not body:
        content = header if header is not None else USER_CONFIG_HEADER
    elif header is not None:
        content = f"{header}{body}"
    else:
        content = body

    _atomic_write(config_file=config_file, content=content)


def set_override(config_file: Path, key_path: Sequence[str], value: object) -> None:
    if not key_path:
        raise ValueError("key_path must not be empty")

    default_value = _default_value(key_path=key_path)
    yaml = _round_trip_yaml()
    doc, header = _load(config_file=config_file, yaml=yaml)

    if value == default_value:
        _prune(doc=doc, key_path=key_path)
    else:
        _assign(doc=doc, key_path=key_path, value=value)

    _dump(config_file=config_file, doc=doc, header=header, yaml=yaml)
