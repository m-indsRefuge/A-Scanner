from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from a_scanner.runner import CommandRunner

MAX_UNTRACKED_FINGERPRINT_BYTES = 100 * 1024 * 1024


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
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        timeout_seconds=30,
    )
    if not result.succeeded:
        raise GitGuardError("Unable to inspect Git working-tree changes.")

    fields = result.stdout.split("\0")
    paths: list[str] = []
    index = 0
    while index < len(fields):
        field = fields[index]
        index += 1
        if not field:
            continue
        if len(field) < 4:
            raise GitGuardError("Unable to parse Git working-tree changes.")

        status = field[:2]
        paths.append(field[3:])
        if "R" in status or "C" in status:
            if index >= len(fields) or not fields[index]:
                raise GitGuardError("Unable to parse Git rename/copy change.")
            index += 1

    return sorted(set(paths))


def fingerprint_worktree(root: Path, runner: CommandRunner) -> str:
    root = root.resolve()
    digest = hashlib.sha256()

    head_result = runner.run(["git", "rev-parse", "HEAD"], cwd=root, timeout_seconds=30)
    if not head_result.succeeded:
        raise GitGuardError("Unable to read Git HEAD for worktree fingerprinting.")
    _update_digest(digest, b"HEAD", head_result.stdout.strip().encode("utf-8", errors="replace"))

    diff_result = runner.run(
        ["git", "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--"],
        cwd=root,
        timeout_seconds=120,
    )
    if not diff_result.succeeded:
        raise GitGuardError("Unable to inspect tracked Git changes for worktree fingerprinting.")
    _update_digest(digest, b"DIFF", diff_result.stdout.encode("utf-8", errors="replace"))

    untracked_result = runner.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=root,
        timeout_seconds=30,
    )
    if not untracked_result.succeeded:
        raise GitGuardError("Unable to inspect untracked files for worktree fingerprinting.")

    relative_paths = sorted(path for path in untracked_result.stdout.split("\0") if path)
    for relative in relative_paths:
        encoded_path = relative.encode("utf-8", errors="replace")
        _update_digest(digest, b"PATH", encoded_path)
        path = root / relative
        try:
            if path.is_symlink():
                _update_digest(
                    digest,
                    b"SYMLINK",
                    str(path.readlink()).encode("utf-8", errors="replace"),
                )
            elif path.is_file():
                size = path.stat().st_size
                if size > MAX_UNTRACKED_FINGERPRINT_BYTES:
                    raise GitGuardError(
                        f"Untracked file is too large to fingerprint safely: {relative} "
                        f"({size} bytes; limit {MAX_UNTRACKED_FINGERPRINT_BYTES})."
                    )
                digest.update(b"FILE\0")
                bytes_read = 0
                with path.open("rb") as handle:
                    while chunk := handle.read(1024 * 1024):
                        bytes_read += len(chunk)
                        if bytes_read > MAX_UNTRACKED_FINGERPRINT_BYTES:
                            raise GitGuardError(
                                f"Untracked file grew too large to fingerprint safely: {relative}."
                            )
                        digest.update(chunk)
                digest.update(b"\0")
            else:
                _update_digest(digest, b"OTHER", b"")
        except GitGuardError:
            raise
        except OSError as exc:
            raise GitGuardError(f"Unable to fingerprint untracked path: {relative}") from exc

    return digest.hexdigest()


def _update_digest(digest, label: bytes, value: bytes) -> None:
    digest.update(label)
    digest.update(b"\0")
    digest.update(value)
    digest.update(b"\0")


def rollback(root: Path, expected_head: str, runner: CommandRunner) -> bool:
    reset = runner.run(["git", "reset", "--hard", expected_head], cwd=root, timeout_seconds=120)
    if not reset.succeeded:
        return False

    clean = runner.run(["git", "clean", "-fd"], cwd=root, timeout_seconds=120)
    if not clean.succeeded:
        return False

    try:
        state = inspect_git(root, runner)
    except GitGuardError:
        return False
    return state.head == expected_head and state.clean
