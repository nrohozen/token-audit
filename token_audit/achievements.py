"""Compute and render gamified achievements from scan results.

Achievements are declarative: each entry in ACHIEVEMENTS maps one computed
stat to bronze/silver/gold thresholds. Adding a new achievement is one entry
here plus (if needed) one stat in compute_achievement_stats. Output is plain
text — emoji only, no ANSI escapes.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from .models import ScanResult

_TIER_NAMES = ["bronze", "silver", "gold"]
_TIER_MEDALS = ["🥉", "🥈", "🥇"]
_BAR_WIDTH = 20

_NIGHT_HOURS = frozenset(range(0, 5))    # 00:00–05:00
_DAWN_HOURS = frozenset(range(5, 8))     # 05:00–08:00


@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    emoji: str
    description: str
    hint: str
    stat: str
    tiers: tuple
    kind: str = "count"  # count | duration | percent
    unit: str = ""


ACHIEVEMENTS = [
    Achievement(
        id="night_owl", name="Night Owl", emoji="🦉",
        description="Sessions with activity between midnight and 5am. Sleep is a suggestion.",
        hint="Ship something between 00:00 and 05:00.",
        stat="night_owl_sessions", tiers=(1, 10, 50), unit="sessions",
    ),
    Achievement(
        id="early_bird", name="Early Bird", emoji="🌅",
        description="Sessions with activity between 5am and 8am. The worm never stood a chance.",
        hint="Catch Claude before your coffee does (05:00–08:00).",
        stat="early_bird_sessions", tiers=(1, 10, 50), unit="sessions",
    ),
    Achievement(
        id="marathon", name="Marathon", emoji="🏃",
        description="Your longest single session, wall-clock. Hydration optional.",
        hint="Keep one session going for an hour.",
        stat="longest_session_seconds", tiers=(3_600, 10_800, 21_600), kind="duration",
    ),
    Achievement(
        id="token_millionaire", name="Token Millionaire", emoji="💰",
        description="Lifetime tokens through the context window.",
        hint="Your first million tokens is the hardest.",
        stat="total_tokens", tiers=(1_000_000, 10_000_000, 100_000_000), unit="tokens",
    ),
    Achievement(
        id="streak", name="Streak", emoji="🔥",
        description="Most consecutive calendar days with usage. The grind is real.",
        hint="Use it three days in a row.",
        stat="max_streak_days", tiers=(3, 7, 30), unit="days",
    ),
    Achievement(
        id="polyglot", name="Polyglot", emoji="🗣️",
        description="Distinct models you have put to work.",
        hint="Try a second model.",
        stat="distinct_models", tiers=(2, 4, 6), unit="models",
    ),
    Achievement(
        id="cache_whisperer", name="Cache Whisperer", emoji="⚡",
        description="Share of input-side tokens served from the prompt cache.",
        hint="Get half your input-side tokens from cache.",
        stat="cache_read_share", tiers=(0.5, 0.75, 0.9), kind="percent",
    ),
    Achievement(
        id="weekend_warrior", name="Weekend Warrior", emoji="🎮",
        description="Weekend days with at least one session. Saturdays are for the context window.",
        hint="Code on five weekend days.",
        stat="weekend_days", tiers=(5, 20, 50), unit="days",
    ),
    Achievement(
        id="daily_driver", name="Daily Driver", emoji="📅",
        description="Total distinct days you showed up.",
        hint="Show up on ten different days.",
        stat="distinct_days", tiers=(10, 50, 200), unit="days",
    ),
    Achievement(
        id="big_day", name="Big Day", emoji="📈",
        description="Most tokens burned in a single day.",
        hint="Burn 500,000 tokens before midnight.",
        stat="max_day_tokens", tiers=(500_000, 2_000_000, 10_000_000), unit="tokens",
    ),
    Achievement(
        id="century", name="Century", emoji="💯",
        description="Total sessions started. Quantity has a quality all its own.",
        hint="Ten sessions gets you on the board.",
        stat="total_sessions", tiers=(10, 100, 1_000), unit="sessions",
    ),
]


@dataclass(frozen=True)
class AchievementStatus:
    achievement: Achievement
    value: float
    tier: int  # 0 = locked, 1..3 = bronze/silver/gold

    @property
    def maxed(self) -> bool:
        return self.tier >= len(self.achievement.tiers)

    @property
    def next_threshold(self) -> Optional[float]:
        if self.maxed:
            return None
        return self.achievement.tiers[self.tier]

    @property
    def progress(self) -> float:
        """Progress toward the next tier (0..1); 1.0 when maxed."""
        nxt = self.next_threshold
        if nxt is None:
            return 1.0
        return min(1.0, self.value / nxt) if nxt else 1.0


# ── Stats ─────────────────────────────────────────────────────────────────────

def _max_streak(days) -> int:
    """Longest run of consecutive calendar days in an iterable of dates."""
    streak = 0
    run = 0
    prev: Optional[date] = None
    for d in sorted(set(days)):
        run = run + 1 if (prev is not None and d - prev == timedelta(days=1)) else 1
        streak = max(streak, run)
        prev = d
    return streak


def compute_achievement_stats(result: ScanResult) -> dict:
    """Reduce a ScanResult to the stats the achievement definitions consume.

    Time-of-day and per-day stats use local time, matching wrapped.
    """
    records = result.records
    local_ts = [r.timestamp.astimezone() for r in records]

    session_hours: dict[str, set] = defaultdict(set)
    session_span: dict[str, list] = {}
    tokens_by_day: Counter = Counter()
    models: set[str] = set()

    for r, ts in zip(records, local_ts):
        session_hours[r.session_id].add(ts.hour)
        span = session_span.setdefault(r.session_id, [ts, ts])
        span[0] = min(span[0], ts)
        span[1] = max(span[1], ts)
        tokens_by_day[ts.date()] += r.total_tokens()
        if r.model:
            models.add(r.model)

    days = set(tokens_by_day)

    inp = sum(r.input_tokens for r in records)
    cw = sum(r.cache_creation_tokens for r in records)
    cr = sum(r.cache_read_tokens for r in records)
    input_side = inp + cw + cr
    cache_read_share: Optional[float] = None
    if (cw + cr) > 0 and input_side > 0:
        cache_read_share = cr / input_side

    return {
        "night_owl_sessions": sum(
            1 for hours in session_hours.values() if hours & _NIGHT_HOURS
        ),
        "early_bird_sessions": sum(
            1 for hours in session_hours.values() if hours & _DAWN_HOURS
        ),
        "longest_session_seconds": max(
            ((b - a).total_seconds() for a, b in session_span.values()), default=0.0
        ),
        "total_tokens": sum(r.total_tokens() for r in records),
        "max_streak_days": _max_streak(days),
        "distinct_models": len(models),
        "cache_read_share": cache_read_share,
        "weekend_days": sum(1 for d in days if d.weekday() >= 5),
        "distinct_days": len(days),
        "max_day_tokens": max(tokens_by_day.values(), default=0),
        "total_sessions": len(session_hours),
    }


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate_achievements(
    stats: dict, definitions: list = ACHIEVEMENTS
) -> list[AchievementStatus]:
    """Score each achievement; ones whose stat is unavailable (None) are skipped."""
    statuses = []
    for a in definitions:
        value = stats.get(a.stat)
        if value is None:
            continue
        tier = sum(1 for t in a.tiers if value >= t)
        statuses.append(AchievementStatus(achievement=a, value=value, tier=tier))
    return statuses


# ── Formatting ────────────────────────────────────────────────────────────────

def _fmt_value(a: Achievement, value: float) -> str:
    if a.kind == "duration":
        return f"{value / 3600:.1f}h"
    if a.kind == "percent":
        return f"{value * 100:.1f}%"
    return f"{int(value):,} {a.unit}".rstrip()


def _fmt_threshold(a: Achievement, t: float) -> str:
    if a.kind == "duration":
        return f"{t / 3600:g}h"
    if a.kind == "percent":
        return f"{t * 100:g}%"
    return f"{int(t):,} {a.unit}".rstrip()


def _bar(progress: float) -> str:
    filled = round(_BAR_WIDTH * max(0.0, min(1.0, progress)))
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


def format_achievements(statuses: list[AchievementStatus]) -> str:
    lines = ["Achievements", "============", ""]

    unlocked = [s for s in statuses if s.tier > 0]
    locked = [s for s in statuses if s.tier == 0]
    unlocked.sort(key=lambda s: -s.tier)

    for s in unlocked:
        a = s.achievement
        lines.append(f"{_TIER_MEDALS[s.tier - 1]} {a.emoji} {a.name} — {_TIER_NAMES[s.tier - 1]}")
        lines.append(f"     {a.description}")
        if s.maxed:
            lines.append(f"     {_fmt_value(a, s.value)} · all tiers unlocked")
        else:
            lines.append(
                f"     {_fmt_value(a, s.value)} · next: {_TIER_MEDALS[s.tier]} "
                f"{_TIER_NAMES[s.tier]} at {_fmt_threshold(a, s.next_threshold)}"
            )
            lines.append(f"     {_bar(s.progress)} {s.progress * 100:.0f}%")
        lines.append("")

    if locked:
        lines += ["Locked", "------", ""]
        for s in locked:
            a = s.achievement
            lines.append(
                f"🔒 {a.emoji} {a.name} — {_fmt_value(a, s.value)} so far; "
                f"bronze at {_fmt_threshold(a, a.tiers[0])}"
            )
            lines.append(f"     {a.hint}")
            lines.append("")

    earned = sum(s.tier for s in statuses)
    total_tiers = sum(len(s.achievement.tiers) for s in statuses)
    lines.append(f"Score: {earned}/{total_tiers} tiers unlocked")
    return "\n".join(lines)
