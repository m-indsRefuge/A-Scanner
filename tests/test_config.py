from pathlib import Path

import pytest

from a_scanner.config import (
    DEFAULT_EXCLUDES,
    ConfigError,
    discover_validation_commands,
    load_config,
)
from a_scanner.models import DetectedProject, Ecosystem

CANONICAL_EXCLUDES = (
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".a-scanner",
    ".pytest-tmp",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    ".tox",
    ".nox",
)


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


def test_default_excludes_are_canonical(tmp_path: Path) -> None:
    config = load_config(tmp_path, None)

    assert DEFAULT_EXCLUDES == CANONICAL_EXCLUDES
    assert config.excludes == CANONICAL_EXCLUDES


def test_custom_excludes_extend_and_deduplicate_defaults(tmp_path: Path) -> None:
    path = tmp_path / "a-scanner.toml"
    path.write_text(
        """
schema_version = 1
[scan]
exclude = ["generated", ".venv", "generated"]
""".strip(),
        encoding="utf-8",
    )

    config = load_config(tmp_path, None)

    assert config.excludes == (*CANONICAL_EXCLUDES, "generated")


@pytest.mark.parametrize(
    "exclude_toml",
    [
        'exclude = "generated"',
        'exclude = [""]',
        'exclude = ["   "]',
        "exclude = [42]",
    ],
)
def test_rejects_invalid_exclusion_configuration(
    tmp_path: Path,
    exclude_toml: str,
) -> None:
    path = tmp_path / "a-scanner.toml"
    path.write_text(
        f"schema_version = 1\n[scan]\n{exclude_toml}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"\[scan\]\.exclude"):
        load_config(tmp_path, None)
