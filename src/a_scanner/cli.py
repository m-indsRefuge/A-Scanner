from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from a_scanner import __version__
from a_scanner.engine import ScanOptions, execute
from a_scanner.models import Mode, Status
from a_scanner.report import render_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="a-scan",
        description=(
            "Scan a Git repository for uv/npm dependency updates and deprecation warnings."
        ),
    )
    parser.add_argument("repository", nargs="?", default=".", help="Repository path.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Read-only repository scan (default).")
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply latest-compatible updates, validate, and roll back on failure.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a-scanner.toml; defaults to the repository root.",
    )
    parser.add_argument(
        "--report-directory",
        type=Path,
        default=None,
        help="Override the external report directory.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Terminal output format.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selected_mode = Mode.APPLY if args.apply else Mode.CHECK

    report = execute(
        ScanOptions(
            repository=Path(args.repository),
            mode=selected_mode,
            config_path=args.config,
            report_directory=args.report_directory,
        )
    )

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(render_text(report), end="")

    failure_statuses = {
        Status.PREFLIGHT_FAILED.value,
        Status.BASELINE_FAILED.value,
        Status.UPDATE_FAILED_ROLLED_BACK.value,
        Status.VALIDATION_FAILED_ROLLED_BACK.value,
        Status.ROLLBACK_FAILED.value,
    }
    return 1 if report.status in failure_statuses else 0
