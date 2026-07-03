"""Generate a "Claude Code Wrapped" single-file HTML page from scan results.

All rendering is stdlib string templating — no template engine, no external
assets, no network requests. The output opens straight from disk.
"""

import html
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Optional

from .achievements import (
    _TIER_MEDALS,
    _TIER_NAMES,
    _fmt_threshold,
    _fmt_value,
    compute_achievement_stats,
    evaluate_achievements,
)
from .models import ScanResult, TokenRecord
from .pricing import PricingTable

# ── Palette (dark mode, validated set — see dataviz reference palette) ───────
# Categorical slots in fixed order; assigned by position, never cycled.
_SERIES = ["#3987e5", "#199e70", "#c98500", "#008300", "#9085e9", "#e66767"]
_BLUE = "#3987e5"
_AQUA = "#199e70"
_OTHER_GRAY = "#565550"

_INK = "#ffffff"
_INK_2 = "#c3c2b7"
_MUTED = "#898781"
_BASELINE = "#383835"

# ── Fun-stat constants ────────────────────────────────────────────────────────
_TOKENS_PER_NOVEL = 117_000        # ~90k words x ~1.3 tokens/word
_TOKENS_WAR_AND_PEACE = 763_000    # ~587k words x ~1.3 tokens/word
_COFFEE_USD = 5.0

_ARCHETYPES = {
    "Bash": ("The Terminal Cowboy", "When in doubt, shell out. You and the command line are on a first-name basis."),
    "PowerShell": ("The Terminal Cowboy", "When in doubt, shell out — one cmdlet at a time."),
    "Edit": ("The Surgeon", "Precise, minimal incisions. No diff too small to care about."),
    "Read": ("The Scholar", "You actually read the code before changing it. Rare. Respected."),
    "Grep": ("The Detective", "Nothing in the codebase hides from your regex. Nothing."),
    "Glob": ("The Cartographer", "You know where every file lives, and you have the patterns to prove it."),
    "Write": ("The Author", "Blank files tremble at your approach."),
    "Agent": ("The Delegator", "Why do one thing at a time when subagents exist?"),
    "Task": ("The Delegator", "Why do one thing at a time when subagents exist?"),
    "WebSearch": ("The Researcher", "Trust, but verify. Then search again just to be sure."),
    "WebFetch": ("The Researcher", "Trust, but verify. Then fetch the page and read it yourself."),
    "TodoWrite": ("The Planner", "No task begins before the checklist exists."),
}
_ARCHETYPE_FALLBACK = ("The Original", "Your favorite tool defies classification. So do you.")
_ARCHETYPE_NO_TOOLS = ("The Conversationalist", "No tool calls at all. Words were enough.")

_TIME_BADGES = [
    ("Night Owl", frozenset({22, 23, 0, 1, 2, 3, 4}), "of your turns happened between 10pm and 5am. Sleep is a suggestion."),
    ("Early Bird", frozenset({5, 6, 7, 8}), "of your turns happened between 5am and 9am. The worm never stood a chance."),
    ("9-to-5er", frozenset({9, 10, 11, 12, 13, 14, 15, 16, 17}), "of your turns happened during office hours. Suspiciously responsible."),
    ("Twilight Tinkerer", frozenset({18, 19, 20, 21}), "of your turns happened between 6pm and 10pm. Dinner can wait."),
]

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ── Small helpers ─────────────────────────────────────────────────────────────

def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _compact(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f}M"
    if n >= 1_000:
        return f"{n / 1e3:.1f}K"
    return str(n)


def _fmt_usd(c: Optional[float]) -> str:
    if c is None:
        return "n/a"
    return f"${c:,.2f}"


def _hour_label(h: int) -> str:
    if h == 0:
        return "12a"
    if h < 12:
        return f"{h}a"
    if h == 12:
        return "12p"
    return f"{h - 12}p"


def _decode_project_dir(name: str) -> str:
    """Best-effort decode of an encoded project directory name to a path."""
    m = re.match(r"^([A-Za-z])--(.+)$", name)
    if m:
        return f"{m.group(1)}:\\" + m.group(2).replace("-", "\\")
    if name.startswith("-"):
        return "/" + name[1:].replace("-", "/")
    return name


def _short_path(path: str) -> str:
    parts = [p for p in re.split(r"[\\/]+", path) if p]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return path


# ── Stats ─────────────────────────────────────────────────────────────────────

def compute_wrapped_stats(result: ScanResult, pricing: Optional[PricingTable]) -> dict:
    """Reduce a ScanResult to everything the Wrapped page displays."""
    records = result.records

    inp = sum(r.input_tokens for r in records)
    out = sum(r.output_tokens for r in records)
    cw = sum(r.cache_creation_tokens for r in records)
    cr = sum(r.cache_read_tokens for r in records)
    total = inp + out + cw + cr

    cost: Optional[float] = None
    cache_saved: Optional[float] = None
    if pricing is not None:
        cost_sum, saved_sum, any_priced = 0.0, 0.0, False
        for r in records:
            c = pricing.compute_cost(
                r.model, r.input_tokens, r.output_tokens,
                r.cache_creation_tokens, r.cache_read_tokens,
            )
            if c is not None:
                cost_sum += c
                any_priced = True
            prices = pricing.get_prices(r.model)
            if prices is not None:
                delta = prices["input"] - prices["cache_read"]
                if delta > 0:
                    saved_sum += r.cache_read_tokens * delta / 1_000_000
        if any_priced:
            cost = cost_sum
            cache_saved = saved_sum

    input_side = inp + cw + cr
    cache_hit_rate = (cr / input_side) if input_side else None

    # Project display names: prefer the most common cwd recorded in the
    # transcripts themselves, fall back to decoding the directory name.
    cwd_by_project: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        if r.cwd:
            cwd_by_project[r.project][r.cwd] += 1

    def display_name(project: str) -> str:
        counts = cwd_by_project.get(project)
        if counts:
            return counts.most_common(1)[0][0]
        return _decode_project_dir(project)

    tokens_by_project: Counter = Counter()
    for r in records:
        tokens_by_project[r.project] += r.total_tokens()
    top_projects = [
        (display_name(p), t) for p, t in tokens_by_project.most_common(5)
    ]

    tokens_by_model: Counter = Counter()
    for r in records:
        tokens_by_model[r.model or "<unknown>"] += r.total_tokens()
    model_mix = []
    for m, t in tokens_by_model.most_common(5):
        model_mix.append((m, t, (t / total) if total else 0.0))
    rest = sum(t for _, t in tokens_by_model.most_common()[5:])
    if rest:
        model_mix.append(("other", rest, rest / total if total else 0.0))

    tool_counts: Counter = Counter()
    for r in records:
        tool_counts.update(r.tool_names)
    top_tools = tool_counts.most_common(5)
    tool_total = sum(tool_counts.values())
    if top_tools:
        archetype = _ARCHETYPES.get(top_tools[0][0], _ARCHETYPE_FALLBACK)
    else:
        archetype = _ARCHETYPE_NO_TOOLS

    # Time habits — everything below uses *local* time.
    local_ts = [r.timestamp.astimezone() for r in records]
    hour_turns = [0] * 24
    for ts in local_ts:
        hour_turns[ts.hour] += 1
    peak_hour = hour_turns.index(max(hour_turns)) if records else None

    turns = len(records)
    badge_title, badge_line = "", ""
    if turns:
        best = max(
            _TIME_BADGES,
            key=lambda b: sum(hour_turns[h] for h in b[1]),
        )
        share = sum(hour_turns[h] for h in best[1]) / turns
        badge_title = best[0]
        badge_line = f"{share * 100:.0f}% {best[2]}"

    tokens_by_day: Counter = Counter()
    turns_by_weekday = [0] * 7
    for r, ts in zip(records, local_ts):
        tokens_by_day[ts.date()] += r.total_tokens()
        turns_by_weekday[ts.weekday()] += 1
    busiest_day = max(tokens_by_day.items(), key=lambda kv: kv[1]) if tokens_by_day else None
    busiest_weekday = None
    if turns:
        wd = max(range(7), key=lambda i: turns_by_weekday[i])
        busiest_weekday = (_WEEKDAYS[wd], turns_by_weekday[wd])

    streak = 0
    days = sorted(tokens_by_day)
    run = 0
    prev: Optional[date] = None
    for d in days:
        run = run + 1 if (prev is not None and d - prev == timedelta(days=1)) else 1
        streak = max(streak, run)
        prev = d

    # Longest session by turns (tokens break ties).
    sessions_agg: dict[str, dict] = {}
    for r, ts in zip(records, local_ts):
        s = sessions_agg.setdefault(
            r.session_id,
            {"turns": 0, "tokens": 0, "project": r.project, "date": ts.date()},
        )
        s["turns"] += 1
        s["tokens"] += r.total_tokens()
        s["date"] = min(s["date"], ts.date())
    longest_session = None
    if sessions_agg:
        best_s = max(sessions_agg.values(), key=lambda s: (s["turns"], s["tokens"]))
        longest_session = {
            "turns": best_s["turns"],
            "tokens": best_s["tokens"],
            "project": _short_path(display_name(best_s["project"])),
            "date": best_s["date"],
        }

    equivalents = []
    if out:
        novels = out / _TOKENS_PER_NOVEL
        equivalents.append((
            f"{novels:.1f}", "novels' worth of output",
            f"{_fmt_int(out)} output tokens at ~90k words a novel. Tolstoy wishes.",
        ))
    if total:
        wnp = total / _TOKENS_WAR_AND_PEACE
        equivalents.append((
            f"{wnp:,.0f}x" if wnp >= 10 else f"{wnp:.1f}x", "War and Peace",
            f"{_fmt_int(total)} total tokens passed through the context window.",
        ))
    if cost:
        coffees = cost / _COFFEE_USD
        equivalents.append((
            f"{coffees:,.0f}", "coffees",
            f"{_fmt_usd(cost)} estimated spend, at $5 a cup. Cheaper than a junior dev.",
        ))

    awards = []
    if top_projects:
        name, t = top_projects[0]
        awards.append((
            "Most Interrogated Project",
            _short_path(name),
            f"{_compact(t)} tokens. It has told you everything it knows.",
        ))
    if longest_session:
        awards.append((
            "Marathon Session Award",
            f"{longest_session['turns']} turns in one sitting",
            f"{longest_session['date']} in {longest_session['project']} — {_compact(longest_session['tokens'])} tokens.",
        ))
    if cache_saved:
        awards.append((
            "Cache Money Award",
            f"{_fmt_usd(cache_saved)} saved",
            f"{_compact(cr)} tokens served from cache instead of full-price input.",
        ))
    if peak_hour is not None and turns:
        awards.append((
            "Power Hour",
            _hour_label(peak_hour),
            f"{hour_turns[peak_hour]} turns landed in your busiest hour of the day.",
        ))
    if streak > 1:
        awards.append((
            "Iron Streak",
            f"{streak} days in a row",
            "Consecutive days with at least one session. The grind is real.",
        ))

    achievements = evaluate_achievements(compute_achievement_stats(result))

    dates = sorted(ts.date() for ts in local_ts)
    return {
        "date_range": (dates[0], dates[-1]) if dates else None,
        "sessions": len({r.session_id for r in records}),
        "turns": turns,
        "projects": len({r.project for r in records}),
        "input": inp,
        "output": out,
        "cache_write": cw,
        "cache_read": cr,
        "total": total,
        "cost": cost,
        "cache_hit_rate": cache_hit_rate,
        "cache_saved": cache_saved,
        "top_projects": top_projects,
        "model_mix": model_mix,
        "top_tools": top_tools,
        "tool_total": tool_total,
        "archetype": archetype,
        "hour_turns": hour_turns,
        "peak_hour": peak_hour,
        "time_badge": (badge_title, badge_line),
        "busiest_day": busiest_day,
        "busiest_weekday": busiest_weekday,
        "streak": streak,
        "longest_session": longest_session,
        "equivalents": equivalents[:3],
        "awards": awards[:5],
        "achievements": achievements,
    }


# ── SVG builders ──────────────────────────────────────────────────────────────

def _col_path(x: float, y: float, w: float, h: float, r: float = 4) -> str:
    """Column with a rounded top and a square baseline."""
    r = min(r, h, w / 2)
    return (
        f"M{x:.1f},{y + h:.1f} v{-(h - r):.1f} q0,{-r:.1f} {r:.1f},{-r:.1f} "
        f"h{w - 2 * r:.1f} q{r:.1f},0 {r:.1f},{r:.1f} v{h - r:.1f} z"
    )


def _hbar_path(x: float, y: float, w: float, h: float, r: float = 4) -> str:
    """Horizontal bar with a rounded data end and a square baseline."""
    r = min(r, w, h / 2)
    return (
        f"M{x:.1f},{y:.1f} h{w - r:.1f} q{r:.1f},0 {r:.1f},{r:.1f} "
        f"v{h - 2 * r:.1f} q0,{r:.1f} {-r:.1f},{r:.1f} h{-(w - r):.1f} z"
    )


def _svg_hours(hour_turns: list) -> str:
    w, h = 720, 190
    top, bottom, side = 26, 26, 6
    plot_h = h - top - bottom
    baseline = h - bottom
    mx = max(hour_turns) if any(hour_turns) else 1
    slot = (w - 2 * side) / 24
    bw = min(24.0, slot - 2)

    parts = [
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Turns by hour of day" preserveAspectRatio="xMidYMid meet">'
    ]
    peak = hour_turns.index(max(hour_turns))
    for hour, v in enumerate(hour_turns):
        x = side + slot * hour + (slot - bw) / 2
        if v > 0:
            bh = max(3.0, plot_h * v / mx)
            parts.append(
                f'<path d="{_col_path(x, baseline - bh, bw, bh)}" fill="{_BLUE}">'
                f"<title>{_hour_label(hour)} — {v} turns</title></path>"
            )
        if v > 0 and hour == peak:
            cx = side + slot * hour + slot / 2
            parts.append(
                f'<text x="{cx:.1f}" y="{baseline - max(3.0, plot_h * v / mx) - 8:.1f}" '
                f'text-anchor="middle" fill="{_INK}" font-size="13" font-weight="600">{v}</text>'
            )
    parts.append(
        f'<line x1="{side}" y1="{baseline}" x2="{w - side}" y2="{baseline}" stroke="{_BASELINE}" stroke-width="1"/>'
    )
    for hour in (0, 6, 12, 18, 23):
        cx = side + slot * hour + slot / 2
        parts.append(
            f'<text x="{cx:.1f}" y="{h - 8}" text-anchor="middle" fill="{_MUTED}" '
            f'font-size="12">{_hour_label(hour)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _svg_hbars(items: list, color: str) -> str:
    """Labeled horizontal bars: items is [(label, value)]."""
    if not items:
        return ""
    row_h, w = 52, 720
    h = row_h * len(items)
    bar_max = w - 90
    mx = max(v for _, v in items) or 1
    parts = [
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Bar chart" preserveAspectRatio="xMidYMid meet">'
    ]
    for i, (label, value) in enumerate(items):
        y = i * row_h
        bw = max(3.0, bar_max * value / mx)
        parts.append(
            f'<text x="0" y="{y + 15}" fill="{_INK_2}" font-size="13">{html.escape(str(label))}</text>'
        )
        parts.append(
            f'<path d="{_hbar_path(0, y + 22, bw, 16)}" fill="{color}">'
            f"<title>{html.escape(str(label))} — {_fmt_int(value)}</title></path>"
        )
        parts.append(
            f'<text x="{bw + 8:.1f}" y="{y + 35}" fill="{_INK}" font-size="12" '
            f'font-weight="600">{_compact(value)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _svg_model_bar(mix: list) -> str:
    """One 100%-stacked bar; mix is [(model, tokens, share)]."""
    if not mix:
        return ""
    w, h, gap = 720, 28, 2
    parts = [
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Model mix" preserveAspectRatio="none" '
        f'style="width:100%;height:{h}px">',
        f'<clipPath id="mixclip"><rect x="0" y="0" width="{w}" height="{h}" rx="6"/></clipPath>',
        '<g clip-path="url(#mixclip)">',
    ]
    x = 0.0
    avail = w - gap * (len(mix) - 1)
    for i, (model, tokens, share) in enumerate(mix):
        color = _OTHER_GRAY if model == "other" else _SERIES[i % len(_SERIES)]
        sw = avail * share
        parts.append(
            f'<rect x="{x:.1f}" y="0" width="{max(sw, 1.0):.1f}" height="{h}" fill="{color}">'
            f"<title>{html.escape(model)} — {share * 100:.1f}%</title></rect>"
        )
        x += sw + gap
    parts.append("</g></svg>")
    return "".join(parts)


# ── HTML ──────────────────────────────────────────────────────────────────────

_CSS = """
:root{
  --plane:#0d0d0d; --surface:#1a1a19;
  --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
  --hairline:rgba(255,255,255,0.10);
  --grad-a:linear-gradient(100deg,#9085e9,#3987e5);
  --grad-b:linear-gradient(100deg,#e66767,#c98500);
  --grad-c:linear-gradient(100deg,#199e70,#3987e5);
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  line-height:1.45;-webkit-font-smoothing:antialiased;
}
main{max-width:760px;margin:0 auto;padding:48px 20px 80px;display:flex;flex-direction:column;gap:28px}
.card{
  background:var(--surface);border:1px solid var(--hairline);border-radius:20px;
  padding:36px 32px;opacity:0;transform:translateY(24px);
  transition:opacity .6s ease,transform .6s ease;
}
.card.in{opacity:1;transform:none}
.kicker{font-size:13px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
.hero-num{font-size:clamp(56px,12vw,104px);font-weight:800;line-height:1.05;letter-spacing:-.02em}
.big{font-size:clamp(40px,8vw,64px);font-weight:800;line-height:1.1;letter-spacing:-.02em}
.grad-a,.grad-b,.grad-c{-webkit-background-clip:text;background-clip:text;color:transparent}
.grad-a{background-image:var(--grad-a)}
.grad-b{background-image:var(--grad-b)}
.grad-c{background-image:var(--grad-c)}
.sub{color:var(--ink2);font-size:16px;margin-top:10px}
.fine{color:var(--muted);font-size:13px;margin-top:8px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;margin-top:22px}
.tile{background:rgba(255,255,255,0.03);border:1px solid var(--hairline);border-radius:12px;padding:14px 16px}
.tile .l{font-size:12px;color:var(--muted);margin-bottom:4px}
.tile .v{font-size:24px;font-weight:700}
.split{margin-top:22px;width:100%;border-collapse:collapse;font-size:14px}
.split td{padding:7px 0;border-bottom:1px solid var(--hairline);color:var(--ink2)}
.split td:last-child{text-align:right;color:var(--ink);font-variant-numeric:tabular-nums;font-weight:600}
.split tr:last-child td{border-bottom:none;font-weight:700;color:var(--ink)}
svg{display:block;width:100%;height:auto;margin-top:20px}
.legend{list-style:none;margin-top:14px;display:flex;flex-direction:column;gap:8px}
.legend li{display:flex;align-items:center;gap:10px;font-size:14px;color:var(--ink2)}
.legend .sw{width:12px;height:12px;border-radius:4px;flex:none}
.legend .pct{margin-left:auto;color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}
.legend .tok{color:var(--muted);font-size:12px;min-width:70px;text-align:right;font-variant-numeric:tabular-nums}
.awards{list-style:none;margin-top:8px;display:flex;flex-direction:column;gap:18px}
.awards li{border-top:1px solid var(--hairline);padding-top:16px}
.awards .t{font-size:13px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.awards .w{font-size:26px;font-weight:800;margin:4px 0 2px}
.awards .d{font-size:14px;color:var(--ink2)}
.ach{list-style:none;margin-top:16px;display:flex;flex-direction:column;gap:14px}
.ach li{border-top:1px solid var(--hairline);padding-top:14px}
.ach li.locked{opacity:.45}
.ach .h{display:flex;align-items:baseline;gap:10px;font-size:16px;font-weight:700}
.ach .medal{flex:none}
.ach .meta{margin-left:auto;font-size:12px;font-weight:600;color:var(--muted);font-variant-numeric:tabular-nums;text-align:right}
.ach .d{font-size:13px;color:var(--ink2);margin-top:2px}
.ach .bar{margin-top:8px;height:6px;border-radius:3px;background:rgba(255,255,255,0.08);overflow:hidden}
.ach .bar span{display:block;height:100%;border-radius:3px;background:var(--grad-a)}
.ach-score{margin-top:20px;font-size:14px;font-weight:700}
.equiv{display:flex;flex-direction:column;gap:20px;margin-top:8px}
.equiv .n{font-size:44px;font-weight:800;line-height:1.1}
.equiv .l{font-size:16px;color:var(--ink2)}
.equiv .d{font-size:13px;color:var(--muted);margin-top:2px}
.closer{text-align:center;padding:44px 32px}
.closer .logo{font-weight:800;font-size:20px}
@media (prefers-reduced-motion:reduce){
  .card{opacity:1;transform:none;transition:none}
}
"""

_JS = """
var cards=document.querySelectorAll('.card');
if(!('IntersectionObserver' in window)||matchMedia('(prefers-reduced-motion: reduce)').matches){
  cards.forEach(function(c){c.classList.add('in')});
}else{
  var io=new IntersectionObserver(function(es){
    es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}});
  },{threshold:0.15});
  cards.forEach(function(c){io.observe(c)});
}
"""


def _card(inner: str) -> str:
    return f'<section class="card">{inner}</section>'


def render_wrapped_html(stats: dict) -> str:
    esc = html.escape
    cards = []

    # Hero
    if stats["date_range"]:
        lo, hi = stats["date_range"]
        period = f"{lo} → {hi}"
    else:
        period = "no transcripts found"
    cards.append(_card(
        '<div class="kicker">Claude Code Wrapped</div>'
        f'<div class="hero-num grad-a">{_compact(stats["total"])}</div>'
        '<div class="sub">tokens. That\'s you and Claude, all in.</div>'
        f'<div class="fine">{esc(period)}</div>'
    ))

    # Headline totals
    tiles = "".join(
        f'<div class="tile"><div class="l">{label}</div><div class="v">{value}</div></div>'
        for label, value in [
            ("Sessions", _fmt_int(stats["sessions"])),
            ("API turns", _fmt_int(stats["turns"])),
            ("Projects", _fmt_int(stats["projects"])),
            ("Est. cost", _fmt_usd(stats["cost"])),
        ]
    )
    split = "".join(
        f"<tr><td>{label}</td><td>{_fmt_int(v)}</td></tr>"
        for label, v in [
            ("Input", stats["input"]),
            ("Output", stats["output"]),
            ("Cache write", stats["cache_write"]),
            ("Cache read", stats["cache_read"]),
            ("Total", stats["total"]),
        ]
    )
    cards.append(_card(
        '<div class="kicker">By the numbers</div>'
        f'<div class="tiles">{tiles}</div>'
        f'<table class="split">{split}</table>'
    ))

    # Cache hero
    if stats["cache_hit_rate"] is not None:
        saved = (
            f"That's roughly <strong>{_fmt_usd(stats['cache_saved'])}</strong> saved versus paying full input price."
            if stats["cache_saved"] else ""
        )
        cards.append(_card(
            '<div class="kicker">Cache money</div>'
            f'<div class="big grad-c">{stats["cache_hit_rate"] * 100:.1f}%</div>'
            f'<div class="sub">of your input-side tokens came straight from the prompt cache — '
            f'{_compact(stats["cache_read"])} tokens you didn\'t pay full freight for. {saved}</div>'
        ))

    # Top projects
    if stats["top_projects"]:
        items = [(_short_path(p), t) for p, t in stats["top_projects"]]
        cards.append(_card(
            '<div class="kicker">Top projects</div>'
            f'<div class="big">{esc(_short_path(stats["top_projects"][0][0]))}</div>'
            '<div class="sub">got the most of your attention.</div>'
            + _svg_hbars(items, _BLUE)
        ))

    # Model mix
    if stats["model_mix"]:
        legend = []
        for i, (model, tokens, share) in enumerate(stats["model_mix"]):
            color = _OTHER_GRAY if model == "other" else _SERIES[i % len(_SERIES)]
            legend.append(
                f'<li><span class="sw" style="background:{color}"></span>{esc(model)}'
                f'<span class="tok">{_compact(tokens)}</span>'
                f'<span class="pct">{share * 100:.1f}%</span></li>'
            )
        cards.append(_card(
            '<div class="kicker">Model mix</div>'
            f'<div class="big">{esc(stats["model_mix"][0][0])}</div>'
            '<div class="sub">was your go-to model, by tokens.</div>'
            + _svg_model_bar(stats["model_mix"])
            + f'<ul class="legend">{"".join(legend)}</ul>'
        ))

    # Tool personality
    title, blurb = stats["archetype"]
    tool_sub = (
        f'Your #1 tool was <strong>{esc(stats["top_tools"][0][0])}</strong> — '
        f'{_fmt_int(stats["top_tools"][0][1])} of your {_fmt_int(stats["tool_total"])} tool calls.'
        if stats["top_tools"] else "Not a single tool call in your transcripts."
    )
    cards.append(_card(
        '<div class="kicker">Tool personality</div>'
        f'<div class="big grad-b">{esc(title)}</div>'
        f'<div class="sub">{tool_sub}</div>'
        f'<div class="fine">{esc(blurb)}</div>'
        + _svg_hbars(stats["top_tools"], _AQUA)
    ))

    # Time habits
    if stats["turns"]:
        badge_title, badge_line = stats["time_badge"]
        habit_tiles = []
        if stats["busiest_day"]:
            d, t = stats["busiest_day"]
            habit_tiles.append(("Busiest day", f"{d} · {_compact(t)} tok"))
        if stats["busiest_weekday"]:
            wd, n = stats["busiest_weekday"]
            habit_tiles.append(("Favorite weekday", f"{wd}"))
        if stats["streak"]:
            habit_tiles.append(("Longest streak", f"{stats['streak']} days"))
        tiles = "".join(
            f'<div class="tile"><div class="l">{esc(l)}</div><div class="v" style="font-size:17px">{esc(v)}</div></div>'
            for l, v in habit_tiles
        )
        cards.append(_card(
            '<div class="kicker">When you code</div>'
            f'<div class="big grad-a">{esc(badge_title)}</div>'
            f'<div class="sub">{esc(badge_line)}</div>'
            + _svg_hours(stats["hour_turns"])
            + f'<div class="tiles">{tiles}</div>'
        ))

    # Longest session
    if stats["longest_session"]:
        s = stats["longest_session"]
        cards.append(_card(
            '<div class="kicker">The marathon</div>'
            f'<div class="big">{_fmt_int(s["turns"])} turns</div>'
            f'<div class="sub">Your longest session — {s["date"]}, in {esc(s["project"])}. '
            f'{_compact(s["tokens"])} tokens before either of you blinked.</div>'
        ))

    # Fun equivalents
    if stats["equivalents"]:
        rows = "".join(
            f'<div><div class="n grad-c">{esc(n)}</div><div class="l">{esc(l)}</div>'
            f'<div class="d">{esc(d)}</div></div>'
            for n, l, d in stats["equivalents"]
        )
        cards.append(_card(
            '<div class="kicker">For scale</div>'
            f'<div class="equiv">{rows}</div>'
        ))

    # Awards
    if stats["awards"]:
        rows = "".join(
            f'<li><div class="t">{esc(t)}</div><div class="w">{esc(w)}</div>'
            f'<div class="d">{esc(d)}</div></li>'
            for t, w, d in stats["awards"]
        )
        cards.append(_card(
            '<div class="kicker">The awards</div>'
            f'<ul class="awards">{rows}</ul>'
        ))

    # Achievements
    if stats["achievements"]:
        statuses = sorted(stats["achievements"], key=lambda s: -s.tier)
        rows = []
        for s in statuses:
            a = s.achievement
            if s.tier > 0:
                if s.maxed:
                    meta = f"{_fmt_value(a, s.value)} · all tiers unlocked"
                else:
                    meta = (
                        f"{_fmt_value(a, s.value)} · next: {_TIER_NAMES[s.tier]} "
                        f"at {_fmt_threshold(a, s.next_threshold)}"
                    )
                rows.append(
                    f'<li><div class="h"><span class="medal">{_TIER_MEDALS[s.tier - 1]}</span>'
                    f'<span>{esc(a.emoji)} {esc(a.name)}</span>'
                    f'<span class="meta">{esc(meta)}</span></div>'
                    f'<div class="d">{esc(a.description)}</div>'
                    f'<div class="bar"><span style="width:{s.progress * 100:.0f}%"></span></div></li>'
                )
            else:
                meta = (
                    f"{_fmt_value(a, s.value)} · bronze at "
                    f"{_fmt_threshold(a, a.tiers[0])}"
                )
                rows.append(
                    f'<li class="locked"><div class="h"><span class="medal">🔒</span>'
                    f'<span>{esc(a.emoji)} {esc(a.name)}</span>'
                    f'<span class="meta">{esc(meta)}</span></div>'
                    f'<div class="d">{esc(a.hint)}</div></li>'
                )
        unlocked = sum(1 for s in statuses if s.tier > 0)
        earned = sum(s.tier for s in statuses)
        total_tiers = sum(len(s.achievement.tiers) for s in statuses)
        cards.append(_card(
            '<div class="kicker">Achievements</div>'
            f'<div class="big grad-b">{unlocked} unlocked</div>'
            f'<div class="sub">out of {len(statuses)} achievements. Medal tally below.</div>'
            f'<ul class="ach">{"".join(rows)}</ul>'
            f'<div class="ach-score">{earned}/{total_tiers} tiers unlocked</div>'
        ))

    # Closer
    cards.append(
        '<section class="card closer">'
        '<div class="logo grad-a">token-audit</div>'
        '<div class="fine">Generated by token-audit &middot; all local, no telemetry</div>'
        '</section>'
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Claude Code Wrapped</title>"
        f"<style>{_CSS}</style></head><body>"
        f"<main>{''.join(cards)}</main>"
        f"<noscript><style>.card{{opacity:1;transform:none}}</style></noscript>"
        f"<script>{_JS}</script>"
        "</body></html>\n"
    )
