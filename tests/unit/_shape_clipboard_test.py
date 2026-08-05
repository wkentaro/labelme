from __future__ import annotations

import numpy as np
import pytest

from labelme._shape import Shape
from labelme._shape_clipboard import ShapeClipboard


def _make_polygon() -> Shape:
    return Shape(
        shape_type="polygon",
        points=np.array([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], dtype=np.float64),
        closed=True,
    )


def test_paste_without_store_returns_empty() -> None:
    assert ShapeClipboard().paste() == []


def test_paste_returns_independent_copies_each_call() -> None:
    # Regression guard: paste() must hand out fresh copies so editing one
    # pasted shape never mutates a later paste of the same buffer.
    clipboard = ShapeClipboard()
    clipboard.store([_make_polygon()])

    first = clipboard.paste()
    second = clipboard.paste()

    assert first[0] is not second[0]
    first[0].move_vertex(i=0, pos=(99.0, 99.0))
    assert second[0].points[0] == pytest.approx((0.0, 0.0))


def test_store_snapshots_shapes_at_store_time() -> None:
    # store() copies its input, so mutating the source afterwards must not
    # leak into the buffer.
    clipboard = ShapeClipboard()
    source = _make_polygon()
    clipboard.store([source])

    source.move_vertex(i=0, pos=(99.0, 99.0))

    assert clipboard.paste()[0].points[0] == pytest.approx((0.0, 0.0))


def test_store_preserves_all_shapes_in_order() -> None:
    first = _make_polygon()
    first.label = "first"
    second = _make_polygon()
    second.label = "second"
    clipboard = ShapeClipboard()

    clipboard.store([first, second])
    pasted = clipboard.paste()

    assert [shape.label for shape in pasted] == ["first", "second"]
    assert pasted[0] is not first
    assert pasted[1] is not second


@pytest.mark.parametrize(
    ("prior_count", "new_count", "expected_emissions"),
    [
        (0, 1, [True]),
        (1, 1, []),
        (1, 2, []),
        (1, 0, [False]),
        (0, 0, []),
    ],
    ids=[
        "empty_to_content",
        "content_to_content",
        "content_to_more_content",
        "content_to_empty",
        "empty_to_empty",
    ],
)
def test_availability_changed_emits_only_on_emptiness_transitions(
    prior_count: int, new_count: int, expected_emissions: list[bool]
) -> None:
    clipboard = ShapeClipboard()
    clipboard.store([_make_polygon() for _ in range(prior_count)])
    emissions: list[bool] = []
    clipboard.availability_changed.connect(emissions.append)

    clipboard.store([_make_polygon() for _ in range(new_count)])

    assert emissions == expected_emissions
