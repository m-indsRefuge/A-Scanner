from pathlib import Path

from a_scanner.config import load_config
from a_scanner.detector import discover_projects
from a_scanner.models import Ecosystem


def test_repository_self_discovery_returns_only_root_uv_project(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    repository = Path(__file__).resolve().parents[1]
    config = load_config(repository, None)
    projects = discover_projects(repository, config.excludes)

    assert [(project.ecosystem, project.path) for project in projects] == [
        (Ecosystem.UV, repository),
    ]
