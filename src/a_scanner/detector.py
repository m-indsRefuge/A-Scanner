from __future__ import annotations

import os
from pathlib import Path

from a_scanner.models import DetectedProject, Ecosystem


def discover_projects(repository: Path, excludes: tuple[str, ...]) -> list[DetectedProject]:
    detected: list[DetectedProject] = []
    normalized_excludes = {os.path.normcase(value) for value in excludes}

    for current, directories, filenames in os.walk(repository):
        directories[:] = sorted(
            directory
            for directory in directories
            if os.path.normcase(directory) not in normalized_excludes
        )
        current_path = Path(current)
        names = set(filenames)

        if {"pyproject.toml", "uv.lock"}.issubset(names):
            detected.append(
                DetectedProject(
                    ecosystem=Ecosystem.UV,
                    path=current_path,
                    manifest=current_path / "pyproject.toml",
                    lockfile=current_path / "uv.lock",
                )
            )

        if {"package.json", "package-lock.json"}.issubset(names):
            detected.append(
                DetectedProject(
                    ecosystem=Ecosystem.NPM,
                    path=current_path,
                    manifest=current_path / "package.json",
                    lockfile=current_path / "package-lock.json",
                )
            )

    return sorted(detected, key=lambda item: (str(item.path), item.ecosystem.value))
