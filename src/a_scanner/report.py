from __future__ import annotations

import json
import os
import re
from pathlib import Path

from a_scanner.adapters.npm_adapter import has_failed_npm_inventory
from a_scanner.models import DependencyRecord, ScanReport


def default_report_directory(repository: Path) -> Path:
    if local_app_data := os.environ.get("LOCALAPPDATA"):
        base = Path(local_app_data) / "A-Scanner" / "logs"
    elif xdg_state := os.environ.get("XDG_STATE_HOME"):
        base = Path(xdg_state) / "a-scanner" / "logs"
    else:
        base = Path.home() / ".local" / "state" / "a-scanner" / "logs"

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", repository.name).strip("-") or "repository"
    return base / safe_name


def persist_report(report: ScanReport, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stem = report.run_id
    json_path = directory / f"{stem}.json"
    text_path = directory / f"{stem}.log"

    report.report_json_path = str(json_path)
    report.report_text_path = str(text_path)

    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    text_path.write_text(render_text(report), encoding="utf-8", newline="\n")
    return json_path, text_path


def render_text(report: ScanReport) -> str:
    lines = [
        "A-SCANNER",
        "",
        f"Run ID:       {report.run_id}",
        f"Repository:   {report.repository}",
        f"Mode:         {report.mode}",
        f"Status:       {report.status}",
        f"Git HEAD:     {report.git_head or 'unknown'}",
        f"Initial clean:{' ' if report.initially_clean is not None else ''}"
        f"{report.initially_clean}",
        "",
        "PROJECTS BEFORE",
    ]

    if not report.projects_before:
        lines.append("  No supported locked projects detected.")
    for project in report.projects_before:
        inventory_failed = has_failed_npm_inventory(project)
        outdated_summary = (
            "unavailable" if inventory_failed else str(len(project.outdated_dependencies))
        )

        lines.extend(
            [
                f"  [{project.ecosystem}] {project.path}",
                f"    Direct dependencies:   {len(project.direct_dependencies)}",
                f"    Resolved dependencies: {len(project.resolved_dependencies)}",
                f"    Outdated dependencies: {outdated_summary}",
            ]
        )

        if inventory_failed:
            lines.extend(
                [
                    "    Dependency inventory unavailable.",
                    "    See command evidence in the full report.",
                ]
            )
            continue

        direct_updates = [
            dependency for dependency in project.outdated_dependencies if dependency.direct
        ]
        transitive_count = len(project.outdated_dependencies) - len(direct_updates)
        if direct_updates or transitive_count:
            lines.append("    AVAILABLE UPDATES")
            lines.extend(f"      {_render_dependency_update(item)}" for item in direct_updates)
            if transitive_count:
                noun = "update" if transitive_count == 1 else "updates"
                summary = f"{transitive_count} transitive dependency {noun} available."
                lines.append(f"      {summary}")

        ceilings = sum(
            1 for dependency in project.outdated_dependencies if dependency.compatibility_ceiling
        )
        if ceilings:
            lines.append(f"    Compatibility ceilings:{ceilings:2d}")

    lines.extend(
        [
            "",
            f"Deprecation warnings before: {len(report.warnings_before)}",
            f"Deprecation warnings after:  {len(report.warnings_after)}",
            "",
            "VALIDATION",
        ]
    )

    if not report.validation:
        lines.append("  No validation commands ran.")
    for validation in report.validation:
        outcome = "PASS" if validation.passed else "FAIL"
        argv = " ".join(validation.command.argv)
        lines.append(f"  {outcome} [{validation.phase}] {validation.name}: {argv}")

    if report.changed_files:
        lines.extend(["", "CHANGED FILES"])
        lines.extend(f"  {path}" for path in report.changed_files)

    if report.events:
        lines.extend(["", "EVENTS"])
        lines.extend(f"  {event}" for event in report.events)

    lines.extend(
        [
            "",
            "RESULT",
            f"  {_result_message(report)}",
            "",
            f"Rollback verified: {report.rollback_verified}",
            f"JSON report: {report.report_json_path or 'pending'}",
            f"Text report: {report.report_text_path or 'pending'}",
            "",
        ]
    )
    return "\n".join(lines)


def _render_dependency_update(dependency: DependencyRecord) -> str:
    current = dependency.current or "unknown"
    target = dependency.wanted or dependency.latest or "unknown"

    if dependency.compatibility_ceiling and dependency.latest and dependency.latest != target:
        ceiling = f"latest {dependency.latest}; compatibility ceiling"
        if target == current:
            return f"{dependency.name} {current} ({ceiling})"
        return f"{dependency.name} {current} -> {target} ({ceiling})"

    if target == current:
        return f"{dependency.name} {current}"
    return f"{dependency.name} {current} -> {target}"


def _result_message(report: ScanReport) -> str:
    messages = {
        "check_completed": "Check completed. Repository was not modified.",
        "updated": "Compatible dependency updates were applied and validated.",
        "no_changes": "No compatible dependency changes were required.",
        "preflight_failed": "Scan stopped during preflight; inspect the events above.",
        "baseline_failed": "Baseline validation failed; intake state restoration was attempted.",
        "update_failed_rolled_back": (
            "Dependency update failed; original repository state was restored."
        ),
        "validation_failed_rolled_back": (
            "Post-update validation failed; original repository state was restored."
        ),
        "rollback_failed": (
            "Rollback could not be verified; inspect the full report before continuing."
        ),
    }
    return messages.get(report.status, f"Run finished with status: {report.status}.")
