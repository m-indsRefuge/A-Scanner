from __future__ import annotations

import json
import re
import tomllib
from typing import Any

from a_scanner.adapters.base import PackageAdapter
from a_scanner.models import CommandResult, DependencyRecord, DetectedProject, ProjectRecord

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")
UV_INVENTORY_UNAVAILABLE_NOTE = (
    "uv outdated dependency inventory unavailable; raw command evidence is preserved."
)


def has_unavailable_uv_inventory(project: ProjectRecord) -> bool:
    return project.ecosystem == "uv" and UV_INVENTORY_UNAVAILABLE_NOTE in project.notes


class UvAdapter(PackageAdapter):
    executable = "uv"

    def snapshot(self, project: DetectedProject) -> ProjectRecord:
        direct = self._read_direct(project)
        resolved = self._read_lock(project)
        command_results: list[CommandResult] = []

        json_result = self.runner.run(
            ["uv", "tree", "--outdated", "--frozen", "--format", "json"],
            cwd=project.path,
        )
        command_results.append(json_result)

        outdated: list[DependencyRecord] = []
        notes: list[str] = []
        json_inventory_valid = False
        if json_result.succeeded:
            try:
                outdated = self._parse_outdated_json(json_result.stdout, direct)
                json_inventory_valid = True
            except ValueError:
                json_inventory_valid = False

        if not json_inventory_valid:
            text_result = self.runner.run(
                ["uv", "tree", "--outdated", "--frozen"],
                cwd=project.path,
            )
            command_results.append(text_result)
            notes.append(UV_INVENTORY_UNAVAILABLE_NOTE)
            if not text_result.succeeded:
                notes.append("uv outdated inspection failed; see command evidence.")

        return ProjectRecord(
            ecosystem="uv",
            path=str(project.path),
            manifest=str(project.manifest),
            lockfile=str(project.lockfile),
            direct_dependencies=direct,
            resolved_dependencies=resolved,
            outdated_dependencies=outdated,
            command_results=command_results,
            notes=notes,
        )

    def apply_compatible_update(self, project: DetectedProject) -> list[CommandResult]:
        lock = self.runner.run(["uv", "lock", "--upgrade"], cwd=project.path)
        results = [lock]
        if lock.succeeded:
            results.append(self.runner.run(["uv", "sync", "--locked"], cwd=project.path))
        return results

    def _read_direct(self, project: DetectedProject) -> list[DependencyRecord]:
        with project.manifest.open("rb") as handle:
            data = tomllib.load(handle)

        records: list[DependencyRecord] = []
        project_table = data.get("project", {})
        self._append_requirements(records, project_table.get("dependencies", []), "runtime")

        optional = project_table.get("optional-dependencies", {})
        for group, requirements in optional.items():
            self._append_requirements(records, requirements, f"optional:{group}")

        groups = data.get("dependency-groups", {})
        for group, requirements in groups.items():
            self._append_requirements(records, requirements, f"group:{group}")

        return records

    def _append_requirements(
        self,
        records: list[DependencyRecord],
        requirements: list[Any],
        group: str,
    ) -> None:
        for requirement in requirements:
            if not isinstance(requirement, str):
                continue
            match = _NAME_PATTERN.match(requirement.strip())
            if not match:
                continue
            records.append(
                DependencyRecord(
                    name=match.group(0),
                    direct=True,
                    group=group,
                    metadata={"requirement": requirement},
                )
            )

    def _read_lock(self, project: DetectedProject) -> list[DependencyRecord]:
        with project.lockfile.open("rb") as handle:
            data = tomllib.load(handle)

        records: list[DependencyRecord] = []
        for package in data.get("package", []):
            name = package.get("name")
            if not isinstance(name, str):
                continue
            records.append(
                DependencyRecord(
                    name=name,
                    current=str(package.get("version")) if package.get("version") else None,
                    direct=False,
                    metadata={"source": package.get("source", {})},
                )
            )
        return records

    def _parse_outdated_json(
        self,
        raw: str,
        direct: list[DependencyRecord],
    ) -> list[DependencyRecord]:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("uv outdated JSON could not be decoded") from exc

        direct_names = {item.name.casefold() for item in direct}
        records: dict[tuple[str, str | None, str | None], DependencyRecord] = {}
        saw_package_node = False

        def visit(node: Any) -> None:
            nonlocal saw_package_node
            if isinstance(node, dict):
                name = node.get("name")
                current = node.get("version") or node.get("current")
                latest = (
                    node.get("latest") or node.get("latest_version") or node.get("latest-version")
                )
                if isinstance(name, str) and current is not None:
                    saw_package_node = True
                if isinstance(name, str) and current and latest and str(current) != str(latest):
                    key = (name, str(current), str(latest))
                    records[key] = DependencyRecord(
                        name=name,
                        current=str(current),
                        wanted=str(latest),
                        latest=str(latest),
                        direct=name.casefold() in direct_names,
                        compatibility_ceiling=False,
                    )
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for item in node:
                    visit(item)

        visit(data)
        if not saw_package_node:
            raise ValueError("uv outdated JSON did not contain a recognized package tree")
        return sorted(records.values(), key=lambda item: item.name.casefold())
