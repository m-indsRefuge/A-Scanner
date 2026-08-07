from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from a_scanner import __version__
from a_scanner.adapters import NpmAdapter, UvAdapter
from a_scanner.config import (
    ScannerConfig,
    ValidationCommand,
    discover_validation_commands,
    load_config,
)
from a_scanner.detector import discover_projects
from a_scanner.git_guard import (
    GitGuardError,
    GitState,
    changed_files,
    fingerprint_worktree,
    inspect_git,
    rollback,
)
from a_scanner.models import (
    DetectedProject,
    Ecosystem,
    Mode,
    ScanReport,
    Status,
    ValidationRecord,
)
from a_scanner.report import default_report_directory, persist_report
from a_scanner.runner import CommandRunner
from a_scanner.warning_parser import parse_warnings


@dataclass(frozen=True, slots=True)
class ScanOptions:
    repository: Path
    mode: Mode
    config_path: Path | None = None
    report_directory: Path | None = None


def execute(options: ScanOptions) -> ScanReport:
    runner = CommandRunner()
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%S.%fZ")
    repository = options.repository.expanduser().resolve()
    git_state: GitState | None = None
    update_started = False

    report = ScanReport(
        schema_version=1,
        tool_version=__version__,
        run_id=run_id,
        started_at=started.isoformat(),
        completed_at=None,
        repository=str(repository),
        git_head=None,
        mode=options.mode.value,
        status=Status.PREFLIGHT_FAILED.value,
        initially_clean=None,
    )

    try:
        if not repository.exists() or not repository.is_dir():
            report.events.append("Target repository path does not exist or is not a directory.")
            return _finish(report, repository, options.report_directory)

        if runner.which("git") is None:
            report.events.append("Required executable not found on PATH: git")
            return _finish(report, repository, options.report_directory)

        git_state = inspect_git(repository, runner)
        repository = git_state.root
        report.repository = str(repository)
        report.git_head = git_state.head
        report.initially_clean = git_state.clean

        if options.report_directory is not None and _report_directory_is_inside_repository(
            repository,
            options.report_directory,
        ):
            report.events.append("Report directory must be outside the target repository.")
            return _finish(report, repository, None)

        config = load_config(repository, options.config_path)
        projects = discover_projects(repository, config.excludes)
        if not projects:
            if options.mode is Mode.APPLY:
                report.events.append(
                    "Apply mode requires at least one supported locked uv or npm project."
                )
                return _finish(report, repository, options.report_directory)
            report.events.append("No supported locked uv or npm projects were detected.")
            report.status = Status.CHECK_COMPLETED.value
            return _finish(report, repository, options.report_directory)

        missing = sorted(
            {
                project.ecosystem.value
                for project in projects
                if runner.which(_executable_for(project.ecosystem)) is None
            }
        )
        if missing:
            report.events.append(
                "Missing required package manager executable(s): " + ", ".join(missing)
            )
            return _finish(report, repository, options.report_directory)

        adapters = {
            Ecosystem.UV: UvAdapter(runner),
            Ecosystem.NPM: NpmAdapter(runner),
        }

        report.projects_before = [
            adapters[project.ecosystem].snapshot(project) for project in projects
        ]
        report.warnings_before = _collect_warnings(
            report.projects_before,
            config,
            source_prefix="inventory-before",
        )

        if options.mode is Mode.CHECK:
            report.status = Status.CHECK_COMPLETED.value
            return _finish(report, repository, options.report_directory)

        if not git_state.clean:
            report.events.append("Apply mode requires a clean Git working tree.")
            return _finish(report, repository, options.report_directory)

        validation_commands = _validation_commands(repository, projects, config)
        if not validation_commands:
            report.events.append(
                "Apply mode requires configured or conservatively discovered validation commands."
            )
            return _finish(report, repository, options.report_directory)

        baseline_fingerprint = fingerprint_worktree(repository, runner)
        baseline = _run_validation(
            repository,
            validation_commands,
            runner,
            phase="baseline",
            config=config,
            report=report,
        )
        baseline_integrity, baseline_integrity_event = _validation_integrity(
            repository,
            runner,
            expected_head=git_state.head,
            expected_fingerprint=baseline_fingerprint,
            phase="Baseline",
        )
        if baseline_integrity_event:
            report.events.append(baseline_integrity_event)
        if not baseline or not baseline_integrity:
            if not baseline:
                report.events.append(
                    "Baseline validation failed; no dependency updates were attempted."
                )
            if not baseline_integrity:
                report.events.append(
                    "Baseline validation changed Git-visible repository state; "
                    "no dependency updates were attempted."
                )
                return _rollback_after_baseline_integrity_failure(
                    report,
                    repository,
                    git_state.head,
                    runner,
                    options.report_directory,
                )
            report.status = Status.BASELINE_FAILED.value
            return _finish(report, repository, options.report_directory)

        allowed_update_files = _allowed_update_files(repository, projects)
        update_commands = []
        for project in projects:
            update_started = True
            results = adapters[project.ecosystem].apply_compatible_update(project)
            update_commands.extend((project, result) for result in results)
            if any(not result.succeeded for result in results):
                report.events.append(
                    f"Update command failed for {project.ecosystem.value} project {project.path}."
                )
                report.warnings_after.extend(
                    _warnings_from_results(
                        [result for _, result in update_commands],
                        config,
                        ecosystem="mixed",
                        source="update",
                    )
                )
                return _rollback_after_update_failure(
                    report,
                    repository,
                    git_state.head,
                    runner,
                    options.report_directory,
                )

        update_integrity, update_integrity_event = _package_update_integrity(
            repository,
            runner,
            expected_head=git_state.head,
            allowed_files=allowed_update_files,
        )
        if update_integrity_event:
            report.events.append(update_integrity_event)
        if not update_integrity:
            return _rollback_after_update_failure(
                report,
                repository,
                git_state.head,
                runner,
                options.report_directory,
            )

        report.projects_after = [
            adapters[project.ecosystem].snapshot(project) for project in projects
        ]
        report.warnings_after = _collect_warnings(
            report.projects_after,
            config,
            source_prefix="inventory-after",
        )
        report.warnings_after.extend(
            _warnings_from_results(
                [result for _, result in update_commands],
                config,
                ecosystem="mixed",
                source="update",
            )
        )

        post_update_state = inspect_git(repository, runner)
        post_update_fingerprint = fingerprint_worktree(repository, runner)
        post = _run_validation(
            repository,
            validation_commands,
            runner,
            phase="post-update",
            config=config,
            report=report,
        )
        post_integrity, post_integrity_event = _validation_integrity(
            repository,
            runner,
            expected_head=post_update_state.head,
            expected_fingerprint=post_update_fingerprint,
            phase="Post-update",
        )
        if post_integrity_event:
            report.events.append(post_integrity_event)

        changes_inspected = True
        try:
            report.changed_files = changed_files(repository, runner)
        except GitGuardError as exc:
            changes_inspected = False
            report.events.append(f"Post-update Git change inspection failed: {exc}")

        if not post or not post_integrity or not changes_inspected:
            if not post:
                report.events.append("Post-update validation command failed.")
            return _rollback_after_validation_failure(
                report,
                repository,
                git_state.head,
                runner,
                options.report_directory,
            )

        report.rollback_verified = None
        report.status = Status.UPDATED.value if report.changed_files else Status.NO_CHANGES.value
        return _finish(report, repository, options.report_directory)

    except (GitGuardError, OSError, ValueError) as exc:
        report.events.append(f"{type(exc).__name__}: {exc}")
        if update_started and git_state is not None:
            return _rollback_after_update_failure(
                report,
                repository,
                git_state.head,
                runner,
                options.report_directory,
            )
        return _finish(report, repository, options.report_directory)


def _report_directory_is_inside_repository(repository: Path, directory: Path) -> bool:
    resolved = directory.expanduser().resolve()
    return resolved == repository or repository in resolved.parents


def _allowed_update_files(
    repository: Path,
    projects: list[DetectedProject],
) -> set[str]:
    allowed: set[str] = set()
    for project in projects:
        allowed.add(project.manifest.relative_to(repository).as_posix())
        allowed.add(project.lockfile.relative_to(repository).as_posix())
    return allowed


def _package_update_integrity(
    repository: Path,
    runner: CommandRunner,
    *,
    expected_head: str,
    allowed_files: set[str],
) -> tuple[bool, str | None]:
    try:
        state = inspect_git(repository, runner)
        if state.head != expected_head:
            return False, "Package update changed Git HEAD unexpectedly."
        changed = changed_files(repository, runner)
    except GitGuardError as exc:
        return False, f"Package update Git integrity inspection failed: {exc}"

    unexpected = sorted(path for path in changed if path.replace("\\", "/") not in allowed_files)
    if unexpected:
        return (
            False,
            "Package update changed unexpected Git-visible files: " + ", ".join(unexpected),
        )
    return True, None


def _validation_integrity(
    repository: Path,
    runner: CommandRunner,
    *,
    expected_head: str,
    expected_fingerprint: str,
    phase: str,
) -> tuple[bool, str | None]:
    try:
        state = inspect_git(repository, runner)
        if state.head != expected_head:
            return False, f"{phase} validation changed Git HEAD."
        fingerprint = fingerprint_worktree(repository, runner)
    except GitGuardError as exc:
        return False, f"{phase} validation Git integrity inspection failed: {exc}"

    if fingerprint != expected_fingerprint:
        return False, f"{phase} validation changed Git-visible repository content."
    return True, None


def _rollback_after_baseline_integrity_failure(
    report: ScanReport,
    repository: Path,
    expected_head: str,
    runner: CommandRunner,
    report_directory: Path | None,
) -> ScanReport:
    verified = rollback(repository, expected_head, runner)
    report.rollback_verified = verified
    report.status = Status.BASELINE_FAILED.value if verified else Status.ROLLBACK_FAILED.value
    report.events.append("Baseline validation integrity failure; rollback was attempted.")
    return _finish(report, repository, report_directory)


def _rollback_after_update_failure(
    report: ScanReport,
    repository: Path,
    expected_head: str,
    runner: CommandRunner,
    report_directory: Path | None,
) -> ScanReport:
    verified = rollback(repository, expected_head, runner)
    report.rollback_verified = verified
    report.status = (
        Status.UPDATE_FAILED_ROLLED_BACK.value if verified else Status.ROLLBACK_FAILED.value
    )
    report.events.append("Package update failed integrity checks; rollback was attempted.")
    return _finish(report, repository, report_directory)


def _rollback_after_validation_failure(
    report: ScanReport,
    repository: Path,
    expected_head: str,
    runner: CommandRunner,
    report_directory: Path | None,
) -> ScanReport:
    verified = rollback(repository, expected_head, runner)
    report.rollback_verified = verified
    report.status = (
        Status.VALIDATION_FAILED_ROLLED_BACK.value if verified else Status.ROLLBACK_FAILED.value
    )
    report.events.append("Post-update validation failed; rollback was attempted.")
    return _finish(report, repository, report_directory)


def _validation_commands(
    repository: Path,
    projects: list[DetectedProject],
    config: ScannerConfig,
) -> tuple[ValidationCommand, ...]:
    if config.validation_commands:
        return config.validation_commands
    return discover_validation_commands(repository, projects)


def _run_validation(
    repository: Path,
    commands: tuple[ValidationCommand, ...],
    runner: CommandRunner,
    *,
    phase: str,
    config: ScannerConfig,
    report: ScanReport,
) -> bool:
    passed = True
    for command in commands:
        cwd = (repository / command.cwd).resolve()
        if repository not in cwd.parents and cwd != repository:
            report.events.append(
                f"Validation cwd escapes repository and was rejected: {command.cwd}"
            )
            passed = False
            continue

        result = runner.run(
            command.argv,
            cwd=cwd,
            env={
                "PYTHONWARNINGS": "default",
                "NODE_OPTIONS": "--trace-deprecation",
            },
        )
        record = ValidationRecord(name=command.name, phase=phase, command=result)
        report.validation.append(record)
        parsed = parse_warnings(
            f"{result.stdout}\n{result.stderr}",
            ecosystem="validation",
            source=f"{phase}:{command.name}",
            patterns=config.warning_patterns,
        )
        if phase == "baseline":
            report.warnings_before.extend(parsed)
        else:
            report.warnings_after.extend(parsed)
        if not record.passed:
            passed = False
            break
    return passed


def _collect_warnings(projects, config: ScannerConfig, *, source_prefix: str):
    warnings = []
    for project in projects:
        for result in project.command_results:
            warnings.extend(
                parse_warnings(
                    f"{result.stdout}\n{result.stderr}",
                    ecosystem=project.ecosystem,
                    source=f"{source_prefix}:{' '.join(result.argv)}",
                    patterns=config.warning_patterns,
                )
            )
    return warnings


def _warnings_from_results(
    results,
    config: ScannerConfig,
    *,
    ecosystem: str,
    source: str,
):
    warnings = []
    for result in results:
        warnings.extend(
            parse_warnings(
                f"{result.stdout}\n{result.stderr}",
                ecosystem=ecosystem,
                source=f"{source}:{' '.join(result.argv)}",
                patterns=config.warning_patterns,
            )
        )
    return warnings


def _executable_for(ecosystem: Ecosystem) -> str:
    return "uv" if ecosystem is Ecosystem.UV else "npm"


def _finish(
    report: ScanReport,
    repository: Path,
    report_directory: Path | None,
) -> ScanReport:
    report.completed_at = datetime.now(UTC).isoformat()
    directory = report_directory or default_report_directory(repository)
    persist_report(report, directory)
    return report
