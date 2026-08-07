import json
import subprocess
import sys
from pathlib import Path

import pytest

import a_scanner.engine as engine
from a_scanner.engine import ScanOptions, execute
from a_scanner.git_guard import GitGuardError, inspect_git
from a_scanner.models import CommandResult, Mode, ProjectRecord, Status
from a_scanner.runner import CommandRunner


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_config(repository: Path, argv: list[str]) -> None:
    encoded = ", ".join(json.dumps(value) for value in argv)
    (repository / "a-scanner.toml").write_text(
        "\n".join(
            [
                "schema_version = 1",
                "[[validation.commands]]",
                'name = "Fixture validation"',
                f"argv = [{encoded}]",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _repository(
    tmp_path: Path,
    *,
    project: bool = False,
    validation_argv: list[str] | None = None,
) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "fixture@example.com")
    _git(repository, "config", "user.name", "Fixture")
    (repository / "tracked.txt").write_text("before\n", encoding="utf-8")

    if project:
        (repository / "pyproject.toml").write_text(
            '[project]\nname = "fixture"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        (repository / "uv.lock").write_text("version = 1\n", encoding="utf-8")

    if validation_argv is not None:
        _write_config(repository, validation_argv)

    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial")
    return repository


def _external_reports(repository: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    reports = repository.parent / f"{repository.name}-reports"
    monkeypatch.setattr(engine, "default_report_directory", lambda _: reports)
    return reports


def _success_result(project) -> CommandResult:
    return CommandResult(
        argv=["fake-uv-update"],
        cwd=str(project.path),
        exit_code=0,
        stdout="",
        stderr="",
        duration_seconds=0.0,
    )


def _install_fake_uv_adapter(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    state = {"updates": 0}

    class FakeUvAdapter:
        def __init__(self, runner: CommandRunner) -> None:
            self.runner = runner

        def snapshot(self, project) -> ProjectRecord:
            return ProjectRecord(
                ecosystem="uv",
                path=str(project.path),
                manifest=str(project.manifest),
                lockfile=str(project.lockfile),
            )

        def apply_compatible_update(self, project) -> list[CommandResult]:
            state["updates"] += 1
            project.manifest.write_text(
                project.manifest.read_text(encoding="utf-8") + "# package update\n",
                encoding="utf-8",
            )
            return [_success_result(project)]

    monkeypatch.setattr(engine, "UvAdapter", FakeUvAdapter)
    return state


def _install_update_side_effect_adapter(
    monkeypatch: pytest.MonkeyPatch,
    *,
    unrelated_change: bool = False,
    head_change: bool = False,
    fail_second_snapshot: bool = False,
) -> None:
    class SideEffectUvAdapter:
        def __init__(self, runner: CommandRunner) -> None:
            self.runner = runner
            self.snapshots = 0

        def snapshot(self, project) -> ProjectRecord:
            self.snapshots += 1
            if fail_second_snapshot and self.snapshots == 2:
                raise OSError("post-update inventory failed")
            return ProjectRecord(
                ecosystem="uv",
                path=str(project.path),
                manifest=str(project.manifest),
                lockfile=str(project.lockfile),
            )

        def apply_compatible_update(self, project) -> list[CommandResult]:
            project.manifest.write_text(
                project.manifest.read_text(encoding="utf-8") + "# package update\n",
                encoding="utf-8",
            )
            if unrelated_change:
                (project.path / "tracked.txt").write_text(
                    "unexpected update side effect\n",
                    encoding="utf-8",
                )
            if head_change:
                _git(project.path, "commit", "--allow-empty", "-m", "updater-head-change")
            return [_success_result(project)]

    monkeypatch.setattr(engine, "UvAdapter", SideEffectUvAdapter)


def test_check_rejects_report_directory_equal_to_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    external = _external_reports(repository, monkeypatch)

    report = execute(
        ScanOptions(
            repository=repository,
            mode=Mode.CHECK,
            report_directory=repository,
        )
    )

    assert report.status == Status.PREFLIGHT_FAILED.value
    assert report.report_json_path is not None
    assert Path(report.report_json_path).parent == external
    assert any("report directory" in event.lower() for event in report.events)


def test_check_rejects_report_directory_below_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    external = _external_reports(repository, monkeypatch)

    report = execute(
        ScanOptions(
            repository=repository,
            mode=Mode.CHECK,
            report_directory=repository / "reports",
        )
    )

    assert report.status == Status.PREFLIGHT_FAILED.value
    assert report.report_json_path is not None
    assert Path(report.report_json_path).parent == external


def test_check_accepts_external_report_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    _external_reports(repository, monkeypatch)
    requested = tmp_path / "requested-reports"

    report = execute(
        ScanOptions(
            repository=repository,
            mode=Mode.CHECK,
            report_directory=requested,
        )
    )

    assert report.status == Status.CHECK_COMPLETED.value
    assert report.report_json_path is not None
    assert Path(report.report_json_path).parent == requested


def test_apply_requires_supported_locked_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    _external_reports(repository, monkeypatch)

    report = execute(ScanOptions(repository=repository, mode=Mode.APPLY))

    assert report.status == Status.PREFLIGHT_FAILED.value
    assert any("supported locked" in event.lower() for event in report.events)


def test_baseline_validation_tracked_change_blocks_updates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code = "open('tracked.txt', 'w', encoding='utf-8').write('changed\\n')"
    repository = _repository(
        tmp_path,
        project=True,
        validation_argv=[sys.executable, "-c", code],
    )
    _external_reports(repository, monkeypatch)
    state = _install_fake_uv_adapter(monkeypatch)
    initial_head = inspect_git(repository, CommandRunner()).head

    report = execute(ScanOptions(repository=repository, mode=Mode.APPLY))

    assert report.status == Status.BASELINE_FAILED.value
    assert report.rollback_verified is True
    assert state["updates"] == 0
    final_state = inspect_git(repository, CommandRunner())
    assert final_state.head == initial_head
    assert final_state.clean
    assert (repository / "tracked.txt").read_text(encoding="utf-8") == "before\n"
    assert any("baseline" in event.lower() and "git" in event.lower() for event in report.events)


def test_baseline_validation_head_change_blocks_updates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(
        tmp_path,
        project=True,
        validation_argv=["git", "commit", "--allow-empty", "-m", "validation-head-change"],
    )
    _external_reports(repository, monkeypatch)
    state = _install_fake_uv_adapter(monkeypatch)
    initial_head = inspect_git(repository, CommandRunner()).head

    report = execute(ScanOptions(repository=repository, mode=Mode.APPLY))

    assert report.status == Status.BASELINE_FAILED.value
    assert report.rollback_verified is True
    assert state["updates"] == 0
    final_state = inspect_git(repository, CommandRunner())
    assert final_state.head == initial_head
    assert final_state.clean
    assert any("head" in event.lower() for event in report.events)


def test_package_update_unrelated_change_triggers_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(
        tmp_path,
        project=True,
        validation_argv=[sys.executable, "-c", "pass"],
    )
    _external_reports(repository, monkeypatch)
    _install_update_side_effect_adapter(monkeypatch, unrelated_change=True)
    initial_head = inspect_git(repository, CommandRunner()).head

    report = execute(ScanOptions(repository=repository, mode=Mode.APPLY))

    assert report.status == Status.UPDATE_FAILED_ROLLED_BACK.value
    assert report.rollback_verified is True
    assert inspect_git(repository, CommandRunner()).head == initial_head
    assert inspect_git(repository, CommandRunner()).clean
    events = [event.lower() for event in report.events]
    assert any("unexpected" in event and "update" in event for event in events)


def test_package_update_head_change_triggers_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(
        tmp_path,
        project=True,
        validation_argv=[sys.executable, "-c", "pass"],
    )
    _external_reports(repository, monkeypatch)
    _install_update_side_effect_adapter(monkeypatch, head_change=True)
    initial_head = inspect_git(repository, CommandRunner()).head

    report = execute(ScanOptions(repository=repository, mode=Mode.APPLY))

    assert report.status == Status.UPDATE_FAILED_ROLLED_BACK.value
    assert report.rollback_verified is True
    assert inspect_git(repository, CommandRunner()).head == initial_head
    assert any("head" in event.lower() and "update" in event.lower() for event in report.events)


def test_exception_after_update_started_triggers_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(
        tmp_path,
        project=True,
        validation_argv=[sys.executable, "-c", "pass"],
    )
    _external_reports(repository, monkeypatch)
    _install_update_side_effect_adapter(monkeypatch, fail_second_snapshot=True)
    initial_head = inspect_git(repository, CommandRunner()).head

    report = execute(ScanOptions(repository=repository, mode=Mode.APPLY))

    assert report.status == Status.UPDATE_FAILED_ROLLED_BACK.value
    assert report.rollback_verified is True
    assert inspect_git(repository, CommandRunner()).head == initial_head
    assert inspect_git(repository, CommandRunner()).clean
    assert any("post-update inventory failed" in event for event in report.events)


def _second_validation_mutates_target_command(marker: Path, target: str) -> list[str]:
    code = (
        "import sys; from pathlib import Path; "
        "marker=Path(sys.argv[1]); target=Path(sys.argv[2]); "
        "target.write_text('validation change\\n', encoding='utf-8') "
        "if marker.exists() else marker.write_text('seen\\n', encoding='utf-8')"
    )
    return [sys.executable, "-c", code, str(marker), target]


def _second_validation_changes_head_command(marker: Path) -> list[str]:
    code = (
        "import subprocess, sys; from pathlib import Path; "
        "marker=Path(sys.argv[1]); "
        "subprocess.run(['git','commit','--allow-empty','-m','post-validation-head'], check=True) "
        "if marker.exists() else marker.write_text('seen\\n', encoding='utf-8')"
    )
    return [sys.executable, "-c", code, str(marker)]


@pytest.mark.parametrize("target", ["tracked.txt", "pyproject.toml"])
def test_post_validation_content_change_triggers_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    marker = tmp_path / "validation-marker"
    repository = _repository(
        tmp_path,
        project=True,
        validation_argv=_second_validation_mutates_target_command(marker, target),
    )
    _external_reports(repository, monkeypatch)
    _install_fake_uv_adapter(monkeypatch)
    initial_head = inspect_git(repository, CommandRunner()).head

    report = execute(ScanOptions(repository=repository, mode=Mode.APPLY))

    assert report.status == Status.VALIDATION_FAILED_ROLLED_BACK.value
    assert report.rollback_verified is True
    final_state = inspect_git(repository, CommandRunner())
    assert final_state.head == initial_head
    assert final_state.clean


def test_post_validation_head_change_triggers_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "validation-marker"
    repository = _repository(
        tmp_path,
        project=True,
        validation_argv=_second_validation_changes_head_command(marker),
    )
    _external_reports(repository, monkeypatch)
    _install_fake_uv_adapter(monkeypatch)
    initial_head = inspect_git(repository, CommandRunner()).head

    report = execute(ScanOptions(repository=repository, mode=Mode.APPLY))

    assert report.status == Status.VALIDATION_FAILED_ROLLED_BACK.value
    assert report.rollback_verified is True
    assert inspect_git(repository, CommandRunner()).head == initial_head


def test_post_validation_git_inspection_failure_is_controlled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(
        tmp_path,
        project=True,
        validation_argv=[sys.executable, "-c", "pass"],
    )
    _external_reports(repository, monkeypatch)
    _install_fake_uv_adapter(monkeypatch)
    calls = 0

    def flaky_fingerprint(root: Path, runner: CommandRunner) -> str:
        nonlocal calls
        del root, runner
        calls += 1
        if calls == 4:
            raise GitGuardError("post-validation fingerprint failed")
        return "baseline" if calls <= 2 else "post-update"

    monkeypatch.setattr(engine, "fingerprint_worktree", flaky_fingerprint, raising=False)

    report = execute(ScanOptions(repository=repository, mode=Mode.APPLY))

    assert report.status == Status.VALIDATION_FAILED_ROLLED_BACK.value
    assert report.rollback_verified is True
    assert any("fingerprint" in event.lower() for event in report.events)
