from __future__ import annotations

import re
from functools import lru_cache

from a_scanner.models import WarningRecord


@lru_cache(maxsize=64)
def _compile_patterns(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


def parse_warnings(
    text: str,
    *,
    ecosystem: str,
    source: str,
    patterns: tuple[str, ...],
) -> list[WarningRecord]:
    compiled = _compile_patterns(patterns)
    records: list[WarningRecord] = []
    seen: set[str] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or not any(pattern.search(line) for pattern in compiled):
            continue
        normalized = re.sub(r"\s+", " ", line)[:2000]
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        records.append(
            WarningRecord(
                ecosystem=ecosystem,
                source=source,
                line=normalized,
                category=_classify(normalized),
            )
        )

    return records


def _classify(line: str) -> str:
    lowered = line.casefold()
    if "futurewarning" in lowered:
        return "future_warning"
    if "deprecationwarning" in lowered:
        return "python_deprecation"
    if "no longer supported" in lowered:
        return "unsupported"
    if "will be removed" in lowered:
        return "scheduled_removal"
    if "deprecated" in lowered or "deprecation" in lowered:
        return "deprecation"
    return "warning"
