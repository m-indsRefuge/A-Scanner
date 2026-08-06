import subprocess
from pathlib import Path

from a_scanner.git_guard import inspect_git, rollback
from a_scanner.runner import CommandRunner


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_rollback_restores_clean_repository(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "fixture@example.com")
    _git(tmp_path, "config", "user.name", "Fixture")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "initial")

    runner = CommandRunner()
    state = inspect_git(tmp_path, runner)
    tracked.write_text("after\n")
    (tmp_path / "new.txt").write_text("new\n")

    assert rollback(tmp_path, state.head, runner) is True
    assert tracked.read_text() == "before\n"
    assert not (tmp_path / "new.txt").exists()
    assert inspect_git(tmp_path, runner).clean
