import os
import sys
from pathlib import Path

import pytest

from a_scanner.runner import CommandRunner


@pytest.mark.skipif(sys.platform != "win32", reason="Windows command-shim regression")
def test_runner_executes_windows_cmd_shim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shim = tmp_path / "fixture-tool.cmd"
    shim.write_text(
        "@echo off\r\necho shim-executed\r\n",
        encoding="utf-8",
    )

    existing_path = os.environ.get("PATH", "")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{existing_path}")

    runner = CommandRunner()

    resolved = runner.which("fixture-tool")
    assert resolved is not None
    assert resolved.lower().endswith(".cmd")

    result = runner.run(
        ["fixture-tool"],
        cwd=tmp_path,
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "shim-executed"
    assert result.stderr == ""


@pytest.mark.skipif(sys.platform != "win32", reason="Windows npm integration regression")
def test_runner_executes_real_npm_on_windows() -> None:
    runner = CommandRunner()

    resolved = runner.which("npm")
    assert resolved is not None

    result = runner.run(
        ["npm", "--version"],
        cwd=Path.cwd(),
    )

    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip()
    assert result.stderr == ""
