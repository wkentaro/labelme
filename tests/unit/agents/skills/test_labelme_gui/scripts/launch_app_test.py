from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Protocol
from typing import cast

import pytest
from loguru import logger

from labelme import __main__ as labelme_main
from labelme import _app as labelme_app
from labelme._label_file import read_label_file

from ..conftest import SkillScriptLoader


class PrepareSourceRun(Protocol):
    def __call__(
        self, *, prepare_module: ModuleType, run_dir: Path
    ) -> dict[str, object]: ...


@pytest.fixture
def prepare_source_run(repo_root: Path) -> PrepareSourceRun:
    def prepare(*, prepare_module: ModuleType, run_dir: Path) -> dict[str, object]:
        return prepare_module.prepare_run(
            repo_root=repo_root,
            requested_run_dir=run_dir,
            profile="smoke",
            theme="system",
        )

    return prepare


def test_launch_none_uses_no_input_path_and_records_exact_process(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run with spaces"
    manifest = prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    original_argv = sys.argv[:]
    original_qsettings = labelme_app.QtCore.QSettings

    def run_fake_app() -> None:
        assert sys.argv == [
            "labelme",
            "--config",
            manifest["config_path"],
            "--output",
            str(run_dir / "outputs/none"),
            "--logger-level",
            "warning",
        ]
        settings = labelme_app.QtCore.QSettings("labelme", "labelme")
        assert Path(settings.fileName()) == Path(
            cast(str, manifest["window_state_path"])
        )
        settings.setValue("qa-marker", "isolated")

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    launch_module.launch_labelme(
        run_dir=run_dir,
        mode="none",
        logger_level="warning",
    )

    assert sys.argv == original_argv
    assert labelme_app.QtCore.QSettings is original_qsettings
    assert Path(cast(str, manifest["window_state_path"])).is_file()
    persisted_manifest = json.loads((run_dir / "manifest.json").read_text())
    launches = cast(list[dict[str, object]], persisted_manifest["launches"])
    assert len(launches) == 1
    launch = launches[0]
    assert launch["mode"] == "none"
    assert launch["input_path"] is None
    assert launch["output_path"] == str(run_dir / "outputs/none")
    assert launch["window_state_path"] == manifest["window_state_path"]
    assert launch["pid"]
    assert launch["python_executable"] == sys.executable
    assert launch["expected_shape_count"] is None
    assert launch["application_log_path"] == manifest["application_log_path"]
    report = (run_dir / "report.md").read_text()
    assert (
        f'| <code>"none"</code> | none '
        f"| <code>{json.dumps(obj=str(run_dir / 'outputs/none'))}</code>" in report
    )
    assert (
        f"| <code>{json.dumps(obj=manifest['config_path'])}</code> "
        f"| <code>{json.dumps(obj=manifest['window_state_path'])}</code> "
        f"| <code>{json.dumps(obj=manifest['application_log_path'])}</code> "
        f'| <code>"PID '
    ) in report
    assert f"| <code>{json.dumps(obj=launch['app_argv'])}</code> |" in report


def test_launch_annotated_opens_seeded_annotation_with_expected_shapes(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    manifest = prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    datasets = cast(dict[str, str], manifest["datasets"])
    annotation_path = Path(datasets["annotated"])

    assert annotation_path == run_dir / "outputs/annotated/primitives.json"
    annotation = read_label_file(filename=str(annotation_path))
    assert len(annotation.shapes) == 8
    assert cast(dict[str, int], manifest["expected_shape_counts"])["annotated"] == 8
    assert (annotation_path.parent / annotation.image_path).resolve().is_file()

    def run_fake_app() -> None:
        assert sys.argv[1] == str(annotation_path)
        assert sys.argv[sys.argv.index("--output") + 1] == str(
            run_dir / "outputs/annotated"
        )

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    launch_module.launch_labelme(
        run_dir=run_dir,
        mode="annotated",
        logger_level="warning",
    )


@pytest.mark.parametrize(
    ("mode", "path_kind"),
    [
        ("raw", "directory"),
        ("sequence", "directory"),
        ("corrupt", "file"),
        ("missing-image", "file"),
    ],
)
def test_existing_modes_keep_inputs_and_outputs_inside_the_run(
    mode: str,
    path_kind: str,
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)

    def run_fake_app() -> None:
        input_path = Path(sys.argv[1])
        output_path = Path(sys.argv[sys.argv.index("--output") + 1])
        assert input_path.resolve().is_relative_to(run_dir)
        assert output_path.resolve().is_relative_to(run_dir / "outputs")
        assert input_path.is_dir() if path_kind == "directory" else input_path.is_file()

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    launch_module.launch_labelme(
        run_dir=run_dir,
        mode=mode,
        logger_level="warning",
    )


def test_invalid_mode_path_fails_before_labelme_starts(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["datasets"]["annotated"] = manifest["datasets"]["raw"]
    manifest_path.write_text(json.dumps(manifest))
    did_start = False

    def run_fake_app() -> None:
        nonlocal did_start
        did_start = True

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    with pytest.raises(
        ValueError,
        match="annotated mode requires prepared input",
    ):
        launch_module.launch_labelme(
            run_dir=run_dir,
            mode="annotated",
            logger_level="warning",
        )

    assert did_start is False


def test_report_ledger_is_derived_from_canonical_manifest(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    report_path = run_dir / "report.md"
    launch_separator = "| -- | -- | -- | -- | -- | -- | -- | -- |"
    report_path.write_text(
        report_path.read_text().replace(launch_separator, "| missing |", 1)
    )
    did_start = False

    def run_fake_app() -> None:
        nonlocal did_start
        did_start = True

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    launch_module.launch_labelme(
        run_dir=run_dir,
        mode="none",
        logger_level="warning",
    )

    persisted_manifest = json.loads((run_dir / "manifest.json").read_text())
    assert len(persisted_manifest["launches"]) == 1
    report = report_path.read_text()
    assert launch_separator in report
    assert "| missing |" not in report
    assert did_start is True


def test_report_write_failure_keeps_canonical_launch_and_starts(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    original_write_text = Path.write_text
    did_start = False

    def fail_report_write(
        path: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if "report.md" in path.name:
            raise OSError("report is not writable")
        return original_write_text(
            path, data, encoding=encoding, errors=errors, newline=newline
        )

    def run_fake_app() -> None:
        nonlocal did_start
        did_start = True

    monkeypatch.setattr(Path, "write_text", fail_report_write)
    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    launch_module.launch_labelme(
        run_dir=run_dir,
        mode="none",
        logger_level="warning",
    )

    persisted_manifest = json.loads((run_dir / "manifest.json").read_text())
    assert len(persisted_manifest["launches"]) == 1
    assert "PID" not in (run_dir / "report.md").read_text()
    assert did_start is True


def test_partial_manifest_write_keeps_both_launch_records_unchanged(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    original_write_text = Path.write_text
    did_start = False

    def fail_after_partial_manifest_write(
        path: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if "manifest.json" in path.name:
            original_write_text(
                path,
                data[:20],
                encoding=encoding,
                errors=errors,
                newline=newline,
            )
            raise OSError("manifest write stopped")
        return original_write_text(
            path, data, encoding=encoding, errors=errors, newline=newline
        )

    def run_fake_app() -> None:
        nonlocal did_start
        did_start = True

    monkeypatch.setattr(Path, "write_text", fail_after_partial_manifest_write)
    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    with pytest.raises(OSError, match="manifest write stopped"):
        launch_module.launch_labelme(
            run_dir=run_dir,
            mode="none",
            logger_level="warning",
        )

    persisted_manifest = json.loads((run_dir / "manifest.json").read_text())
    assert persisted_manifest["launches"] == []
    assert "PID" not in (run_dir / "report.md").read_text()
    assert did_start is False


@pytest.mark.skipif(
    sys.platform == "win32", reason="pipe is not valid in Windows paths"
)
def test_report_escapes_markdown_delimiters_in_launch_paths(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run|with`delimiters\nand newline"
    prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)

    def run_fake_app() -> None:
        pass

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    launch_module.launch_labelme(
        run_dir=run_dir,
        mode="none",
        logger_level="warning",
    )

    report = (run_dir / "report.md").read_text()
    launch_row = next(line for line in report.splitlines() if "PID" in line)
    assert launch_row.count("|") == 9
    assert "&#124;" in launch_row
    assert "&#96;" in launch_row
    assert "\\n" in launch_row


def test_output_symlink_escape_fails_before_labelme_starts(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    external_output = tmp_path / "external-output"
    external_output.mkdir()
    try:
        (run_dir / "outputs/none").symlink_to(external_output, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")
    did_start = False

    def run_fake_app() -> None:
        nonlocal did_start
        did_start = True

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    with pytest.raises(ValueError, match="output path must stay inside the run"):
        launch_module.launch_labelme(
            run_dir=run_dir,
            mode="none",
            logger_level="warning",
        )

    persisted_manifest = json.loads((run_dir / "manifest.json").read_text())
    assert persisted_manifest["launches"] == []
    assert did_start is False


def test_unknown_mode_fails_before_labelme_starts(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    did_start = False

    def run_fake_app() -> None:
        nonlocal did_start
        did_start = True

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    with pytest.raises(
        ValueError, match="unknown launch mode 'invalid'; choose one of"
    ):
        launch_module.launch_labelme(
            run_dir=run_dir,
            mode="invalid",
            logger_level="warning",
        )

    assert did_start is False


@pytest.mark.parametrize(
    ("mode", "replacement"),
    [
        ("raw", "inputs/sequence"),
        ("annotated", "inputs/corrupt/primitives.json"),
        ("corrupt", "inputs/raw/primitives.jpg"),
        ("missing-image", "inputs/raw/primitives.jpg"),
    ],
)
def test_mismatched_mode_path_fails_before_labelme_starts(
    mode: str,
    replacement: str,
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["datasets"][mode] = str(run_dir / replacement)
    manifest_path.write_text(json.dumps(manifest))
    did_start = False

    def run_fake_app() -> None:
        nonlocal did_start
        did_start = True

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    with pytest.raises(ValueError, match=f"{mode} mode requires prepared input"):
        launch_module.launch_labelme(
            run_dir=run_dir,
            mode=mode,
            logger_level="warning",
        )

    assert did_start is False


def test_launch_routes_application_log_inside_run(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    manifest = prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    original_log_setup = labelme_main._setup_loguru

    def run_fake_app() -> None:
        labelme_main._setup_loguru(logger_level="WARNING")
        logger.warning("isolated application log")

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    launch_module.launch_labelme(
        run_dir=run_dir,
        mode="none",
        logger_level="warning",
    )
    logger.remove()
    logger.add(sys.stderr)

    assert labelme_main._setup_loguru is original_log_setup
    application_log_path = Path(cast(str, manifest["application_log_path"]))
    assert application_log_path.is_relative_to(run_dir / "evidence/logs")
    assert "isolated application log" in application_log_path.read_text()


def test_annotated_mode_rejects_unexpected_shape_count_before_start(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    manifest = prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    datasets = cast(dict[str, str], manifest["datasets"])
    annotation_path = Path(datasets["annotated"])
    annotation = json.loads(annotation_path.read_text())
    annotation["shapes"].pop()
    annotation_path.write_text(json.dumps(annotation))
    did_start = False

    def run_fake_app() -> None:
        nonlocal did_start
        did_start = True

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    with pytest.raises(ValueError, match="annotated mode expected 8 Shapes"):
        launch_module.launch_labelme(
            run_dir=run_dir,
            mode="annotated",
            logger_level="warning",
        )

    assert did_start is False


@pytest.mark.parametrize("mode", ["annotated", "missing-image"])
def test_annotation_mode_rejects_non_object_json_before_start(
    mode: str,
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    manifest = prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    datasets = cast(dict[str, str], manifest["datasets"])
    Path(datasets[mode]).write_text("[]")
    did_start = False

    def run_fake_app() -> None:
        nonlocal did_start
        did_start = True

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    with pytest.raises(ValueError, match=f"{mode} mode requires a JSON object"):
        launch_module.launch_labelme(
            run_dir=run_dir,
            mode=mode,
            logger_level="warning",
        )

    assert did_start is False


def test_missing_image_mode_rejects_external_missing_path_before_start(
    load_skill_script: SkillScriptLoader,
    prepare_source_run: PrepareSourceRun,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_module = load_skill_script("prepare_run")
    launch_module = load_skill_script("launch_app")
    run_dir = tmp_path / "run"
    manifest = prepare_source_run(prepare_module=prepare_module, run_dir=run_dir)
    datasets = cast(dict[str, str], manifest["datasets"])
    annotation_path = Path(datasets["missing-image"])
    annotation = json.loads(annotation_path.read_text())
    annotation["imagePath"] = str(tmp_path / "external/missing.jpg")
    annotation_path.write_text(json.dumps(annotation))
    did_start = False

    def run_fake_app() -> None:
        nonlocal did_start
        did_start = True

    monkeypatch.setattr(labelme_main, "main", run_fake_app)

    with pytest.raises(
        ValueError, match="missing-image mode image path must stay inside the run"
    ):
        launch_module.launch_labelme(
            run_dir=run_dir,
            mode="missing-image",
            logger_level="warning",
        )

    assert did_start is False
