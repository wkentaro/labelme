from __future__ import annotations

import re

from loguru import logger


def compile_label_flags(
    label_flags: dict[str, list[str]] | None,
) -> dict[re.Pattern[str], list[str]]:
    # The patterns arrive unvalidated from ~/.labelmerc or --label-flags, so
    # neither a typo like `person-(` nor a non-str key (an unquoted `2024`
    # parses as an int) must take the app down. The str check is what keeps a
    # bytes pattern out: it compiles happily, then raises at match time.
    compiled: dict[re.Pattern[str], list[str]] = {}
    for pattern, keys in (label_flags or {}).items():
        if not isinstance(pattern, str):
            logger.warning("Non-str label_flags pattern: {!r}", pattern)
            continue
        try:
            compiled[re.compile(pattern)] = keys
        except re.error as e:
            logger.warning("Invalid label_flags pattern {!r}: {}", pattern, e)
    return compiled
