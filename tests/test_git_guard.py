import subprocess
from pathlib import Path

import pytest

import a_scanner.git_guard as git_guard
from a_scanner.git_guard import GitGuardError, changed_files, inspect_git, rollback
from a_scanner.models import CommandResult
from a_scanner.runner import CommandRunner


class ScriptedRunner:
    def __init__(self, *results: CommandResult) -> None:
        self.results = list(results)

    def run(self, *args, **kwargs) -> CommandResult:
        del args, kwargs
        return self.results.pop(0)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _committed_repository(tmp_path: Path) -> tuple[CommandRunner, str, Path]:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "fixture@example.com")
    _git(tmp_path, "config", "user.name", "Fixture")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "initial")
    runner = CommandRunner()
    return runner, inspect_git(tmp_path, runner).head, tracked


def test_rollback_restores_clean_repository(tmp_path: Path) -> None:
    runner, head, tracked = _committed_repository(tmp_path)
    tracked.write_text("after\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")

    assert rollback(tmp_path, head, runner) is True
    assert tracked.read_text(encoding="utf-8") == "before\n"
    assert not (tmp_path / "new.txt").exists()
    assert inspect_git(tmp_path, runner).clean


def test_changed_files_raises_when_git_status_fails(tmp_path: Path) -> None:
    runner = ScriptedRunner(
        CommandResult(
            argv=["git", "status"],
            cwd=str(tmp_path),
            exit_code=1,
            stdout="",
            stderr="status failed",
            duration_seconds=0.0,
        )
    )

    with pytest.raises(GitGuardError, match="working-tree change"):
        changed_files(tmp_path, runner)


def test_rollback_returns_false_when_final_inspection_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner, head, tracked = _committed_repository(tmp_path)
    tracked.write_text("after\n", encoding="utf-8")

    def fail_inspection(root: Path, command_runner: CommandRunner):
        del root, command_runner
        raise GitGuardError("verification failed")

    monkeypatch.setattr(git_guard, "inspect_git", fail_inspection)

    assert rollback(tmp_path, head, runner) is False


def test_worktree_fingerprint_detects_tracked_content_change_with_same_status(
    tmp_path: Path,
) -> None:
    runner, _, tracked = _committed_repository(tmp_path)
    tracked.write_text("first change\n", encoding="utf-8")
    first = git_guard.fingerprint_worktree(tmp_path, runner)

    tracked.write_text("second change\n", encoding="utf-8")
    second = git_guard.fingerprint_worktree(tmp_path, runner)

    assert first != second


def test_worktree_fingerprint_detects_untracked_content_change_with_same_path(
    tmp_path: Path,
) -> None:
    runner, _, _ = _committed_repository(tmp_path)
    untracked = tmp_path / "new.txt"
    untracked.write_text("first\n", encoding="utf-8")
    first = git_guard.fingerprint_worktree(tmp_path, runner)

    untracked.write_text("second\n", encoding="utf-8")
    second = git_guard.fingerprint_worktree(tmp_path, runner)

    assert first != second
