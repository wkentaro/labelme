from __future__ import annotations

from typing import IO
from typing import Any

from ruamel.yaml import YAML


def safe_load(stream: str | IO[str]) -> Any:  # noqa: ANN401
    # A fresh instance per call, not a shared one: ruamel's load() appends to
    # YAML().doc_infos and never clears it, so a long-lived instance leaks.
    return YAML(typ="safe").load(stream)
