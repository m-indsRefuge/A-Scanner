from pathlib import Path

from a_scanner.detector import discover_projects
from a_scanner.models import Ecosystem


def test_discovers_uv_and_npm_projects(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.1.0'\n")
    (tmp_path / "uv.lock").write_text("version = 1\n")
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text("{}")
    (web / "package-lock.json").write_text("{}")

    projects = discover_projects(tmp_path, (".git", ".venv", "node_modules"))
    assert [(item.ecosystem, item.path) for item in projects] == [
        (Ecosystem.UV, tmp_path),
        (Ecosystem.NPM, web),
    ]


def test_skips_excluded_directories(tmp_path: Path) -> None:
    ignored = tmp_path / "node_modules" / "nested"
    ignored.mkdir(parents=True)
    (ignored / "package.json").write_text("{}")
    (ignored / "package-lock.json").write_text("{}")

    assert discover_projects(tmp_path, ("node_modules",)) == []
