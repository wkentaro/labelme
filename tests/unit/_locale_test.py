from __future__ import annotations

from labelme import _locale


def test_available_translation_locales_includes_bundled_locale() -> None:
    assert "ja_JP" in _locale.available_translation_locales()


def test_available_translation_locales_excludes_source_locale() -> None:
    assert _locale.SOURCE_LOCALE not in _locale.available_translation_locales()


def test_is_valid_language_accepts_none_source_and_bundled() -> None:
    assert _locale.is_valid_language(None)
    assert _locale.is_valid_language(_locale.SOURCE_LOCALE)
    assert _locale.is_valid_language("ja_JP")


def test_is_valid_language_rejects_unknown_code() -> None:
    assert not _locale.is_valid_language("xx_ZZ")
