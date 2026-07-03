"""token-audit: report Claude Code token usage from local session transcripts."""

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from .achievements import (
    compute_achievement_stats,
    evaluate_achievements,
    format_achievements,
)
from .models import ScanResult
from .pricing import PricingTable
from .report import (
    AggRow,
    agg_by_day,
    agg_by_model,
    agg_by_project,
    agg_summary,
    format_csv,
    format_json,
    format_summary_table,
    format_table,
)
from .scanner import scan_directory
from .wrapped import compute_wrapped_stats, render_wrapped_html

_DEFAULT_DATA_DIR = Path.home() / ".claude" / "projects"


def _parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{s}', expected YYYY-MM-DD")


def _filter_by_date(result: ScanResult, since: Optional[date], until: Optional[date]) -> ScanResult:
    if since is None and until is None:
        return result
    records = [
        r for r in result.records
        if (since is None or r.date >= since) and (until is None or r.date <= until)
    ]
    return ScanResult(
        records=records,
        skipped_lines=result.skipped_lines,
        scanned_files=result.scanned_files,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="token-audit",
        description="Report Claude Code token usage from local session transcripts.",
    )
    parser.add_argument(
        "--data-dir",
        metavar="PATH",
        type=Path,
        default=_DEFAULT_DATA_DIR,
        help="Claude projects directory (default: ~/.claude/projects)",
    )
    parser.add_argument(
        "--prices",
        metavar="PATH",
        type=Path,
        default=None,
        help="Path to a prices.toml config file",
    )
    parser.add_argument(
        "--no-cost",
        action="store_true",
        help="Skip cost estimation",
    )
    parser.add_argument(
        "--format",
        choices=["table", "csv", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--efficiency",
        action="store_true",
        help="Show efficiency ratios (cache hit rate, output yield, cost per "
        "turn/session) instead of raw token counts in breakdown tables. "
        "Always included in csv/json output.",
    )
    parser.add_argument(
        "--since",
        metavar="DATE",
        type=_parse_date,
        default=None,
        help="Include only records on or after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--until",
        metavar="DATE",
        type=_parse_date,
        default=None,
        help="Include only records on or before this date (YYYY-MM-DD)",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    sub.add_parser("summary", help="Totals across all projects")
    sub.add_parser("by-project", help="Breakdown by project directory")
    sub.add_parser("by-model", help="Breakdown by model")
    sub.add_parser("by-day", help="Breakdown by calendar day")
    sub.add_parser("achievements", help="Gamified achievements from your usage")

    wrapped = sub.add_parser(
        "wrapped",
        help="Generate a 'Claude Code Wrapped' HTML page",
    )
    wrapped.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        type=Path,
        default=Path("wrapped.html"),
        help="Output HTML file (default: wrapped.html)",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    result = scan_directory(args.data_dir)
    result = _filter_by_date(result, args.since, args.until)

    pricing: Optional[PricingTable] = None
    if not args.no_cost:
        try:
            pricing = PricingTable(args.prices)
        except Exception as exc:
            print(f"Warning: could not load pricing table: {exc}", file=sys.stderr)

    fmt: str = args.format

    if args.command == "summary":
        row = agg_summary(result, pricing)
        if fmt == "table":
            print(format_summary_table(row, result))
        elif fmt == "csv":
            print(format_csv([row], "period"))
        else:
            print(format_json([row], "period"))

    elif args.command == "by-project":
        rows = agg_by_project(result, pricing)
        total = agg_summary(result, pricing)
        if fmt == "table":
            print(format_table("Usage by Project", rows, total, "Project", args.efficiency))
            if result.skipped_lines:
                print(f"\nWarning: {result.skipped_lines} line(s) skipped")
        elif fmt == "csv":
            print(format_csv(rows, "project"))
        else:
            print(format_json(rows, "project"))

    elif args.command == "by-model":
        rows = agg_by_model(result, pricing)
        total = agg_summary(result, pricing)
        if fmt == "table":
            print(format_table("Usage by Model", rows, total, "Model", args.efficiency))
            if result.skipped_lines:
                print(f"\nWarning: {result.skipped_lines} line(s) skipped")
        elif fmt == "csv":
            print(format_csv(rows, "model"))
        else:
            print(format_json(rows, "model"))

    elif args.command == "by-day":
        rows = agg_by_day(result, pricing)
        total = agg_summary(result, pricing)
        if fmt == "table":
            print(format_table("Usage by Day", rows, total, "Date", args.efficiency))
            if result.skipped_lines:
                print(f"\nWarning: {result.skipped_lines} line(s) skipped")
        elif fmt == "csv":
            print(format_csv(rows, "date"))
        else:
            print(format_json(rows, "date"))

    elif args.command == "achievements":
        stats = compute_achievement_stats(result)
        print(format_achievements(evaluate_achievements(stats)))
        if result.skipped_lines:
            print(f"\nWarning: {result.skipped_lines} line(s) skipped")

    elif args.command == "wrapped":
        stats = compute_wrapped_stats(result, pricing)
        args.output.write_text(render_wrapped_html(stats), encoding="utf-8")
        print(args.output)
        if result.skipped_lines:
            print(
                f"Warning: {result.skipped_lines} line(s) skipped", file=sys.stderr
            )

    return 0


def entrypoint() -> None:
    # Windows consoles often default to a legacy codepage that can't
    # encode emoji; degrade gracefully instead of crashing.
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())


if __name__ == "__main__":
    entrypoint()
