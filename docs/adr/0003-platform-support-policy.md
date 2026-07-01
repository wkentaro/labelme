# The Python support window follows SPEC 0, floor Python 3.12

labelme drops Python minors on the [SPEC 0](https://scientific-python.org/specs/spec-0000/)
schedule (the successor to [NEP 29](https://numpy.org/neps/nep-0029-deprecation_policy.html)),
anchored to what its core scientific dependencies (numpy, scipy, scikit-image)
actually ship. For v7.0.0 that makes the floor **Python 3.12**
(`requires-python = ">=3.12"`). The strict SPEC 0 calendar reaches 3.12 once 3.11
passes its three-year mark (around October 2025), and the dependency stack has now
caught up: numpy (2.5) and scipy (1.18) both require `>=3.12` at HEAD, so 3.12 is
the real ecosystem floor as well. v6.3.x is the maintenance line for the Qt5 and
Python 3.10 / 3.11 stragglers left behind by v7.0.0, receiving critical fixes only.

This is an application policy, not a library one: labelme has effectively no
downstream packages, so the value of SPEC 0 here is not coordination but honesty.
The dependency stack decides what can be shipped, and SPEC 0 describes how that
stack moves. When numpy/scipy/scikit-image drop 3.12, labelme raises its floor to
match in the next release that crosses the boundary.

## Considered options

- **Keep `>=3.11`** (rejected): numpy and scipy have both dropped 3.11 at HEAD
  (numpy 2.5 / scipy 1.18 require `>=3.12`). A 3.11 install silently resolves to
  stale science (the last numpy 2.4.x / scipy 1.17.x releases), the same trap that
  retired 3.10 in the previous revision of this policy. Advertising 3.11 is a
  promise the dependency stack no longer keeps.
- **Hold at `>=3.11` until scikit-image also drops it** (rejected): the earlier
  floor policy moved "when the first of numpy/scipy/scikit-image drops 3.11", and
  that trigger has now fired twice (numpy and scipy). Waiting for the slowest
  dependency would keep advertising a version two of three core deps no longer
  build against, and would hold an extra minor in the CI matrix (each supported
  Python is a full os x version cell across Windows, macOS, and Linux) for users
  the stack can no longer serve.
- **Follow Python's upstream end-of-life (~5 years) instead of SPEC 0** (rejected):
  this over-promises for a package built on the scientific stack. Python 3.11 is in
  upstream EOL into 2027, but the deps have already dropped it, so an EOL-based
  pledge could not be honored with current dependencies.
- **Adopt SPEC 0 anchored to dependency practice, floor 3.12** (chosen): the
  calendar (3.11 past its three-year mark) and the wheels (numpy/scipy at `>=3.12`)
  now agree, so 3.12 is both the principled schedule and the version labelme can
  actually install today. It also keeps the test matrix to the three minors the
  ecosystem still builds against, rather than paying CI for a fourth it does not.

## Consequences

- v6.3.x becomes a standing maintenance line for the Qt5 and Python 3.10 / 3.11
  stragglers v7.0.0 leaves behind, receiving critical fixes only.
- The floor moves again when the first of numpy/scipy/scikit-image drops 3.12;
  until then labelme's floor tracks the strict SPEC 0 calendar.
- The CI minimum-version matrix entry tracks `requires-python`, so raising the
  floor to 3.12 raises the lowest tested Python (and the `.python-version` dev pin)
  in lockstep and drops the 3.11 row from the test matrix.
