from a_scanner.cli import build_parser


def test_check_is_default() -> None:
    args = build_parser().parse_args(["."])
    assert args.apply is False
    assert args.check is False


def test_apply_flag() -> None:
    args = build_parser().parse_args([".", "--apply", "--format", "json"])
    assert args.apply is True
    assert args.format == "json"
