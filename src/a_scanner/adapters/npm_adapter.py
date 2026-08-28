from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from a_scanner.adapters.base import PackageAdapter
from a_scanner.models import CommandResult, DependencyRecord, DetectedProject, ProjectRecord

NPM_INVENTORY_FAILURE_NOTE = "npm outdated inspection failed; see command evidence."


def has_failed_npm_inventory(project: ProjectRecord) -> bool:
    return project.ecosystem == "npm" and NPM_INVENTORY_FAILURE_NOTE in project.notes


class NpmAdapter(PackageAdapter):
    executable = "npm"

    def snapshot(self, project: DetectedProject) -> ProjectRecord:
        package_data = json.loads(project.manifest.read_text(encoding="utf-8"))
        direct = self._read_direct(package_data)
        resolved = self._read_lock(project.lockfile, direct)

        outdated_result = self.runner.run(
            ["npm", "outdated", "--all", "--json"],
            cwd=project.path,
        )
        inventory_valid = self._outdated_result_is_valid(outdated_result)
        outdated = self._parse_outdated(outdated_result.stdout, direct) if inventory_valid else []

        notes: list[str] = []
        if not inventory_valid:
            notes.append(NPM_INVENTORY_FAILURE_NOTE)

        return ProjectRecord(
            ecosystem="npm",
            path=str(project.path),
            manifest=str(project.manifest),
            lockfile=str(project.lockfile),
            direct_dependencies=direct,
            resolved_dependencies=resolved,
            outdated_dependencies=outdated,
            command_results=[outdated_result],
            notes=notes,
        )

    def apply_compatible_update(self, project: DetectedProject) -> list[CommandResult]:
        return [
            self.runner.run(
                ["npm", "update", "--save"],
                cwd=project.path,
            )
        ]

    def _read_direct(self, package_data: dict[str, Any]) -> list[DependencyRecord]:
        records: list[DependencyRecord] = []
        sections = (
            "dependencies",
            "devDependencies",
            "optionalDependencies",
            "peerDependencies",
        )
        for section in sections:
            values = package_data.get(section, {})
            if not isinstance(values, dict):
                continue
            for name, requirement in values.items():
                records.append(
                    DependencyRecord(
                        name=name,
                        direct=True,
                        group=section,
                        metadata={"requirement": requirement},
                    )
                )
        return records

    def _read_lock(
        self,
        lockfile: Path,
        direct: list[DependencyRecord],
    ) -> list[DependencyRecord]:
        data = json.loads(lockfile.read_text(encoding="utf-8"))
        direct_names = {item.name for item in direct}
        records: list[DependencyRecord] = []

        packages = data.get("packages")
        if isinstance(packages, dict):
            for location, package in packages.items():
                if not location or not isinstance(package, dict):
                    continue
                name = package.get("name") or _name_from_location(location)
                version = package.get("version")
                if not name:
                    continue
                records.append(
                    DependencyRecord(
                        name=str(name),
                        current=str(version) if version else None,
                        direct=str(name) in direct_names,
                        metadata={"location": location},
                    )
                )
            return records

        dependencies = data.get("dependencies", {})
        if isinstance(dependencies, dict):
            for name, package in dependencies.items():
                if not isinstance(package, dict):
                    continue
                records.append(
                    DependencyRecord(
                        name=name,
                        current=str(package.get("version")) if package.get("version") else None,
                        direct=name in direct_names,
                    )
                )
        return records

    def _outdated_result_is_valid(self, result: CommandResult) -> bool:
        if result.exit_code not in {0, 1}:
            return False

        raw = result.stdout.strip()
        if not raw:
            return result.exit_code == 0

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return False

        if not isinstance(data, dict) or "error" in data:
            return False
        if result.exit_code == 1 and not data:
            return False

        return all(_outdated_entries(details) is not None for details in data.values())

    def _parse_outdated(
        self,
        raw: str,
        direct: list[DependencyRecord],
    ) -> list[DependencyRecord]:
        if not raw.strip():
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, dict):
            return []

        direct_names = {item.name for item in direct}
        records: list[DependencyRecord] = []
        for name, details in data.items():
            entries = _outdated_entries(details)
            if entries is None:
                continue

            current = _common_value(entries, "current")
            wanted = _common_value(entries, "wanted")
            latest = _common_value(entries, "latest")
            metadata_entries = [
                {
                    key: value
                    for key, value in entry.items()
                    if key not in {"current", "wanted", "latest"}
                }
                for entry in entries
            ]
            metadata = metadata_entries[0] if len(entries) == 1 else {"entries": metadata_entries}

            records.append(
                DependencyRecord(
                    name=name,
                    current=current,
                    wanted=wanted,
                    latest=latest,
                    direct=name in direct_names,
                    compatibility_ceiling=any(
                        entry.get("wanted")
                        and entry.get("latest")
                        and entry["wanted"] != entry["latest"]
                        for entry in entries
                    ),
                    metadata=metadata,
                )
            )
        return sorted(records, key=lambda item: item.name.casefold())


def _outdated_entries(details: Any) -> list[dict[str, Any]] | None:
    if isinstance(details, dict):
        entries = [details]
    elif isinstance(details, list) and details and all(isinstance(item, dict) for item in details):
        entries = details
    else:
        return None

    if not all(any(key in entry for key in ("current", "wanted", "latest")) for entry in entries):
        return None
    return entries


def _common_value(entries: list[dict[str, Any]], key: str) -> str | None:
    values = {str(entry[key]) for entry in entries if entry.get(key) is not None}
    if len(values) == 1:
        return values.pop()
    return None


def _name_from_location(location: str) -> str:
    normalized = location.replace("\\", "/")
    marker = "node_modules/"
    if marker not in normalized:
        return normalized.rsplit("/", 1)[-1]
    tail = normalized.rsplit(marker, 1)[-1]
    if tail.startswith("@") and "/" in tail:
        scope, name = tail.split("/", 1)
        return f"{scope}/{name.split('/', 1)[0]}"
    return tail.split("/", 1)[0]
