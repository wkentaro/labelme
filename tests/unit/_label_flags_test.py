from __future__ import annotations

from typing import cast

from labelme._label_flags import compile_label_flags


def test_compile_label_flags_none_is_empty() -> None:
    assert compile_label_flags(label_flags=None) == {}


def test_compile_label_flags_keeps_the_flag_keys_of_a_valid_pattern() -> None:
    compiled = compile_label_flags(label_flags={"^cat$": ["occluded", "truncated"]})
    (pattern,) = compiled
    assert pattern.pattern == "^cat$"
    assert compiled[pattern] == ["occluded", "truncated"]


def test_compile_label_flags_drops_an_uncompilable_pattern() -> None:
    assert compile_label_flags(label_flags={"cat(": ["occluded"]}) == {}


def test_compile_label_flags_drops_a_non_str_pattern() -> None:
    # An unquoted numeric key in ~/.labelmerc reaches us as an int.
    label_flags = cast(dict[str, list[str]], {2024: ["occluded"]})
    assert compile_label_flags(label_flags=label_flags) == {}


def test_compile_label_flags_drops_a_bytes_pattern() -> None:
    # A bytes pattern compiles, so only the str check keeps it out of the
    # result; matching it against a str label would raise at the call site.
    label_flags = cast(dict[str, list[str]], {b"cat": ["occluded"]})
    assert compile_label_flags(label_flags=label_flags) == {}


def test_compile_label_flags_keeps_the_valid_patterns_of_a_mixed_spec() -> None:
    compiled = compile_label_flags(
        label_flags={"cat(": ["broken"], "^cat$": ["occluded"]}
    )
    assert [pattern.pattern for pattern in compiled] == ["^cat$"]
