from __future__ import annotations

from pathlib import Path
from typing import Final

# en_US is the untranslated source language: it ships no .qm file yet is always
# a valid selection.
SOURCE_LOCALE: Final = "en_US"

TRANSLATE_DIR: Final = Path(__file__).resolve().parent / "translate"


def available_translation_locales() -> list[str]:
    if not TRANSLATE_DIR.is_dir():
        return []
    return sorted(
        path.stem for path in TRANSLATE_DIR.glob("*.qm") if path.stem != SOURCE_LOCALE
    )


def is_valid_language(code: object) -> bool:
    if code is None or code == SOURCE_LOCALE:
        return True
    return code in available_translation_locales()
