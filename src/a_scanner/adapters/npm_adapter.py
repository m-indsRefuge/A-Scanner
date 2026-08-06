from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from a_scanner.adapters.base import PackageAdapter
from a_scanner.models import CommandResult, DependencyRecord, DetectedProject, ProjectRecord


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
        outdated = self._parse_outdated(outdated_result.stdout, direct)

        notes: list[str] = []
        if outdated_result.exit_code not in {0, 1}:
            notes.append("npm outdated inspection failed; see command evidence.")

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
            if not isinstance(details, dict):
                continue
            current = details.get("current")
            wanted = details.get("wanted")
            latest = details.get("latest")
            records.append(
                DependencyRecord(
                    name=name,
                    current=str(current) if current is not None else None,
                    wanted=str(wanted) if wanted is not None else None,
                    latest=str(latest) if latest is not None else None,
                    direct=name in direct_names,
                    compatibility_ceiling=bool(wanted and latest and wanted != latest),
                    metadata={
                        key: value
                        for key, value in details.items()
                        if key not in {"current", "wanted", "latest"}
                    },
                )
            )
        return sorted(records, key=lambda item: item.name.casefold())


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
