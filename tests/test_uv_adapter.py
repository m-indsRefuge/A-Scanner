import json
from pathlib import Path

from a_scanner.adapters.uv_adapter import UvAdapter
from a_scanner.models import DependencyRecord, DetectedProject, Ecosystem
from a_scanner.runner import CommandRunner


def test_reads_uv_direct_and_lock_dependencies(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    lock = tmp_path / "uv.lock"
    pyproject.write_text(
        """
[project]
name = "fixture"
version = "0.1.0"
dependencies = ["requests>=2"]

[dependency-groups]
dev = ["pytest>=8"]
""".strip()
    )
    lock.write_text(
        """
version = 1

[[package]]
name = "requests"
version = "2.32.0"
source = { registry = "https://pypi.org/simple" }
""".strip()
    )
    project = DetectedProject(Ecosystem.UV, tmp_path, pyproject, lock)
    adapter = UvAdapter(CommandRunner())

    direct = adapter._read_direct(project)
    resolved = adapter._read_lock(project)
    assert {item.name for item in direct} == {"requests", "pytest"}
    assert resolved[0].current == "2.32.0"


def test_generic_uv_outdated_json_parser() -> None:
    adapter = UvAdapter(CommandRunner())
    raw = json.dumps(
        {
            "name": "root",
            "version": "0.1.0",
            "dependencies": [{"name": "demo", "version": "1.0.0", "latest_version": "1.3.0"}],
        }
    )
    records = adapter._parse_outdated_json(
        raw,
        [DependencyRecord(name="demo", direct=True)],
    )
    assert records[0].name == "demo"
    assert records[0].direct is True
    assert records[0].latest == "1.3.0"
