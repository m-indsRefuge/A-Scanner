from a_scanner.warning_parser import parse_warnings


def test_parses_and_deduplicates_deprecations() -> None:
    text = """
    DeprecationWarning: old API will be removed
    DeprecationWarning: old API will be removed
    ordinary output
    package-x is deprecated
    """
    records = parse_warnings(
        text,
        ecosystem="uv",
        source="pytest",
        patterns=("DeprecationWarning", "deprecated", "will be removed"),
    )
    assert len(records) == 2
    assert records[0].category == "python_deprecation"
    assert records[1].category == "deprecation"
