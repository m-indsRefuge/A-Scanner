from __future__ import annotations

from abc import ABC, abstractmethod

from a_scanner.models import DetectedProject, ProjectRecord
from a_scanner.runner import CommandRunner


class PackageAdapter(ABC):
    executable: str

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    @abstractmethod
    def snapshot(self, project: DetectedProject) -> ProjectRecord:
        raise NotImplementedError

    @abstractmethod
    def apply_compatible_update(self, project: DetectedProject) -> list:
        raise NotImplementedError
