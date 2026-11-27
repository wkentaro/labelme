"""Run with python -m tools.benchmark_hover_target."""

from __future__ import annotations

import argparse
import functools
import json
import statistics
import timeit
from typing import Final

import numpy as np

from labelme._shape import Shape
from labelme._widgets._canvas_interaction import find_hover_target

SCALE: Final[float] = 0.05
EPSILON: Final[float] = 10.0
POINT_SIZE: Final[int] = 8
CENTER_SPACING: Final[float] = 20.0
MS_PER_S: Final[int] = 1000
CASES: Final[dict[str, tuple[float, tuple[float, float]]]] = {
    "all-in-reach": (150.0, (20.37, 3.11)),
    "few-in-reach": (10_000.0, (10_020.37, 3.11)),
}


def _circle(*, center_x: float, radius: float, vertices: int) -> Shape:
    theta = np.linspace(0, 2 * np.pi, vertices, endpoint=False)
    return Shape(
        shape_type="polygon",
        points=np.column_stack(
            (center_x + radius * np.cos(theta), radius * np.sin(theta))
        ),
        closed=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, action="append", dest="cases")
    parser.add_argument("--shapes", type=int, default=3)
    parser.add_argument("--vertices", type=int, default=10000)
    parser.add_argument("--number", type=int, default=50)
    parser.add_argument("--repeat", type=int, default=15)
    args = parser.parse_args()
    if min(args.shapes, args.vertices, args.number, args.repeat) < 1:
        parser.error("counts must be positive")
    for case in args.cases or CASES:
        radius, cursor = CASES[case]
        shapes = [
            _circle(center_x=i * CENTER_SPACING, radius=radius, vertices=args.vertices)
            for i in range(args.shapes)
        ]
        point = np.array(cursor, dtype=np.float64)

        hover = functools.partial(
            find_hover_target,
            shapes=shapes,
            point=point,
            scale=SCALE,
            epsilon=EPSILON,
            point_size=POINT_SIZE,
            priority_shape=None,
        )
        target = hover()
        runs = timeit.repeat(hover, number=args.number, repeat=args.repeat)
        per_call_ms = [run / args.number * MS_PER_S for run in runs]
        print(
            json.dumps(
                {
                    "case": case,
                    "shapes": args.shapes,
                    "vertices": args.vertices,
                    "number": args.number,
                    "repeat": args.repeat,
                    "vertices_in_reach": [
                        int(
                            np.count_nonzero(
                                np.linalg.norm(shape.points - point, axis=1)
                                <= EPSILON / SCALE
                            )
                        )
                        for shape in shapes
                    ],
                    "target": None
                    if target is None
                    else {
                        "kind": target.kind.value,
                        "shape": shapes.index(target.shape),
                        "index": target.index,
                    },
                    "median_ms": statistics.median(per_call_ms),
                    "min_ms": min(per_call_ms),
                    "max_ms": max(per_call_ms),
                    "samples_ms": per_call_ms,
                }
            )
        )


if __name__ == "__main__":
    main()
