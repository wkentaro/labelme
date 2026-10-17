from __future__ import annotations

import ast
import dataclasses
from typing import Final

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


@dataclasses.dataclass(frozen=True)
class UntranslatableTrCall:
    file_path: str
    line_number: int
    expression: str
    argument_expr: str

    def __str__(self) -> str:
        return (
            f"{self.file_path}:{self.line_number}: "
            f"non-literal tr() call `{self.expression}` "
            f"(argument: `{self.argument_expr}`). "
            "pyside6-lupdate only extracts string literals; "
            "non-literal calls remain untranslated at runtime. "
            "Pass a string literal or register with QT_TRANSLATE_NOOP."
        )


# Non-literal tr() calls are only allowed when the underlying strings are
# registered for extraction via QT_TRANSLATE_NOOP("SettingsDialog", ...)
# in labelme/_config/_schema.py and labelme/_widgets/_settings_dialog.py.
_ALLOWED_NON_LITERAL_TR_CALLS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("_widgets/_settings_dialog.py", "group"),
        ("_widgets/_settings_dialog.py", "setting.label"),
        ("_widgets/_settings_dialog.py", "setting.note"),
        ("_widgets/_settings_dialog.py", "label"),
    }
)


def _is_tr_call(node: ast.Call, /) -> bool:
    if isinstance(node.func, ast.Attribute) and node.func.attr == "tr":
        return True
    return isinstance(node.func, ast.Name) and node.func.id == "tr"


def find_untranslatable_tr_calls(
    *,
    source: str,
    file_path: str,
    allowlist: frozenset[tuple[str, str]] = _ALLOWED_NON_LITERAL_TR_CALLS,
) -> tuple[list[UntranslatableTrCall], set[tuple[str, str]]]:
    tree = ast.parse(source, filename=file_path)
    violations: list[UntranslatableTrCall] = []
    allowlisted_hits: set[tuple[str, str]] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_tr_call(node):
            continue

        if node.args:
            arg = node.args[0]
            is_literal = isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            arg_expr = ast.unparse(arg)
        else:
            arg_expr = "<no arguments>"
            is_literal = False

        if is_literal:
            continue

        key = (file_path, arg_expr)
        if key in allowlist:
            allowlisted_hits.add(key)
        else:
            violations.append(
                UntranslatableTrCall(
                    file_path=file_path,
                    line_number=node.lineno,
                    expression=ast.unparse(node),
                    argument_expr=arg_expr,
                )
            )

    return violations, allowlisted_hits


def test_find_untranslatable_tr_calls_detects_variables() -> None:
    source = """
def update_label(self, slider_label):
    self.label.setText(self.tr(slider_label))
"""
    violations, _ = find_untranslatable_tr_calls(
        source=source, file_path="_widgets/_dialog.py"
    )
    assert len(violations) == 1
    assert violations[0].argument_expr == "slider_label"
    assert violations[0].line_number == 3


def test_find_untranslatable_tr_calls_detects_fstrings() -> None:
    source = """
def greet(self, name):
    return self.tr(f"Hello, {name}!")
"""
    violations, _ = find_untranslatable_tr_calls(
        source=source, file_path="_widgets/_dialog.py"
    )
    assert len(violations) == 1
    assert violations[0].line_number == 3


def test_find_untranslatable_tr_calls_detects_binary_ops() -> None:
    source = """
def format_text(self, count):
    return self.tr("Items: %d" % count)
"""
    violations, _ = find_untranslatable_tr_calls(
        source=source, file_path="_widgets/_dialog.py"
    )
    assert len(violations) == 1
    assert violations[0].line_number == 3


def test_find_untranslatable_tr_calls_detects_non_string_constants() -> None:
    source = """
def format_num(self):
    return self.tr(123)
"""
    violations, _ = find_untranslatable_tr_calls(
        source=source, file_path="_widgets/_dialog.py"
    )
    assert len(violations) == 1
    assert violations[0].argument_expr == "123"
    assert violations[0].line_number == 3


def test_find_untranslatable_tr_calls_detects_zero_arguments() -> None:
    source = """
def empty_tr(self):
    return self.tr()
"""
    violations, _ = find_untranslatable_tr_calls(
        source=source, file_path="_widgets/_dialog.py"
    )
    assert len(violations) == 1
    assert violations[0].argument_expr == "<no arguments>"
    assert violations[0].line_number == 3


def test_find_untranslatable_tr_calls_allows_string_literals() -> None:
    source = """
def setup_ui(self):
    self.setWindowTitle(self.tr("Settings"))
    self.setToolTip(self.tr("Close window", "disambiguation"))
    bare = tr("Save")
"""
    violations, _ = find_untranslatable_tr_calls(
        source=source, file_path="_widgets/_dialog.py"
    )
    assert violations == []


def test_find_untranslatable_tr_calls_allows_settings_dialog_allowlist() -> None:
    source = """
def build(self, group, setting, label):
    a = self.tr(group)
    b = self.tr(setting.label)
    c = self.tr(setting.note)
    d = self.tr(label)
"""
    violations, hits = find_untranslatable_tr_calls(
        source=source, file_path="_widgets/_settings_dialog.py"
    )
    assert violations == []
    assert hits == {
        ("_widgets/_settings_dialog.py", "group"),
        ("_widgets/_settings_dialog.py", "setting.label"),
        ("_widgets/_settings_dialog.py", "setting.note"),
        ("_widgets/_settings_dialog.py", "label"),
    }


def test_find_untranslatable_tr_calls_rejects_allowlisted_arg_in_other_files() -> None:
    source = """
def build(self, group):
    return self.tr(group)
"""
    violations, _ = find_untranslatable_tr_calls(
        source=source, file_path="_widgets/_canvas.py"
    )
    assert len(violations) == 1
    assert violations[0].argument_expr == "group"


