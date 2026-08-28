from pathlib import Path

from a_scanner.models import DependencyRecord, ProjectRecord, ScanReport
from a_scanner.report import persist_report, render_text


def test_persists_text_and_json(tmp_path: Path) -> None:
    report = ScanReport(
        schema_version=1,
        tool_version="0.1.0",
        run_id="test-run",
        started_at="2026-08-06T00:00:00+00:00",
        completed_at="2026-08-06T00:00:01+00:00",
        repository=str(tmp_path),
        git_head="abc",
        mode="check",
        status="check_completed",
        initially_clean=True,
    )
    json_path, text_path = persist_report(report, tmp_path / "logs")
    assert json_path.exists()
    assert text_path.exists()
    assert '"schema_version": 1' in json_path.read_text()
    assert "CHECK_COMPLETED" not in text_path.read_text()
    assert "check_completed" in text_path.read_text()


def test_text_report_surfaces_direct_updates_and_summarizes_transitive() -> None:
    report = ScanReport(
        schema_version=1,
        tool_version="0.1.1",
        run_id="test-run",
        started_at="2026-08-28T00:00:00+00:00",
        completed_at="2026-08-28T00:00:01+00:00",
        repository="C:/Projects/demo",
        git_head="abc123",
        mode="check",
        status="check_completed",
        initially_clean=True,
        projects_before=[
            ProjectRecord(
                ecosystem="uv",
                path="C:/Projects/demo",
                manifest="C:/Projects/demo/pyproject.toml",
                lockfile="C:/Projects/demo/uv.lock",
                direct_dependencies=[DependencyRecord(name="ruff", direct=True)],
                resolved_dependencies=[
                    DependencyRecord(name="ruff", current="0.16.1", direct=True),
                    DependencyRecord(name="pygments", current="2.20.0"),
                ],
                outdated_dependencies=[
                    DependencyRecord(
                        name="ruff",
                        current="0.16.1",
                        wanted="0.16.5",
                        latest="0.16.5",
                        direct=True,
                    ),
                    DependencyRecord(
                        name="pygments",
                        current="2.20.0",
                        wanted="2.21.0",
                        latest="2.21.0",
                    ),
                ],
            )
        ],
    )

    rendered = render_text(report)

    assert "AVAILABLE UPDATES" in rendered
    assert "ruff 0.16.1 -> 0.16.5" in rendered
    assert "1 transitive dependency update available." in rendered
    assert "Check completed. Repository was not modified." in rendered
