from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from a_scanner.models import DetectedProject, Ecosystem

DEFAULT_EXCLUDES = (
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

DEFAULT_WARNING_PATTERNS = (
    "DeprecationWarning",
    "FutureWarning",
    "deprecated",
    "deprecation",
    "will be removed",
    "no longer supported",
    "legacy API",
)


class ConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidationCommand:
    name: str
    argv: tuple[str, ...]
    cwd: str = "."


@dataclass(frozen=True, slots=True)
class ScannerConfig:
    excludes: tuple[str, ...] = DEFAULT_EXCLUDES
    warning_patterns: tuple[str, ...] = DEFAULT_WARNING_PATTERNS
    validation_commands: tuple[ValidationCommand, ...] = field(default_factory=tuple)


def _merge_excludes(configured: object) -> tuple[str, ...]:
    if configured is None:
        additions: list[object] = []
    elif isinstance(configured, list):
        additions = configured
    else:
        raise ConfigError("[scan].exclude must be an array of non-empty strings.")

    merged: list[str] = []
    seen: set[str] = set()

    for index, value in enumerate((*DEFAULT_EXCLUDES, *additions), start=1):
        if not isinstance(value, str) or not value.strip():
            configured_index = index - len(DEFAULT_EXCLUDES)
            raise ConfigError(
                f"[scan].exclude entry {configured_index} must be a non-empty string."
            )

        key = os.path.normcase(value)
        if key not in seen:
            seen.add(key)
            merged.append(value)

    return tuple(merged)


def load_config(repository: Path, config_path: Path | None) -> ScannerConfig:
    path = config_path or repository / "a-scanner.toml"
    if not path.is_absolute():
        path = repository / path
    if not path.exists():
        return ScannerConfig()

    with path.open("rb") as handle:
        data = tomllib.load(handle)

    schema_version = data.get("schema_version", 1)
    if schema_version != 1:
        raise ConfigError(f"Unsupported a-scanner.toml schema_version: {schema_version}")

    excludes = _merge_excludes(data.get("scan", {}).get("exclude"))
    patterns = tuple(data.get("warning", {}).get("patterns", DEFAULT_WARNING_PATTERNS))

    commands: list[ValidationCommand] = []
    raw_commands = data.get("validation", {}).get("commands", [])
    for index, item in enumerate(raw_commands, start=1):
        argv = item.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(v, str) for v in argv):
            raise ConfigError(f"validation.commands entry {index} requires a non-empty argv array.")
        commands.append(
            ValidationCommand(
                name=str(item.get("name") or f"Validation {index}"),
                argv=tuple(argv),
                cwd=str(item.get("cwd") or "."),
            )
        )

    return ScannerConfig(
        excludes=excludes,
        warning_patterns=patterns,
        validation_commands=tuple(commands),
    )


def discover_validation_commands(
    repository: Path,
    projects: list[DetectedProject],
) -> tuple[ValidationCommand, ...]:
    commands: list[ValidationCommand] = []
    seen: set[tuple[str, tuple[str, ...], str]] = set()

    for project in projects:
        relative = project.path.relative_to(repository)
        cwd = "." if str(relative) == "." else relative.as_posix()

        if project.ecosystem is Ecosystem.UV:
            pyproject_text = project.manifest.read_text(encoding="utf-8", errors="replace")
            if (project.path / "tests").exists():
                _append_unique(
                    commands,
                    seen,
                    ValidationCommand("Pytest", ("uv", "run", "--locked", "pytest"), cwd),
                )
            if "ruff" in pyproject_text.lower():
                _append_unique(
                    commands,
                    seen,
                    ValidationCommand(
                        "Ruff lint",
                        ("uv", "run", "--locked", "ruff", "check", "."),
                        cwd,
                    ),
                )

        if project.ecosystem is Ecosystem.NPM:
            try:
                package_data = json.loads(project.manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            scripts = package_data.get("scripts", {})
            for script_name in ("typecheck", "test", "build"):
                script = scripts.get(script_name)
                if not isinstance(script, str):
                    continue
                if script_name == "test" and "no test specified" in script.lower():
                    continue
                _append_unique(
                    commands,
                    seen,
                    ValidationCommand(
                        f"npm {script_name}",
                        ("npm", "run", script_name),
                        cwd,
                    ),
                )

    return tuple(commands)


def _append_unique(
    commands: list[ValidationCommand],
    seen: set[tuple[str, tuple[str, ...], str]],
    command: ValidationCommand,
) -> None:
    key = (command.name, command.argv, command.cwd)
    if key not in seen:
        seen.add(key)
        commands.append(command)
