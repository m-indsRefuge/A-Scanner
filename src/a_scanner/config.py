from __future__ import annotations

import json
import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from a_scanner.models import DetectedProject, Ecosystem

DEFAULT_EXCLUDES = (
    ".git",
    ".worktrees",
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

MAX_WARNING_PATTERN_LENGTH = 256
_NESTED_REPEAT_PATTERN = re.compile(
    r"\([^()]*[+*][^()]*\)\s*(?:[+*]|\{\d+(?:,\d*)?\})"
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
    npm_ignore_scripts: bool = True


def _table(data: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = data.get(key, {})
    if not isinstance(value, Mapping):
        raise ConfigError(f"[{key}] must be a table.")
    return value


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


def _warning_patterns(configured: object) -> tuple[str, ...]:
    if configured is None:
        values: object = list(DEFAULT_WARNING_PATTERNS)
    else:
        values = configured

    if not isinstance(values, list):
        raise ConfigError("[warning].patterns must be an array of non-empty strings.")

    patterns: list[str] = []
    for index, value in enumerate(values, start=1):
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"[warning].patterns entry {index} must be a non-empty string.")
        if len(value) > MAX_WARNING_PATTERN_LENGTH:
            raise ConfigError(
                f"[warning].patterns entry {index} pattern exceeds "
                f"{MAX_WARNING_PATTERN_LENGTH} characters."
            )
        if _NESTED_REPEAT_PATTERN.search(value):
            raise ConfigError(
                f"[warning].patterns entry {index} pattern contains nested repetition."
            )
        try:
            re.compile(value, re.IGNORECASE)
        except re.error as exc:
            raise ConfigError(
                f"[warning].patterns entry {index} is an invalid regular expression: {exc}"
            ) from exc
        patterns.append(value)
    return tuple(patterns)


def _validation_commands(configured: object) -> tuple[ValidationCommand, ...]:
    if configured is None:
        values: object = []
    else:
        values = configured

    if not isinstance(values, list):
        raise ConfigError("[validation].commands must be an array of tables.")

    commands: list[ValidationCommand] = []
    for index, item in enumerate(values, start=1):
        if not isinstance(item, Mapping):
            raise ConfigError(f"validation.commands entry {index} must be a table.")

        argv = item.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(value, str) and value.strip() for value in argv)
        ):
            raise ConfigError(f"validation.commands entry {index} requires a non-empty argv array.")

        name_value = item.get("name")
        if name_value is not None and not isinstance(name_value, str):
            raise ConfigError(f"validation.commands entry {index} name must be a string.")
        name = name_value.strip() if isinstance(name_value, str) else ""
        if not name:
            name = f"Validation {index}"

        cwd_value = item.get("cwd")
        if cwd_value is not None and not isinstance(cwd_value, str):
            raise ConfigError(f"validation.commands entry {index} cwd must be a string.")
        cwd = cwd_value.strip() if isinstance(cwd_value, str) else ""
        if not cwd:
            cwd = "."

        commands.append(ValidationCommand(name=name, argv=tuple(argv), cwd=cwd))

    return tuple(commands)


def _boolean_option(
    table: Mapping[str, object],
    key: str,
    *,
    section: str,
    default: bool,
) -> bool:
    value = table.get(key, default)
    if type(value) is not bool:
        raise ConfigError(f"[{section}].{key} must be a boolean.")
    return value


def load_config(repository: Path, config_path: Path | None) -> ScannerConfig:
    explicit_config = config_path is not None
    path = (config_path or repository / "a-scanner.toml").expanduser()
    if not path.is_absolute():
        path = repository / path
    if not path.exists():
        if explicit_config:
            raise ConfigError(f"Config file not found: {path}")
        return ScannerConfig()

    with path.open("rb") as handle:
        data = tomllib.load(handle)

    schema_version = data.get("schema_version", 1)
    if type(schema_version) is not int or schema_version != 1:
        raise ConfigError(f"Unsupported a-scanner.toml schema_version: {schema_version}")

    scan = _table(data, "scan")
    warning = _table(data, "warning")
    validation = _table(data, "validation")
    npm = _table(data, "npm")

    return ScannerConfig(
        excludes=_merge_excludes(scan.get("exclude")),
        warning_patterns=_warning_patterns(warning.get("patterns")),
        validation_commands=_validation_commands(validation.get("commands")),
        npm_ignore_scripts=_boolean_option(
            npm,
            "ignore_scripts",
            section="npm",
            default=True,
        ),
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
            with project.manifest.open("rb") as handle:
                pyproject_data = tomllib.load(handle)
            if (project.path / "tests").exists():
                _append_unique(
                    commands,
                    seen,
                    ValidationCommand("Pytest", ("uv", "run", "--locked", "pytest"), cwd),
                )
            if _has_ruff_configuration(pyproject_data):
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
            if not isinstance(package_data, dict):
                continue
            scripts = package_data.get("scripts", {})
            if not isinstance(scripts, dict):
                continue
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


def _has_ruff_configuration(data: Mapping[str, object]) -> bool:
    tool = data.get("tool")
    if not isinstance(tool, Mapping):
        return False
    return isinstance(tool.get("ruff"), Mapping)


def _append_unique(
    commands: list[ValidationCommand],
    seen: set[tuple[str, tuple[str, ...], str]],
    command: ValidationCommand,
) -> None:
    key = (command.name, command.argv, command.cwd)
    if key not in seen:
        seen.add(key)
        commands.append(command)
