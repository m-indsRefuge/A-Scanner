import json
from pathlib import Path

from a_scanner.adapters.npm_adapter import NpmAdapter
from a_scanner.models import CommandResult, DependencyRecord
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


def test_outdated_accepts_array_entries_from_multiple_dependents() -> None:
    adapter = NpmAdapter(CommandRunner())
    raw = json.dumps(
        {
            "magic-string": [
                {
                    "current": "0.30.21",
                    "wanted": "0.30.21",
                    "latest": "1.2.3",
                    "dependent": "@vitest/mocker",
                },
                {
                    "current": "0.30.21",
                    "wanted": "0.30.21",
                    "latest": "1.2.3",
                    "dependent": "vitest",
                },
            ]
        }
    )
    command = CommandResult(
        argv=["npm", "outdated", "--all", "--json"],
        cwd="C:/fixture",
        exit_code=1,
        stdout=raw,
        stderr="",
        duration_seconds=0.0,
    )

    assert adapter._outdated_result_is_valid(command) is True

    result = adapter._parse_outdated(raw, [])
    assert len(result) == 1
    assert result[0].name == "magic-string"
    assert result[0].current == "0.30.21"
    assert result[0].wanted == "0.30.21"
    assert result[0].latest == "1.2.3"
    assert result[0].compatibility_ceiling is True
    assert result[0].metadata["entries"] == [
        {"dependent": "@vitest/mocker"},
        {"dependent": "vitest"},
    ]


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
