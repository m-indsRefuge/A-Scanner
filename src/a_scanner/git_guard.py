from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from a_scanner.runner import CommandRunner


class GitGuardError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GitState:
    root: Path
    head: str
    status: str

    @property
    def clean(self) -> bool:
        return not self.status.strip()


def inspect_git(repository: Path, runner: CommandRunner) -> GitState:
    root_result = runner.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repository,
        timeout_seconds=30,
    )
    if not root_result.succeeded:
        raise GitGuardError("Target path is not inside a Git repository.")

    root = Path(root_result.stdout.strip()).resolve()
    head_result = runner.run(["git", "rev-parse", "HEAD"], cwd=root, timeout_seconds=30)
    if not head_result.succeeded:
        raise GitGuardError("Git repository does not have a readable HEAD commit.")

    status_result = runner.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        timeout_seconds=30,
    )
    if not status_result.succeeded:
        raise GitGuardError("Unable to inspect Git working-tree state.")

    return GitState(
        root=root,
        head=head_result.stdout.strip(),
        status=status_result.stdout,
    )


def changed_files(root: Path, runner: CommandRunner) -> list[str]:
    result = runner.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        timeout_seconds=30,
    )
    if not result.succeeded:
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) >= 4:
            paths.append(line[3:].strip())
    return sorted(set(paths))


def rollback(root: Path, expected_head: str, runner: CommandRunner) -> bool:
    reset = runner.run(["git", "reset", "--hard", expected_head], cwd=root, timeout_seconds=120)
    if not reset.succeeded:
        return False

    clean = runner.run(["git", "clean", "-fd"], cwd=root, timeout_seconds=120)
    if not clean.succeeded:
        return False

    state = inspect_git(root, runner)
    return state.head == expected_head and state.clean
