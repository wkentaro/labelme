from __future__ import annotations

import sys
import warnings

import pytest

from labelme.__main__ import main


@pytest.mark.parametrize("flag", ["--nodata", "--autosave"])
def test_removed_flag_errors_as_unknown(
    flag: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["labelme", flag])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


@pytest.mark.parametrize(
    ("argv", "canonical"),
    [
        (["--nosortlabels"], "--no-sort-labels"),
        (["--nosort"], "--no-sort-labels"),  # argparse abbreviation
        (["--labelflags", "{}"], "--label-flags"),
        (["--validatelabel", "exact"], "--validate-label"),
    ],
)
def test_deprecated_alias_warns_pointing_to_canonical(
    argv: list[str], canonical: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["labelme", *argv, "--version"])
    with pytest.warns(FutureWarning, match=canonical):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0


@pytest.mark.parametrize(
    "argv",
    [
        ["--no-sort-labels"],
        ["--label-flags", "{}"],
        ["--validate-label", "exact"],
        ["--with-image-data"],
        ["--no-auto-save"],
    ],
)
def test_canonical_flag_does_not_warn(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["labelme", *argv, "--version"])
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0
