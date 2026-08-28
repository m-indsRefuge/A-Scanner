from pathlib import Path

import pytest

from a_scanner.config import DEFAULT_EXCLUDES
from a_scanner.detector import discover_projects
from a_scanner.models import Ecosystem

TRANSIENT_DIRECTORIES = (
    ".pytest-tmp",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "__pycache__",
    ".tox",
    ".nox",
)


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


def test_default_excludes_nested_git_worktrees(tmp_path: Path) -> None:
    ignored = tmp_path / ".worktrees" / "feature"
    ignored.mkdir(parents=True)
    (ignored / "package.json").write_text("{}", encoding="utf-8")
    (ignored / "package-lock.json").write_text("{}", encoding="utf-8")

    assert discover_projects(tmp_path, DEFAULT_EXCLUDES) == []


@pytest.mark.parametrize("directory_name", TRANSIENT_DIRECTORIES)
def test_skips_canonical_transient_directories(
    tmp_path: Path,
    directory_name: str,
) -> None:
    ignored = tmp_path / directory_name / "nested"
    ignored.mkdir(parents=True)
    (ignored / "package.json").write_text("{}", encoding="utf-8")
    (ignored / "package-lock.json").write_text("{}", encoding="utf-8")

    assert discover_projects(tmp_path, DEFAULT_EXCLUDES) == []


def test_normalizes_exclusion_names_before_matching(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ignored = tmp_path / "GENERATED" / "nested"
    ignored.mkdir(parents=True)
    (ignored / "package.json").write_text("{}", encoding="utf-8")
    (ignored / "package-lock.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("a_scanner.detector.os.path.normcase", str.casefold)

    assert discover_projects(tmp_path, ("generated",)) == []


def test_discovers_root_project_but_not_transient_nested_projects(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='root'\nversion='0.1.0'\n",
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    transient = tmp_path / ".pytest-tmp" / "fixture"
    transient.mkdir(parents=True)
    (transient / "package.json").write_text("{}", encoding="utf-8")
    (transient / "package-lock.json").write_text("{}", encoding="utf-8")

    projects = discover_projects(tmp_path, DEFAULT_EXCLUDES)

    assert [(project.ecosystem, project.path) for project in projects] == [
        (Ecosystem.UV, tmp_path),
    ]
