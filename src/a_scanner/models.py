from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Mode(StrEnum):
    CHECK = "check"
    APPLY = "apply"


class Ecosystem(StrEnum):
    UV = "uv"
    NPM = "npm"


class Status(StrEnum):
    CHECK_COMPLETED = "check_completed"
    UPDATED = "updated"
    NO_CHANGES = "no_changes"
    PREFLIGHT_FAILED = "preflight_failed"
    BASELINE_FAILED = "baseline_failed"
    UPDATE_FAILED_ROLLED_BACK = "update_failed_rolled_back"
    VALIDATION_FAILED_ROLLED_BACK = "validation_failed_rolled_back"
    ROLLBACK_FAILED = "rollback_failed"


@dataclass(slots=True)
class CommandResult:
    argv: list[str]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


@dataclass(slots=True)
class WarningRecord:
    ecosystem: str
    source: str
    line: str
    category: str


@dataclass(slots=True)
class DependencyRecord:
    name: str
    current: str | None = None
    wanted: str | None = None
    latest: str | None = None
    direct: bool = False
    group: str | None = None
    compatibility_ceiling: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProjectRecord:
    ecosystem: str
    path: str
    manifest: str
    lockfile: str
    direct_dependencies: list[DependencyRecord] = field(default_factory=list)
    resolved_dependencies: list[DependencyRecord] = field(default_factory=list)
    outdated_dependencies: list[DependencyRecord] = field(default_factory=list)
    command_results: list[CommandResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidationRecord:
    name: str
    phase: str
    command: CommandResult

    @property
    def passed(self) -> bool:
        return self.command.succeeded


@dataclass(slots=True)
class ScanReport:
    schema_version: int
    tool_version: str
    run_id: str
    started_at: str
    completed_at: str | None
    repository: str
    git_head: str | None
    mode: str
    status: str
    initially_clean: bool | None
    changed_files: list[str] = field(default_factory=list)
    projects_before: list[ProjectRecord] = field(default_factory=list)
    projects_after: list[ProjectRecord] = field(default_factory=list)
    warnings_before: list[WarningRecord] = field(default_factory=list)
    warnings_after: list[WarningRecord] = field(default_factory=list)
    validation: list[ValidationRecord] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    rollback_verified: bool | None = None
    report_json_path: str | None = None
    report_text_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DetectedProject:
    ecosystem: Ecosystem
    path: Path
    manifest: Path
    lockfile: Path
