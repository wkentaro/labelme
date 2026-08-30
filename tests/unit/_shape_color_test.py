from __future__ import annotations

import pytest

from labelme._shape_color import resolve_shape_color


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            {
                "mode": "auto",
                "auto": {"shift": -1},
                "uniform": {"color": [0, 255, 0]},
                "by_label": {"colors": None, "fallback": [0, 255, 0]},
            },
            (0, 0, 0),
        ),
        (
            {
                "mode": "uniform",
                "auto": {"shift": 0},
                "uniform": {"color": [215, 60, 233]},
                "by_label": {"colors": None, "fallback": [0, 255, 0]},
            },
            (215, 60, 233),
        ),
        (
            {
                "mode": "by_label",
                "auto": {"shift": 0},
                "uniform": {"color": [0, 255, 0]},
                "by_label": {
                    "colors": {"cat": [255, 0, 0]},
                    "fallback": [215, 60, 233],
                },
            },
            (255, 0, 0),
        ),
        (
            {
                "mode": "by_label",
                "auto": {"shift": 0},
                "uniform": {"color": [0, 255, 0]},
                "by_label": {
                    "colors": {"dog": [0, 0, 255]},
                    "fallback": [215, 60, 233],
                },
            },
            (215, 60, 233),
        ),
    ],
    ids=["auto", "uniform", "by-label-match", "by-label-fallback"],
)
def test_resolve_shape_color(*, config: dict, expected: tuple[int, int, int]) -> None:
    assert resolve_shape_color(config=config, label="cat", label_index=0) == expected
