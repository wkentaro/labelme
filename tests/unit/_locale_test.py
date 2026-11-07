from __future__ import annotations

import ast
import dataclasses
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Final

import pytest

import labelme
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
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }

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
        owner: ast.AST = node
        while owner in parents and not isinstance(owner, ast.ClassDef):
            owner = parents[owner]
        is_settings_context = (
            isinstance(owner, ast.ClassDef)
            and owner.name == "SettingsDialog"
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        )
        if key in allowlist and is_settings_context:
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
class SettingsDialog:
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


def test_tr_calls_repo_wide_use_literals_or_allowlist() -> None:
    labelme_dir = Path(labelme.__file__).resolve().parent
    all_violations: list[UntranslatableTrCall] = []
    matched_allowlist: set[tuple[str, str]] = set()

    for py_path in sorted(labelme_dir.rglob("*.py")):
        rel_path = py_path.relative_to(labelme_dir).as_posix()
        source = py_path.read_text(encoding="utf-8")
        violations, hits = find_untranslatable_tr_calls(
            source=source, file_path=rel_path
        )
        all_violations.extend(violations)
        matched_allowlist.update(hits)

    if all_violations:
        details = "\n".join(str(v) for v in all_violations)
        pytest.fail(
            f"Found {len(all_violations)} untranslatable non-literal "
            f"tr() call(s):\n{details}"
        )

    unused = _ALLOWED_NON_LITERAL_TR_CALLS - matched_allowlist
    assert not unused, f"Unused allowlist entries: {unused}"


def test_qt_translate_noop_calls_use_settings_dialog_context_and_literals() -> None:
    labelme_dir = Path(labelme.__file__).resolve().parent
    noop_count = 0

    for py_path in sorted(labelme_dir.rglob("*.py")):
        tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
        rel_path = py_path.relative_to(labelme_dir).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            is_noop = (
                isinstance(node.func, ast.Name) and node.func.id == "QT_TRANSLATE_NOOP"
            ) or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "QT_TRANSLATE_NOOP"
            )
            if not is_noop:
                continue

            noop_count += 1
            assert len(node.args) >= 2, (
                f"{rel_path}:{node.lineno}: QT_TRANSLATE_NOOP expects (context, text)"
            )
            context_node = node.args[0]
            text_node = node.args[1]
            assert isinstance(context_node, ast.Constant) and isinstance(
                context_node.value, str
            ), f"{rel_path}:{node.lineno}: context must be a string literal"
            assert isinstance(text_node, ast.Constant) and isinstance(
                text_node.value, str
            ), f"{rel_path}:{node.lineno}: source text must be a string literal"
            assert context_node.value == "SettingsDialog", (
                f"{rel_path}:{node.lineno}: expected context 'SettingsDialog', "
                f"got {context_node.value!r}"
            )

    assert noop_count > 0, "Expected to find QT_TRANSLATE_NOOP registrations"


def test_qt_translate_noop_strings_exist_in_all_translation_catalogs() -> None:
    labelme_dir = Path(labelme.__file__).resolve().parent
    registered_texts: set[str] = set()

    for py_path in sorted(labelme_dir.rglob("*.py")):
        tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            is_noop = (
                isinstance(node.func, ast.Name) and node.func.id == "QT_TRANSLATE_NOOP"
            ) or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "QT_TRANSLATE_NOOP"
            )
            if not is_noop or len(node.args) < 2:
                continue
            text_node = node.args[1]
            if isinstance(text_node, ast.Constant) and isinstance(text_node.value, str):
                registered_texts.add(text_node.value)

    assert registered_texts, "No QT_TRANSLATE_NOOP strings found"

    translate_dir = _locale.TRANSLATE_DIR
    ts_paths = sorted(translate_dir.glob("*.ts"))
    assert ts_paths, "No translation .ts files found"

    for ts_path in ts_paths:
        root = ET.parse(ts_path).getroot()
        catalog_sources: set[str] = set()
        for ctx in root.findall("context"):
            name = ctx.find("name")
            if name is None or name.text != "SettingsDialog":
                continue
            for msg in ctx.findall("message"):
                src = msg.find("source")
                if src is not None and src.text:
                    catalog_sources.add(src.text)

        missing = registered_texts - catalog_sources
        assert not missing, (
            f"{ts_path.name} is missing SettingsDialog sources: {sorted(missing)}"
        )


@pytest.mark.parametrize(
    "expression",
    [
        'self.tr("Hello, " "world")',
        'self.tr("Items: %d") % count',
        'self.tr("Items: {count}").format(count=count)',
    ],
)
def test_find_untranslatable_tr_calls_allows_literal_formatting(
    *,
    expression: str,
) -> None:
    violations, _ = find_untranslatable_tr_calls(
        source=expression, file_path="_widgets/_dialog.py"
    )
    assert violations == []


def test_find_untranslatable_tr_calls_rejects_wrong_translation_context() -> None:
    source = """
class OtherDialog:
    def build(self, label):
        return self.tr(label)
"""
    violations, hits = find_untranslatable_tr_calls(
        source=source, file_path="_widgets/_settings_dialog.py"
    )
    assert len(violations) == 1
    assert hits == set()


def _is_named_call(node: ast.AST, /, *, name: str) -> bool:
    return isinstance(node, ast.Call) and (
        isinstance(node.func, ast.Name)
        and node.func.id == name
        or isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    )


def _is_registered_settings_string(node: ast.AST, /) -> bool:
    # cast(str, ...) only changes the static type; lupdate still sees the marker.
    while (
        _is_named_call(node, name="cast")
        and isinstance(node, ast.Call)
        and len(node.args) == 2
    ):
        node = node.args[1]
    return (
        _is_named_call(node, name="QT_TRANSLATE_NOOP")
        and isinstance(node, ast.Call)
        and len(node.args) == 2
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "SettingsDialog"
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    )


def find_unregistered_setting_strings(*, source: str) -> list[str]:
    """Validate the deliberately maintained schema shapes used by dynamic tr()."""
    tree = ast.parse(source)
    errors: list[str] = []
    for node in ast.walk(tree):
        if _is_named_call(node, name="Setting") and isinstance(node, ast.Call):
            fields = {keyword.arg: keyword.value for keyword in node.keywords}
            if node.args or None in fields:
                errors.append(
                    f"line {node.lineno}: Setting must use explicit keyword fields"
                )
            for name in ("label", "note", "choice_labels"):
                value = fields.get(name)
                if value is None:
                    if name == "label":
                        errors.append(f"line {node.lineno}: missing label")
                    continue
                if (
                    name != "label"
                    and isinstance(value, ast.Constant)
                    and value.value is None
                ):
                    continue
                values = (
                    value.elts
                    if name == "choice_labels" and isinstance(value, ast.Tuple)
                    else [value]
                )
                for entry in values:
                    # Model display names are shared verbatim with the AI dock,
                    # intentionally untranslated. This is the sole dynamic
                    # choice source; arbitrary new generators remain rejected.
                    key_path = fields.get("key_path")
                    if (
                        name == "choice_labels"
                        and key_path is not None
                        and ast.unparse(key_path) == "('ai', 'text_model')"
                        and ast.unparse(entry)
                        == (
                            "*(display_name for _, display_name in "
                            "AI_TEXT_MODEL_OPTIONS)"
                        )
                    ):
                        continue
                    if not _is_registered_settings_string(entry):
                        errors.append(
                            f"line {entry.lineno}: {name} must use "
                            "QT_TRANSLATE_NOOP('SettingsDialog', literal)"
                        )
        if not (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "_TRANSLATABLE_GROUPS"
        ):
            continue
        if not isinstance(node.value, ast.Tuple) or not all(
            _is_registered_settings_string(entry) for entry in node.value.elts
        ):
            errors.append(
                f"line {node.lineno}: group headings must use "
                "QT_TRANSLATE_NOOP('SettingsDialog', literal)"
            )
    return errors


def test_settings_schema_strings_are_registered_for_translation() -> None:
    schema_path = Path(labelme.__file__).resolve().parent / "_config" / "_schema.py"
    assert (
        find_unregistered_setting_strings(
            source=schema_path.read_text(encoding="utf-8")
        )
        == []
    )


@pytest.mark.parametrize(
    "field",
    ['label="Unregistered"', 'note="Unregistered"', 'choice_labels=("Unregistered",)'],
)
def test_settings_schema_guard_rejects_bare_fields(*, field: str) -> None:
    required_label = (
        ""
        if field.startswith("label=")
        else 'label=QT_TRANSLATE_NOOP("SettingsDialog", "Registered"),'
    )
    source = f"Setting({required_label}{field})"
    errors = find_unregistered_setting_strings(source=source)
    assert len(errors) == 1
    assert field.split("=")[0] in errors[0]


@pytest.mark.parametrize("context", ['"OtherDialog"', "context_variable"])
def test_settings_schema_guard_rejects_wrong_context(*, context: str) -> None:
    source = f'Setting(label=QT_TRANSLATE_NOOP({context}, "Label"))'
    assert len(find_unregistered_setting_strings(source=source)) == 1


def test_settings_schema_guard_accepts_registered_fields_and_optional_none() -> None:
    source = """
_TRANSLATABLE_GROUPS: Final = (QT_TRANSLATE_NOOP("SettingsDialog", "Group"),)
Setting(label=cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "Label")),
        note=typing.cast(str, QT_TRANSLATE_NOOP("SettingsDialog", "A " "note")),
        choice_labels=(QT_TRANSLATE_NOOP("SettingsDialog", "Choice"),))
Setting(label=QT_TRANSLATE_NOOP("SettingsDialog", "Label"),
        note=None, choice_labels=None)
"""
    assert find_unregistered_setting_strings(source=source) == []


@pytest.mark.parametrize(
    "group", ['"Unregistered"', 'QT_TRANSLATE_NOOP("OtherDialog", "Group")']
)
def test_settings_schema_guard_rejects_unregistered_group_heading(
    *, group: str
) -> None:
    source = f"_TRANSLATABLE_GROUPS: Final = ({group},)"
    assert len(find_unregistered_setting_strings(source=source)) == 1


def test_settings_schema_guard_preserves_untranslated_model_names_only() -> None:
    source = """
Setting(key_path=("ai", "text_model"),
        label=QT_TRANSLATE_NOOP("SettingsDialog", "Model"),
        choice_labels=(*(display_name for _, display_name in AI_TEXT_MODEL_OPTIONS),))
"""
    assert find_unregistered_setting_strings(source=source) == []
    assert (
        len(
            find_unregistered_setting_strings(
                source=source.replace("AI_TEXT_MODEL_OPTIONS", "arbitrary_strings")
            )
        )
        == 1
    )
    assert (
        len(
            find_unregistered_setting_strings(
                source=source.replace('"text_model"', '"default"')
            )
        )
        == 1
    )
