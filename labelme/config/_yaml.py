from __future__ import annotations

from io import StringIO
from typing import IO
from typing import Any

from ruamel.yaml import YAML


def safe_load(stream: str | IO[str]) -> Any:  # noqa: ANN401
    return YAML(typ="safe").load(stream)


def safe_dump(data: object) -> str:
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    buffer = StringIO()
    yaml.dump(data, buffer)
    return buffer.getvalue()
