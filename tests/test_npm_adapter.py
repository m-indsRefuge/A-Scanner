import json
from pathlib import Path

from a_scanner.adapters.npm_adapter import NpmAdapter
from a_scanner.models import DependencyRecord
from a_scanner.runner import CommandRunner


def test_outdated_marks_compatibility_ceiling() -> None:
    adapter = NpmAdapter(CommandRunner())
    direct = [DependencyRecord(name="demo", direct=True)]
    raw = json.dumps(
        {
            "demo": {
                "current": "1.0.0",
                "wanted": "1.9.0",
                "latest": "2.1.0",
                "location": "node_modules/demo",
            }
        }
    )
    result = adapter._parse_outdated(raw, direct)
    assert result[0].compatibility_ceiling is True
    assert result[0].wanted == "1.9.0"
    assert result[0].latest == "2.1.0"


def test_reads_package_lock_v3(tmp_path: Path) -> None:
    lock = tmp_path / "package-lock.json"
    lock.write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "root"},
                    "node_modules/demo": {"version": "1.2.3"},
                },
            }
        )
    )
    adapter = NpmAdapter(CommandRunner())
    records = adapter._read_lock(lock, [DependencyRecord(name="demo", direct=True)])
    assert records[0].name == "demo"
    assert records[0].current == "1.2.3"
    assert records[0].direct is True
