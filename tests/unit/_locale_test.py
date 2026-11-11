from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Final

import labelme
from labelme import _locale


def test_available_translation_locales_includes_bundled_locale() -> None:
    assert "ja_JP" in _locale.available_translation_locales()


def test_available_translation_locales_excludes_source_locale() -> None:
    assert _locale.SOURCE_LOCALE not in _locale.available_translation_locales()


def test_is_valid_language_accepts_none_source_and_bundled() -> None:
    assert _locale.is_valid_language(code=None)
    assert _locale.is_valid_language(code=_locale.SOURCE_LOCALE)
    assert _locale.is_valid_language(code="ja_JP")


def test_is_valid_language_rejects_unknown_code() -> None:
    assert not _locale.is_valid_language(code="xx_ZZ")


def test_tr_arguments_are_string_literals() -> None:
    # pyside6-lupdate extracts only string literals, so a variable passed to
    # tr() is never offered to translators and stays in the source language.
    # A variable is fine when QT_TRANSLATE_NOOP registers every string it can
    # hold; add that call site's count here after checking that it does.
    REGISTERED_ELSEWHERE: Final = {
        ("_widgets/_ai_tool_group.py", "self.tr(tier)"): 1,
        ("_widgets/_ai_tool_group.py", "self.tr(tip)"): 1,
        ("_widgets/_settings_dialog.py", "self.tr(group)"): 2,
        ("_widgets/_settings_dialog.py", "self.tr(label)"): 1,
        ("_widgets/_settings_dialog.py", "self.tr(setting.label)"): 2,
        ("_widgets/_settings_dialog.py", "self.tr(setting.note)"): 2,
    }
    package = Path(labelme.__file__).parent
    found: Counter[tuple[str, str]] = Counter()
    for path in package.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "tr"
                and not all(
                    isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                    for arg in node.args[:1]
                )
            ):
                found[(path.relative_to(package).as_posix(), ast.unparse(node))] += 1
    assert found == REGISTERED_ELSEWHERE
