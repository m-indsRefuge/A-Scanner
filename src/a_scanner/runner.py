from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from a_scanner.models import CommandResult


class CommandRunner:
    def which(self, executable: str) -> str | None:
        return shutil.which(executable)

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout_seconds: int = 1800,
    ) -> CommandResult:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        started = time.monotonic()
        try:
            completed = subprocess.run(
                list(argv),
                cwd=cwd,
                env=merged_env,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
                shell=False,
            )
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            stderr = f"{stderr}\nA-Scanner timeout after {timeout_seconds} seconds.".strip()
        except OSError as exc:
            exit_code = 127
            stdout = ""
            stderr = str(exc)

        return CommandResult(
            argv=list(argv),
            cwd=str(cwd),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=round(time.monotonic() - started, 6),
        )
