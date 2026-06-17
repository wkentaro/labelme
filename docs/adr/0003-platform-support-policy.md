# The Python support window follows SPEC 0 as the deps ship it (floor 3.11), not the bare calendar (3.12)

labelme drops Python minors on the [SPEC 0](https://scientific-python.org/specs/spec-0000/)
schedule (the successor to [NEP 29](https://numpy.org/neps/nep-0029-deprecation_policy.html)),
anchored to what its core scientific dependencies (numpy, scipy, scikit-image)
actually ship rather than to the bare 3-years-after-release date. For v7.0.0 that
makes the floor **Python 3.11** (`requires-python = ">=3.11"`). The strict SPEC 0
calendar would say 3.12 (3.11 passed its three-year mark around October 2025), but
numpy, scipy, and scikit-image still publish 3.11 wheels, so 3.11 is the real
ecosystem floor and the one labelme follows. v6.3.x is the maintenance line for the
Qt5 and Python 3.10 stragglers left behind by v7.0.0, receiving critical fixes only.

This is an application policy, not a library one: labelme has effectively no
downstream packages, so the value of SPEC 0 here is not coordination but honesty.
The dependency stack decides what can be shipped, and SPEC 0 describes how that
stack moves. When numpy/scipy/scikit-image drop 3.11, labelme raises its floor to
match in the next release that crosses the boundary.

## Considered options

- **Keep `>=3.10`** (rejected): numpy, scipy, and scikit-image have all dropped 3.10
  at HEAD. A 3.10 install silently resolves to stale science (numpy 2.2.6 /
  scipy 1.15.3 / scikit-image 0.25.2) and required a dedicated
  `onnxruntime<1.24; python_version < '3.11'` constraint to stay installable.
  Advertising 3.10 is a promise the dependency stack no longer keeps.
- **Jump to `>=3.12` to honor the strict SPEC 0 calendar** (rejected): this is
  stricter than the scientific ecosystem itself. numpy/scipy/scikit-image still
  ship 3.11 wheels, so dropping to 3.12 would strand users the dependency stack
  still serves, for no functional gain. The calendar is the schedule; the wheels
  are the reality, and the reality is one minor more generous right now.
- **Follow Python's upstream end-of-life (~5 years) instead of SPEC 0** (rejected):
  this over-promises for a package built on the scientific stack. Python 3.11 is in
  upstream EOL into 2027, but the deps will drop it well before then, so an
  EOL-based pledge could not be honored with current dependencies.
- **Adopt SPEC 0 anchored to dependency practice, floor 3.11** (chosen): the only
  policy that is both principled (a named, citable schedule) and true (matches the
  wheels labelme can actually install today).

## Consequences

- v6.3.x becomes a standing maintenance line for the Qt5 and Python 3.10
  stragglers v7.0.0 leaves behind, receiving critical fixes only.
- The floor moves again when the first of numpy/scipy/scikit-image drops 3.11;
  until then labelme stays one minor below the strict SPEC 0 calendar.
- The CI minimum-version matrix entry tracks `requires-python`, so dropping 3.10
  meant raising the lowest tested Python (and the `.python-version` dev pin) to
  3.11 in lockstep.
- The `onnxruntime<1.24; python_version < '3.11'` constraint was removed: with no
  sub-3.11 interpreter left, there is nothing for it to constrain.
