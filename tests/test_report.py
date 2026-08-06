from pathlib import Path

from a_scanner.models import ScanReport
from a_scanner.report import persist_report


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
