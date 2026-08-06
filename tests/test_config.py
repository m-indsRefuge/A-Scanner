from pathlib import Path

import pytest

from a_scanner.config import ConfigError, discover_validation_commands, load_config
from a_scanner.models import DetectedProject, Ecosystem


def test_loads_argument_array_validation(tmp_path: Path) -> None:
    path = tmp_path / "a-scanner.toml"
    path.write_text(
        """
schema_version = 1
[[validation.commands]]
name = "Tests"
argv = ["uv", "run", "pytest"]
cwd = "backend"
""".strip()
    )
    config = load_config(tmp_path, None)
    assert config.validation_commands[0].argv == ("uv", "run", "pytest")
    assert config.validation_commands[0].cwd == "backend"


def test_rejects_string_command(tmp_path: Path) -> None:
    path = tmp_path / "a-scanner.toml"
    path.write_text(
        """
schema_version = 1
[[validation.commands]]
name = "Unsafe"
argv = "uv run pytest"
""".strip()
    )
    with pytest.raises(ConfigError):
        load_config(tmp_path, None)


def test_discovers_npm_validation_commands(tmp_path: Path) -> None:
    package_json = tmp_path / "package.json"
    package_json.write_text(
        '{"scripts":{"typecheck":"tsc --noEmit","test":"vitest run","build":"vite build"}}',
        encoding="utf-8",
    )
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("{}", encoding="utf-8")
    project = DetectedProject(
        ecosystem=Ecosystem.NPM,
        path=tmp_path,
        manifest=package_json,
        lockfile=lockfile,
    )

    commands = discover_validation_commands(tmp_path, [project])

    assert [command.argv for command in commands] == [
        ("npm", "run", "typecheck"),
        ("npm", "run", "test"),
        ("npm", "run", "build"),
    ]
