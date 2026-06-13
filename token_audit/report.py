import csv
import io
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .models import ScanResult, TokenRecord
from .pricing import PricingTable


@dataclass
class AggRow:
    key: str
    sessions: int
    turns: int
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    cost: Optional[float]

    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_tokens
            + self.cache_read_tokens
        )

    @property
    def cache_hit_rate(self) -> Optional[float]:
        """Share of input-side tokens served from cache (0..1)."""
        denom = self.cache_read_tokens + self.cache_creation_tokens + self.input_tokens
        if denom == 0:
            return None
        return self.cache_read_tokens / denom

    @property
    def output_yield(self) -> Optional[float]:
        """Output tokens produced per input-side token fed in."""
        denom = self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens
        if denom == 0:
            return None
        return self.output_tokens / denom

    @property
    def cost_per_turn(self) -> Optional[float]:
        if self.cost is None or self.turns == 0:
            return None
        return self.cost / self.turns

    @property
    def cost_per_session(self) -> Optional[float]:
        if self.cost is None or self.sessions == 0:
            return None
        return self.cost / self.sessions


def _agg(key: str, records: list[TokenRecord], pricing: Optional[PricingTable]) -> AggRow:
    sessions = len({r.session_id for r in records})
    inp = sum(r.input_tokens for r in records)
    out = sum(r.output_tokens for r in records)
    cw = sum(r.cache_creation_tokens for r in records)
    cr = sum(r.cache_read_tokens for r in records)

    cost: Optional[float] = None
    if pricing is not None:
        total = 0.0
        any_priced = False
        for r in records:
            c = pricing.compute_cost(
                r.model, r.input_tokens, r.output_tokens,
                r.cache_creation_tokens, r.cache_read_tokens,
            )
            if c is not None:
                total += c
                any_priced = True
        if any_priced:
            cost = total

    return AggRow(
        key=key,
        sessions=sessions,
        turns=len(records),
        input_tokens=inp,
        output_tokens=out,
        cache_creation_tokens=cw,
        cache_read_tokens=cr,
        cost=cost,
    )


# ── Aggregation ───────────────────────────────────────────────────────────────

def agg_by_project(result: ScanResult, pricing: Optional[PricingTable]) -> list[AggRow]:
    buckets: dict[str, list[TokenRecord]] = defaultdict(list)
    for r in result.records:
        buckets[r.project].append(r)
    return [_agg(k, buckets[k], pricing) for k in sorted(buckets)]


def agg_by_model(result: ScanResult, pricing: Optional[PricingTable]) -> list[AggRow]:
    buckets: dict[str, list[TokenRecord]] = defaultdict(list)
    for r in result.records:
        buckets[r.model or "<unknown>"].append(r)
    return [_agg(k, buckets[k], pricing) for k in sorted(buckets)]


def agg_by_day(result: ScanResult, pricing: Optional[PricingTable]) -> list[AggRow]:
    buckets: dict[date, list[TokenRecord]] = defaultdict(list)
    for r in result.records:
        buckets[r.date].append(r)
    return [_agg(str(k), buckets[k], pricing) for k in sorted(buckets)]


def agg_summary(result: ScanResult, pricing: Optional[PricingTable]) -> AggRow:
    return _agg("TOTAL", result.records, pricing)


# ── Formatting helpers ────────────────────────────────────────────────────────

def _fmt_tok(n: int) -> str:
    return f"{n:,}"


def _fmt_cost(c: Optional[float]) -> str:
    if c is None:
        return "n/a"
    return f"${c:,.4f}"


def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:.1f}%"


# (header_label, column_width, attr_name_on_AggRow)
_COLS = [
    ("Sessions",     8, "sessions"),
    ("Turns",        7, "turns"),
    ("Input",       14, "input_tokens"),
    ("Output",      14, "output_tokens"),
    ("Cache Write", 14, "cache_creation_tokens"),
    ("Cache Read",  14, "cache_read_tokens"),
    ("Cache Hit",   10, "cache_hit_rate"),
    ("Est. Cost",   12, "cost"),
    ("$/Turn",      10, "cost_per_turn"),
]


def _vals(row: AggRow) -> list[str]:
    return [
        str(row.sessions),
        str(row.turns),
        _fmt_tok(row.input_tokens),
        _fmt_tok(row.output_tokens),
        _fmt_tok(row.cache_creation_tokens),
        _fmt_tok(row.cache_read_tokens),
        _fmt_pct(row.cache_hit_rate),
        _fmt_cost(row.cost),
        _fmt_cost(row.cost_per_turn),
    ]


# Efficiency view: (header_label, column_width)
_EFF_COLS = [
    ("Sessions",   8),
    ("Turns",      7),
    ("Cache Hit", 10),
    ("Out Yield", 10),
    ("$/Turn",    10),
    ("$/Session", 11),
]


def _eff_vals(row: AggRow) -> list[str]:
    return [
        str(row.sessions),
        str(row.turns),
        _fmt_pct(row.cache_hit_rate),
        _fmt_pct(row.output_yield),
        _fmt_cost(row.cost_per_turn),
        _fmt_cost(row.cost_per_session),
    ]


def format_table(
    title: str,
    rows: list[AggRow],
    total_row: Optional[AggRow],
    key_label: str = "Key",
    efficiency: bool = False,
) -> str:
    cols = [(h, w) for h, w in _EFF_COLS] if efficiency else [(h, w) for h, w, _ in _COLS]
    vals_fn = _eff_vals if efficiency else _vals

    key_w = max(
        len(key_label),
        max((len(r.key) for r in rows), default=0),
        len("TOTAL"),
    )

    header = [key_label.ljust(key_w)] + [h.rjust(w) for h, w in cols]
    sep = ["-" * key_w] + ["-" * w for _, w in cols]

    lines = [title, "=" * len(title), "", "  ".join(header), "  ".join(sep)]

    for row in rows:
        vals = vals_fn(row)
        parts = [row.key.ljust(key_w)] + [v.rjust(w) for v, (_, w) in zip(vals, cols)]
        lines.append("  ".join(parts))

    if total_row is not None:
        vals = vals_fn(total_row)
        lines.append("  ".join(sep))
        parts = ["TOTAL".ljust(key_w)] + [v.rjust(w) for v, (_, w) in zip(vals, cols)]
        lines.append("  ".join(parts))

    return "\n".join(lines)


def format_summary_table(row: AggRow, result: ScanResult) -> str:
    projects = len({r.project for r in result.records})
    models = len({r.model for r in result.records})

    lines = ["Token Usage Summary", "=" * 19, ""]
    lines += [
        f"  Files scanned : {result.scanned_files}",
        f"  Projects      : {projects}",
        f"  Sessions      : {row.sessions}",
        f"  API turns     : {row.turns}",
        f"  Models seen   : {models}",
        "",
    ]

    lw, tw, cw = 12, 16, 12
    sep = "-" * (lw + tw + cw + 4)
    lines.append(f"  {'Token type'.ljust(lw)}  {'Tokens'.rjust(tw)}  {'Cost'.rjust(cw)}")
    lines.append(f"  {sep}")
    for label, tok in [
        ("Input",       row.input_tokens),
        ("Output",      row.output_tokens),
        ("Cache write", row.cache_creation_tokens),
        ("Cache read",  row.cache_read_tokens),
    ]:
        lines.append(f"  {label.ljust(lw)}  {_fmt_tok(tok).rjust(tw)}  {''.rjust(cw)}")

    lines.append(f"  {sep}")
    lines.append(
        f"  {'TOTAL'.ljust(lw)}  {_fmt_tok(row.total_tokens()).rjust(tw)}  {_fmt_cost(row.cost).rjust(cw)}"
    )
    lines.append("")

    lines.append("  Efficiency")
    lines.append(f"  {'-' * 30}")
    for label, val in [
        ("Cache hit rate ", _fmt_pct(row.cache_hit_rate)),
        ("Output yield   ", _fmt_pct(row.output_yield)),
        ("Cost / turn    ", _fmt_cost(row.cost_per_turn)),
        ("Cost / session ", _fmt_cost(row.cost_per_session)),
    ]:
        lines.append(f"  {label}: {val}")
    lines.append("")

    if result.skipped_lines:
        lines.append(
            f"  Warning: {result.skipped_lines} line(s) skipped (malformed JSON or read errors)"
        )

    return "\n".join(lines)


# ── CSV / JSON ────────────────────────────────────────────────────────────────

def format_csv(rows: list[AggRow], key_label: str = "key") -> str:
    buf = io.StringIO()
    fieldnames = [
        key_label, "sessions", "turns",
        "input_tokens", "output_tokens",
        "cache_creation_tokens", "cache_read_tokens",
        "estimated_cost_usd",
        "cache_hit_rate", "output_yield",
        "cost_per_turn_usd", "cost_per_session_usd",
    ]

    def _num(x: Optional[float], places: int) -> str:
        return f"{x:.{places}f}" if x is not None else ""

    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({
            key_label: row.key,
            "sessions": row.sessions,
            "turns": row.turns,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "cache_creation_tokens": row.cache_creation_tokens,
            "cache_read_tokens": row.cache_read_tokens,
            "estimated_cost_usd": _num(row.cost, 6),
            "cache_hit_rate": _num(row.cache_hit_rate, 4),
            "output_yield": _num(row.output_yield, 4),
            "cost_per_turn_usd": _num(row.cost_per_turn, 6),
            "cost_per_session_usd": _num(row.cost_per_session, 6),
        })
    return buf.getvalue()


def format_json(rows: list[AggRow], key_label: str = "key") -> str:
    def _round(x: Optional[float], places: int) -> Optional[float]:
        return round(x, places) if x is not None else None

    out = []
    for row in rows:
        out.append({
            key_label: row.key,
            "sessions": row.sessions,
            "turns": row.turns,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "cache_creation_tokens": row.cache_creation_tokens,
            "cache_read_tokens": row.cache_read_tokens,
            "estimated_cost_usd": _round(row.cost, 6),
            "cache_hit_rate": _round(row.cache_hit_rate, 4),
            "output_yield": _round(row.output_yield, 4),
            "cost_per_turn_usd": _round(row.cost_per_turn, 6),
            "cost_per_session_usd": _round(row.cost_per_session, 6),
        })
    return json.dumps(out, indent=2)
