from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import a_scanner.engine as engine
import a_scanner.git_guard as git_guard
import a_scanner.report as report_module
import a_scanner.runner as runner_module
from a_scanner.adapters.npm_adapter import NpmAdapter, has_failed_npm_inventory
from a_scanner.adapters.uv_adapter import UvAdapter
from a_scanner.config import ConfigError, discover_validation_commands, load_config
from a_scanner.detector import discover_projects
from a_scanner.git_guard import GitGuardError, changed_files, fingerprint_worktree
from a_scanner.models import CommandResult, DetectedProject, Ecosystem, Mode, ScanReport
from a_scanner.report import persist_report
from a_scanner.runner import CommandRunner


class RecordingRunner:
    def __init__(self, *results: CommandResult) -> None:
        self.results = list(results)
        self.calls: list[list[str]] = []

    def run(self, argv, *, cwd, **kwargs) -> CommandResult:
        del kwargs
        self.calls.append(list(argv))
        if self.results:
            return self.results.pop(0)
        return CommandResult(
            argv=list(argv),
            cwd=str(cwd),
            exit_code=0,
            stdout="",
            stderr="",
            duration_seconds=0.0,
        )


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _committed_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.email", "fixture@example.com")
    _git(repository, "config", "user.name", "Fixture")
    (repository / "old.txt").write_text("tracked\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial")
    return repository


def _scan_report(repository: Path, run_id: str = "audit-regression") -> ScanReport:
    return ScanReport(
        schema_version=1,
        tool_version="0.1.1",
        run_id=run_id,
        started_at="2026-08-29T00:00:00+00:00",
        completed_at="2026-08-29T00:00:01+00:00",
        repository=str(repository),
        git_head="abc123",
        mode="check",
        status="check_completed",
        initially_clean=True,
    )


def test_explicit_missing_config_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(tmp_path, Path("missing.toml"))


def test_npm_lifecycle_scripts_are_disabled_by_default(tmp_path: Path) -> None:
    runner = RecordingRunner()
    adapter = NpmAdapter(runner)
    project = DetectedProject(
        ecosystem=Ecosystem.NPM,
        path=tmp_path,
        manifest=tmp_path / "package.json",
        lockfile=tmp_path / "package-lock.json",
    )

    adapter.apply_compatible_update(project)

    assert runner.calls == [["npm", "update", "--save", "--ignore-scripts"]]


def test_npm_ignore_scripts_can_be_explicitly_disabled(tmp_path: Path) -> None:
    (tmp_path / "a-scanner.toml").write_text(
        "schema_version = 1\n[npm]\nignore_scripts = false\n",
        encoding="utf-8",
    )

    config = load_config(tmp_path, None)

    assert getattr(config, "npm_ignore_scripts", None) is False


def test_invalid_package_json_becomes_inventory_failure(tmp_path: Path) -> None:
    package_json = tmp_path / "package.json"
    package_json.write_text("{invalid", encoding="utf-8")
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("{}", encoding="utf-8")
    runner = RecordingRunner()
    adapter = NpmAdapter(runner)
    project = DetectedProject(Ecosystem.NPM, tmp_path, package_json, lockfile)

    record = adapter.snapshot(project)

    assert has_failed_npm_inventory(record)
    assert any("package.json" in note for note in record.notes)
    assert runner.calls == []


def test_invalid_package_lock_becomes_inventory_failure(tmp_path: Path) -> None:
    package_json = tmp_path / "package.json"
    package_json.write_text('{"dependencies":{"demo":"^1"}}', encoding="utf-8")
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("{invalid", encoding="utf-8")
    runner = RecordingRunner()
    adapter = NpmAdapter(runner)
    project = DetectedProject(Ecosystem.NPM, tmp_path, package_json, lockfile)

    record = adapter.snapshot(project)

    assert has_failed_npm_inventory(record)
    assert any("package-lock.json" in note for note in record.notes)
    assert runner.calls == []


def test_large_untracked_file_fails_fingerprint_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _committed_repository(tmp_path)
    (repository / "large.bin").write_bytes(b"12345")
    monkeypatch.setattr(
        git_guard,
        "MAX_UNTRACKED_FINGERPRINT_BYTES",
        4,
        raising=False,
    )

    with pytest.raises(GitGuardError, match="too large to fingerprint"):
        fingerprint_worktree(repository, CommandRunner())


def test_changed_files_normalizes_git_rename_to_destination(tmp_path: Path) -> None:
    repository = _committed_repository(tmp_path)
    _git(repository, "mv", "old.txt", "new.txt")

    assert changed_files(repository, CommandRunner()) == ["new.txt"]


def test_uv_unrecognized_json_schema_is_not_reported_as_zero_outdated(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "fixture"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text("version = 1\n", encoding="utf-8")
    runner = RecordingRunner(
        CommandResult(
            argv=["uv", "tree"],
            cwd=str(tmp_path),
            exit_code=0,
            stdout='{"unexpected": []}',
            stderr="",
            duration_seconds=0.0,
        ),
        CommandResult(
            argv=["uv", "tree"],
            cwd=str(tmp_path),
            exit_code=0,
            stdout="fixture v0.1.0",
            stderr="",
            duration_seconds=0.0,
        ),
    )
    adapter = UvAdapter(runner)
    project = DetectedProject(Ecosystem.UV, tmp_path, pyproject, lockfile)

    record = adapter.snapshot(project)

    assert any("inventory unavailable" in note.casefold() for note in record.notes)
    assert len(runner.calls) == 2


def test_allowed_update_files_rejects_project_outside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    project = DetectedProject(
        ecosystem=Ecosystem.NPM,
        path=external,
        manifest=external / "package.json",
        lockfile=external / "package-lock.json",
    )

    with pytest.raises(GitGuardError, match="outside repository"):
        engine._allowed_update_files(repository, [project])


def test_ruff_discovery_ignores_plain_text_mentions(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "fixture"\nversion = "0.1.0"\n# ruff is intentionally not configured\n',
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    project = DetectedProject(Ecosystem.UV, tmp_path, pyproject, tmp_path / "uv.lock")

    commands = discover_validation_commands(tmp_path, [project])

    assert [command.name for command in commands] == ["Pytest"]


def test_ruff_discovery_uses_toml_structure(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "fixture"\nversion = "0.1.0"\n[tool.ruff]\nline-length = 100\n',
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    project = DetectedProject(Ecosystem.UV, tmp_path, pyproject, tmp_path / "uv.lock")

    commands = discover_validation_commands(tmp_path, [project])

    assert [command.name for command in commands] == ["Ruff lint"]


@pytest.mark.parametrize(
    "pattern",
    [
        "a" * 257,
        "(a+)+$",
    ],
)
def test_warning_patterns_reject_resource_exhaustion_shapes(
    tmp_path: Path,
    pattern: str,
) -> None:
    encoded = json.dumps(pattern)
    (tmp_path / "a-scanner.toml").write_text(
        f"schema_version = 1\n[warning]\npatterns = [{encoded}]\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="warning.*pattern"):
        load_config(tmp_path, None)


def test_report_files_are_written_with_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replacements: list[tuple[Path, Path]] = []
    real_replace = report_module.os.replace

    def recording_replace(source, destination) -> None:
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(report_module.os, "replace", recording_replace)

    persist_report(_scan_report(tmp_path), tmp_path / "logs")

    assert len(replacements) == 2
    assert {destination.suffix for _, destination in replacements} == {".json", ".log"}


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission-bit assertion")
def test_report_files_are_private_to_current_user(tmp_path: Path) -> None:
    json_path, text_path = persist_report(_scan_report(tmp_path), tmp_path / "logs")

    for path in (json_path, text_path):
        assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0


def test_path_exclude_prunes_repository_relative_directory(tmp_path: Path) -> None:
    ignored = tmp_path / "packages" / "legacy"
    ignored.mkdir(parents=True)
    (ignored / "package.json").write_text("{}", encoding="utf-8")
    (ignored / "package-lock.json").write_text("{}", encoding="utf-8")

    assert discover_projects(tmp_path, ("packages/legacy",)) == []


def test_rejected_report_directory_event_explains_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _committed_repository(tmp_path)
    external = tmp_path / "external-reports"
    monkeypatch.setattr(engine, "default_report_directory", lambda _: external)

    result = engine.execute(
        engine.ScanOptions(
            repository=repository,
            mode=Mode.CHECK,
            report_directory=repository,
        )
    )

    assert any("default external" in event.casefold() for event in result.events)
    assert result.report_json_path is not None
    assert Path(result.report_json_path).parent == external


def test_command_env_cannot_override_executable_resolution_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_paths: list[str | None] = []
    real_path = os.environ.get("PATH")

    def fake_which(executable: str, path: str | None = None) -> str:
        del executable
        observed_paths.append(path)
        return sys.executable

    monkeypatch.setattr(runner_module.shutil, "which", fake_which)

    result = CommandRunner().run(
        ["python", "-c", "pass"],
        cwd=tmp_path,
        env={"PATH": "attacker-controlled"},
    )

    assert result.exit_code == 0
    assert observed_paths == [real_path]
