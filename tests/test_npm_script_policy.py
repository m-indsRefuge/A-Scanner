from pathlib import Path

from a_scanner.adapters.npm_adapter import NpmAdapter
from a_scanner.models import CommandResult, DetectedProject, Ecosystem


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, argv, *, cwd, **kwargs) -> CommandResult:
        del kwargs
        self.calls.append(list(argv))
        return CommandResult(
            argv=list(argv),
            cwd=str(cwd),
            exit_code=0,
            stdout="",
            stderr="",
            duration_seconds=0.0,
        )


def test_npm_lifecycle_scripts_can_be_explicitly_enabled(tmp_path: Path) -> None:
    runner = RecordingRunner()
    adapter = NpmAdapter(runner, ignore_scripts=False)
    project = DetectedProject(
        ecosystem=Ecosystem.NPM,
        path=tmp_path,
        manifest=tmp_path / "package.json",
        lockfile=tmp_path / "package-lock.json",
    )

    adapter.apply_compatible_update(project)

    assert runner.calls == [["npm", "update", "--save"]]
