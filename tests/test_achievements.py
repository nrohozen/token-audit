"""Test suite for token_audit.achievements module and the 'achievements' CLI command."""

from datetime import datetime, date
from pathlib import Path

from token_audit.achievements import (
    ACHIEVEMENTS,
    Achievement,
    _max_streak,
    compute_achievement_stats,
    evaluate_achievements,
    format_achievements,
)
from token_audit.cli import main
from token_audit.models import ScanResult, TokenRecord
from token_audit.scanner import scan_directory


def _rec(ts, session="s1", model="claude-sonnet-4-6", inp=100, out=10, cw=0, cr=0):
    """Build a TokenRecord with a timezone-aware local timestamp."""
    return TokenRecord(
        project="proj",
        session_file="s.jsonl",
        session_id=session,
        model=model,
        timestamp=ts.astimezone(),
        input_tokens=inp,
        output_tokens=out,
        cache_creation_tokens=cw,
        cache_read_tokens=cr,
    )


def _result(records):
    return ScanResult(records=records, skipped_lines=0, scanned_files=1)


_COUNTER = Achievement(
    id="test", name="Test", emoji="🧪",
    description="d", hint="Do more test things.",
    stat="n", tiers=(10, 100, 1000), unit="things",
)


class TestTierEvaluation:
    """Tests for tier thresholds in evaluate_achievements."""

    def test_below_bronze_is_locked(self):
        (status,) = evaluate_achievements({"n": 9}, [_COUNTER])
        assert status.tier == 0

    def test_exactly_bronze(self):
        (status,) = evaluate_achievements({"n": 10}, [_COUNTER])
        assert status.tier == 1

    def test_between_silver_and_gold(self):
        (status,) = evaluate_achievements({"n": 500}, [_COUNTER])
        assert status.tier == 2
        assert status.next_threshold == 1000
        assert status.progress == 0.5

    def test_at_gold_is_maxed(self):
        (status,) = evaluate_achievements({"n": 1000}, [_COUNTER])
        assert status.tier == 3
        assert status.maxed
        assert status.next_threshold is None
        assert status.progress == 1.0

    def test_unavailable_stat_is_skipped(self):
        """A None stat (e.g. no cache data) excludes the achievement entirely."""
        assert evaluate_achievements({"n": None}, [_COUNTER]) == []

    def test_all_definitions_evaluate_on_empty_stats(self):
        """Every bundled achievement evaluates against zeroed stats."""
        result = scan_directory(Path("/nonexistent/path"))
        stats = compute_achievement_stats(result)
        statuses = evaluate_achievements(stats)
        # cache_read_share is None with no data; all others present, locked.
        assert len(statuses) == len(ACHIEVEMENTS) - 1
        assert all(s.tier == 0 for s in statuses)


class TestMaxStreak:
    """Tests for consecutive-day streak computation."""

    def test_empty(self):
        assert _max_streak([]) == 0

    def test_single_day(self):
        assert _max_streak([date(2026, 1, 15)]) == 1

    def test_consecutive_days(self):
        days = [date(2026, 1, d) for d in (15, 16, 17, 18)]
        assert _max_streak(days) == 4

    def test_gap_breaks_streak(self):
        days = [date(2026, 1, d) for d in (15, 16, 18, 19, 20)]
        assert _max_streak(days) == 3

    def test_unordered_and_duplicated_input(self):
        days = [date(2026, 1, d) for d in (17, 15, 16, 16, 15)]
        assert _max_streak(days) == 3


class TestNightOwlBucketing:
    """Tests for night-owl / early-bird session classification."""

    def test_session_spanning_midnight_counts_once(self):
        """A session with turns at 23:30 and 00:15 counts via the 00:15 turn."""
        records = [
            _rec(datetime(2026, 1, 15, 23, 30), session="s1"),
            _rec(datetime(2026, 1, 16, 0, 15), session="s1"),
        ]
        stats = compute_achievement_stats(_result(records))
        assert stats["night_owl_sessions"] == 1

    def test_late_evening_only_does_not_count(self):
        records = [_rec(datetime(2026, 1, 15, 23, 30))]
        stats = compute_achievement_stats(_result(records))
        assert stats["night_owl_sessions"] == 0

    def test_window_boundaries(self):
        """04:59 is night-owl; 05:00 is early-bird; 08:00 is neither."""
        records = [
            _rec(datetime(2026, 1, 15, 4, 59), session="night"),
            _rec(datetime(2026, 1, 15, 5, 0), session="dawn"),
            _rec(datetime(2026, 1, 15, 8, 0), session="office"),
        ]
        stats = compute_achievement_stats(_result(records))
        assert stats["night_owl_sessions"] == 1
        assert stats["early_bird_sessions"] == 1


class TestComputeAchievementStats:
    """Tests for the stat reducer on synthetic and fixture data."""

    def test_empty_result(self):
        stats = compute_achievement_stats(_result([]))
        assert stats["total_tokens"] == 0
        assert stats["total_sessions"] == 0
        assert stats["max_streak_days"] == 0
        assert stats["longest_session_seconds"] == 0.0
        assert stats["max_day_tokens"] == 0
        assert stats["cache_read_share"] is None

    def test_longest_session_duration(self):
        records = [
            _rec(datetime(2026, 1, 15, 10, 0), session="long"),
            _rec(datetime(2026, 1, 15, 13, 30), session="long"),
            _rec(datetime(2026, 1, 15, 14, 0), session="short"),
        ]
        stats = compute_achievement_stats(_result(records))
        assert stats["longest_session_seconds"] == 3.5 * 3600

    def test_weekend_days(self):
        records = [
            _rec(datetime(2026, 1, 17, 12, 0), session="a"),  # Saturday
            _rec(datetime(2026, 1, 18, 12, 0), session="b"),  # Sunday
            _rec(datetime(2026, 1, 19, 12, 0), session="c"),  # Monday
        ]
        stats = compute_achievement_stats(_result(records))
        assert stats["weekend_days"] == 2
        assert stats["distinct_days"] == 3

    def test_max_day_tokens(self):
        records = [
            _rec(datetime(2026, 1, 15, 10, 0), session="a", inp=1000, out=100),
            _rec(datetime(2026, 1, 15, 11, 0), session="a", inp=2000, out=200),
            _rec(datetime(2026, 1, 16, 10, 0), session="b", inp=500, out=50),
        ]
        stats = compute_achievement_stats(_result(records))
        assert stats["max_day_tokens"] == 3300

    def test_no_cache_data_yields_none_share(self):
        records = [_rec(datetime(2026, 1, 15, 10, 0), inp=100, out=10)]
        stats = compute_achievement_stats(_result(records))
        assert stats["cache_read_share"] is None

    def test_cache_share_ratio(self):
        records = [_rec(datetime(2026, 1, 15, 10, 0), inp=100, cw=100, cr=800)]
        stats = compute_achievement_stats(_result(records))
        assert stats["cache_read_share"] == 0.8

    def test_fixture_totals(self):
        result = scan_directory(Path("tests/fixtures"))
        stats = compute_achievement_stats(result)
        assert stats["total_tokens"] == 62250
        assert stats["distinct_models"] == 4
        assert 0.0 < stats["cache_read_share"] < 1.0


class TestFormatAchievements:
    """Tests for the plain-text report."""

    def test_unlocked_shows_medal_and_progress(self):
        (status,) = evaluate_achievements({"n": 50}, [_COUNTER])
        text = format_achievements([status])
        assert "🥉 🧪 Test — bronze" in text
        assert "50 things" in text
        assert "next: 🥈 silver at 100 things" in text
        assert "█" in text and "░" in text

    def test_maxed_shows_no_bar(self):
        (status,) = evaluate_achievements({"n": 5000}, [_COUNTER])
        text = format_achievements([status])
        assert "all tiers unlocked" in text
        assert "░" not in text

    def test_locked_shows_hint(self):
        (status,) = evaluate_achievements({"n": 0}, [_COUNTER])
        text = format_achievements([status])
        assert "🔒 🧪 Test" in text
        assert "bronze at 10 things" in text
        assert "Do more test things." in text

    def test_score_line(self):
        (status,) = evaluate_achievements({"n": 500}, [_COUNTER])
        text = format_achievements([status])
        assert text.strip().endswith("Score: 2/3 tiers unlocked")

    def test_empty_data_score_is_zero(self):
        result = scan_directory(Path("/nonexistent/path"))
        statuses = evaluate_achievements(compute_achievement_stats(result))
        text = format_achievements(statuses)
        assert f"Score: 0/{(len(ACHIEVEMENTS) - 1) * 3} tiers unlocked" in text

    def test_plain_text_no_ansi(self):
        result = scan_directory(Path("tests/fixtures"))
        statuses = evaluate_achievements(compute_achievement_stats(result))
        assert "\x1b" not in format_achievements(statuses)


class TestCLIAchievements:
    """Tests for the 'achievements' CLI command."""

    def test_command_runs(self, capsys):
        result = main(["--data-dir", "tests/fixtures", "achievements"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Achievements" in captured.out
        assert "Score:" in captured.out

    def test_respects_date_filters(self, capsys):
        """--since past all fixture data leaves everything locked."""
        main(["--data-dir", "tests/fixtures", "--since", "2030-01-01", "achievements"])
        captured = capsys.readouterr()
        assert "Score: 0/" in captured.out

    def test_nonexistent_data_dir(self, capsys):
        result = main(["--data-dir", "/nonexistent/path", "achievements"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Score: 0/" in captured.out
