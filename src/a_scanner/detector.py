from __future__ import annotations

import os
from fnmatch import fnmatchcase
from pathlib import Path

from a_scanner.models import DetectedProject, Ecosystem


def discover_projects(repository: Path, excludes: tuple[str, ...]) -> list[DetectedProject]:
    detected: list[DetectedProject] = []
    repository = repository.resolve()
    normalized_excludes = tuple(_normalize_exclude(value) for value in excludes)

    for current, directories, filenames in os.walk(repository):
        current_path = Path(current)
        kept_directories: list[str] = []
        for directory in sorted(directories):
            relative = (current_path / directory).relative_to(repository).as_posix()
            if _is_excluded(directory, relative, normalized_excludes):
                continue
            kept_directories.append(directory)
        directories[:] = kept_directories

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


def _normalize_exclude(value: str) -> str:
    normalized = value.replace("\\", "/").strip("/")
    return os.path.normcase(normalized)


def _is_excluded(
    basename: str,
    relative_path: str,
    patterns: tuple[str, ...],
) -> bool:
    normalized_basename = os.path.normcase(basename)
    normalized_relative = os.path.normcase(relative_path.replace("\\", "/"))
    for pattern in patterns:
        if "/" in pattern or "\\" in pattern:
            candidate = normalized_relative
        else:
            candidate = normalized_basename
        if fnmatchcase(candidate, pattern):
            return True
    return False
