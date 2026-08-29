import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

import a_scanner.engine as engine
from a_scanner.engine import ScanOptions, execute
from a_scanner.models import CommandResult, Mode, Status
from a_scanner.runner import CommandRunner


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _npm_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()

    _git(repository, "init")
    _git(repository, "config", "user.email", "fixture@example.com")
    _git(repository, "config", "user.name", "Fixture")

    (repository / "package.json").write_text(
        json.dumps(
            {
                "name": "fixture",
                "version": "1.0.0",
                "scripts": {
                    "test": "echo ok",
                },
                "dependencies": {
                    "demo": "^1.0.0",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (repository / "package-lock.json").write_text(
        json.dumps(
            {
                "name": "fixture",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {
                    "": {
                        "name": "fixture",
                        "version": "1.0.0",
                        "dependencies": {
                            "demo": "^1.0.0",
                        },
                    },
                    "node_modules/demo": {
                        "version": "1.0.0",
                    },
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial")
    return repository


class FailingNpmInventoryRunner(CommandRunner):
    def which(self, executable: str) -> str | None:
        if executable == "npm":
            return "npm"
        return super().which(executable)

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: int = 1800,
    ) -> CommandResult:
        if list(argv)[:2] == ["npm", "outdated"]:
            return CommandResult(
                argv=list(argv),
                cwd=str(cwd),
                exit_code=127,
                stdout="",
                stderr="[WinError 2] The system cannot find the file specified",
                duration_seconds=0.0,
            )

        return super().run(
            argv,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
        )


class ErrorJsonNpmInventoryRunner(CommandRunner):
    def which(self, executable: str) -> str | None:
        if executable == "npm":
            return "npm"
        return super().which(executable)

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: int = 1800,
    ) -> CommandResult:
        if list(argv)[:2] == ["npm", "outdated"]:
            return CommandResult(
                argv=list(argv),
                cwd=str(cwd),
                exit_code=1,
                stdout=json.dumps(
                    {
                        "error": {
                            "code": "E401",
                            "summary": "Unauthorized",
                        }
                    }
                ),
                stderr="",
                duration_seconds=0.0,
            )

        return super().run(
            argv,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
        )


class PostUpdateFailingNpmInventoryRunner(CommandRunner):
    def __init__(self) -> None:
        self.outdated_calls = 0

    def which(self, executable: str) -> str | None:
        if executable == "npm":
            return "npm"
        return super().which(executable)

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: int = 1800,
    ) -> CommandResult:
        command = list(argv)

        if command[:2] == ["npm", "outdated"]:
            self.outdated_calls += 1
            if self.outdated_calls == 1:
                return CommandResult(
                    argv=command,
                    cwd=str(cwd),
                    exit_code=1,
                    stdout=json.dumps(
                        {
                            "demo": {
                                "current": "1.0.0",
                                "wanted": "1.0.1",
                                "latest": "2.0.0",
                            }
                        }
                    ),
                    stderr="",
                    duration_seconds=0.0,
                )
            return CommandResult(
                argv=command,
                cwd=str(cwd),
                exit_code=127,
                stdout="",
                stderr="post-update npm inventory failed",
                duration_seconds=0.0,
            )

        if command == ["npm", "update", "--save", "--ignore-scripts"]:
            lockfile = cwd / "package-lock.json"
            lock_data = json.loads(lockfile.read_text(encoding="utf-8"))
            lock_data["packages"]["node_modules/demo"]["version"] = "1.0.1"
            lockfile.write_text(json.dumps(lock_data, indent=2) + "\n", encoding="utf-8")
            return CommandResult(
                argv=command,
                cwd=str(cwd),
                exit_code=0,
                stdout="updated",
                stderr="",
                duration_seconds=0.0,
            )

        if command == ["npm", "run", "test"]:
            return CommandResult(
                argv=command,
                cwd=str(cwd),
                exit_code=0,
                stdout="ok",
                stderr="",
                duration_seconds=0.0,
            )

        return super().run(
            argv,
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
        )


def test_check_fails_closed_when_npm_outdated_inspection_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _npm_repository(tmp_path)
    reports = tmp_path / "reports"

    monkeypatch.setattr(engine, "CommandRunner", FailingNpmInventoryRunner)

    report = execute(
        ScanOptions(
            repository=repository,
            mode=Mode.CHECK,
            report_directory=reports,
        )
    )

    assert len(report.projects_before) == 1

    project = report.projects_before[0]

    assert project.command_results[0].exit_code == 127
    assert any("npm outdated inspection failed" in note.lower() for note in project.notes)

    assert report.status == Status.PREFLIGHT_FAILED.value
    assert any(
        "npm inventory" in event.lower() and "failed" in event.lower() for event in report.events
    )


def test_failed_npm_inventory_is_rendered_as_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from a_scanner.report import render_text

    repository = _npm_repository(tmp_path)
    reports = tmp_path / "reports"

    monkeypatch.setattr(engine, "CommandRunner", FailingNpmInventoryRunner)

    report = execute(
        ScanOptions(
            repository=repository,
            mode=Mode.CHECK,
            report_directory=reports,
        )
    )

    rendered = render_text(report)

    assert "Outdated dependencies: unavailable" in rendered
    assert "Outdated dependencies: 0" not in rendered


def test_check_rejects_npm_exit_one_error_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from a_scanner.report import render_text

    repository = _npm_repository(tmp_path)
    reports = tmp_path / "reports"

    monkeypatch.setattr(engine, "CommandRunner", ErrorJsonNpmInventoryRunner)

    report = execute(
        ScanOptions(
            repository=repository,
            mode=Mode.CHECK,
            report_directory=reports,
        )
    )

    project = report.projects_before[0]
    rendered = render_text(report)

    assert project.command_results[0].exit_code == 1
    assert project.outdated_dependencies == []
    assert any("npm outdated inspection failed" in note.lower() for note in project.notes)
    assert report.status == Status.PREFLIGHT_FAILED.value
    assert "Outdated dependencies: unavailable" in rendered


def test_apply_rolls_back_when_post_update_npm_inventory_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _npm_repository(tmp_path)
    reports = tmp_path / "reports"
    original_lock = (repository / "package-lock.json").read_text(encoding="utf-8")

    monkeypatch.setattr(engine, "CommandRunner", PostUpdateFailingNpmInventoryRunner)

    report = execute(
        ScanOptions(
            repository=repository,
            mode=Mode.APPLY,
            report_directory=reports,
        )
    )

    assert len(report.projects_after) == 1
    assert report.projects_after[0].command_results[0].exit_code == 127
    assert report.status == Status.UPDATE_FAILED_ROLLED_BACK.value
    assert report.rollback_verified is True
    assert any(
        "post-update npm inventory" in event.lower() and "failed" in event.lower()
        for event in report.events
    )
    assert (repository / "package-lock.json").read_text(encoding="utf-8") == original_lock
    assert _git(repository, "status", "--porcelain").stdout == ""
