"""Test suite for token_audit.wrapped module and the 'wrapped' CLI command."""

import json
from pathlib import Path

from token_audit.cli import main
from token_audit.pricing import PricingTable
from token_audit.scanner import scan_directory, scan_file
from token_audit.wrapped import (
    _decode_project_dir,
    compute_wrapped_stats,
    render_wrapped_html,
)


def _fixture_stats():
    result = scan_directory(Path("tests/fixtures"))
    return compute_wrapped_stats(result, PricingTable())


class TestComputeWrappedStats:
    """Tests for compute_wrapped_stats on the shared fixtures."""

    def test_totals_match_fixture_sums(self):
        """Token totals equal the known fixture sums."""
        stats = _fixture_stats()
        assert stats["input"] == 26800
        assert stats["output"] == 5200
        assert stats["cache_write"] == 11250
        assert stats["cache_read"] == 19000
        assert stats["total"] == 62250

    def test_turns_and_projects(self):
        """12 turns across 2 projects with records."""
        stats = _fixture_stats()
        assert stats["turns"] == 12
        assert stats["projects"] == 2

    def test_cost_is_positive(self):
        """Cost estimation yields a positive number for the fixtures."""
        stats = _fixture_stats()
        assert stats["cost"] is not None
        assert stats["cost"] > 0

    def test_cache_hit_rate_in_range(self):
        """Cache hit rate is a sane ratio."""
        stats = _fixture_stats()
        assert 0.0 < stats["cache_hit_rate"] < 1.0

    def test_cache_saved_positive(self):
        """Cache reads translate into positive estimated savings."""
        stats = _fixture_stats()
        assert stats["cache_saved"] is not None
        assert stats["cache_saved"] > 0

    def test_no_tools_archetype(self):
        """Fixtures contain no tool_use blocks -> Conversationalist."""
        stats = _fixture_stats()
        assert stats["top_tools"] == []
        assert stats["archetype"][0] == "The Conversationalist"

    def test_date_range_covers_fixture_days(self):
        """Date range spans the fixture timestamps."""
        stats = _fixture_stats()
        lo, hi = stats["date_range"]
        assert lo <= hi

    def test_model_mix_shares_sum_to_one(self):
        """Model-mix shares sum to ~1.0."""
        stats = _fixture_stats()
        assert abs(sum(share for _, _, share in stats["model_mix"]) - 1.0) < 1e-9

    def test_hour_turns_has_24_buckets(self):
        """Hour histogram always has 24 buckets summing to the turn count."""
        stats = _fixture_stats()
        assert len(stats["hour_turns"]) == 24
        assert sum(stats["hour_turns"]) == stats["turns"]

    def test_no_cost_mode(self):
        """Without pricing, cost and savings are None but stats still work."""
        result = scan_directory(Path("tests/fixtures"))
        stats = compute_wrapped_stats(result, None)
        assert stats["cost"] is None
        assert stats["cache_saved"] is None
        assert stats["total"] == 62250

    def test_empty_result(self):
        """An empty scan produces zeroed stats without crashing."""
        result = scan_directory(Path("/nonexistent/path"))
        stats = compute_wrapped_stats(result, PricingTable())
        assert stats["total"] == 0
        assert stats["date_range"] is None
        assert stats["awards"] == []


class TestScannerToolCapture:
    """Tests for tool_use / cwd capture added for wrapped."""

    def test_scan_file_captures_tool_names(self, tmp_path):
        """tool_use content blocks are collected per record."""
        line = {
            "type": "assistant",
            "timestamp": "2026-01-15T10:30:00.000Z",
            "sessionId": "s1",
            "cwd": "C:\\work\\demo",
            "message": {
                "model": "claude-sonnet-4-6",
                "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "tool_use", "name": "Bash", "input": {}},
                    {"type": "tool_use", "name": "Edit", "input": {}},
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }
        path = tmp_path / "session.jsonl"
        path.write_text(json.dumps(line) + "\n", encoding="utf-8")
        records, skipped = scan_file(path, "demo-project")
        assert skipped == 0
        assert records[0].tool_names == ["Bash", "Edit"]
        assert records[0].cwd == "C:\\work\\demo"

    def test_fixtures_have_no_tool_names(self):
        """Existing fixtures (text-only content) yield empty tool lists."""
        result = scan_directory(Path("tests/fixtures"))
        assert all(r.tool_names == [] for r in result.records)


class TestDecodeProjectDir:
    """Tests for the fallback project-directory decoder."""

    def test_windows_style(self):
        assert _decode_project_dir("C--Users-me-repo") == "C:\\Users\\me\\repo"

    def test_posix_style(self):
        assert _decode_project_dir("-home-me-repo") == "/home/me/repo"

    def test_plain_name_passthrough(self):
        assert _decode_project_dir("project-alpha") == "project-alpha"


class TestRenderWrappedHtml:
    """Tests for the HTML renderer."""

    def test_renders_single_document(self):
        """Output is one self-contained HTML document."""
        html_text = render_wrapped_html(_fixture_stats())
        assert html_text.startswith("<!DOCTYPE html>")
        assert "Claude Code Wrapped" in html_text
        assert "no telemetry" in html_text

    def test_no_external_requests(self):
        """No external URLs are referenced anywhere in the page."""
        html_text = render_wrapped_html(_fixture_stats())
        assert "http://" not in html_text
        assert "https://" not in html_text

    def test_escapes_project_names(self, tmp_path):
        """User-derived strings (cwd/project) are HTML-escaped."""
        line = {
            "type": "assistant",
            "timestamp": "2026-01-15T10:30:00.000Z",
            "sessionId": "s1",
            "cwd": "C:\\evil\\<script>alert(1)</script>",
            "message": {
                "model": "claude-sonnet-4-6",
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "s.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
        result = scan_directory(tmp_path)
        html_text = render_wrapped_html(compute_wrapped_stats(result, None))
        assert "<script>alert(1)</script>" not in html_text
        assert "&lt;script&gt;" in html_text

    def test_renders_empty_stats(self):
        """A page still renders when there is no data at all."""
        result = scan_directory(Path("/nonexistent/path"))
        html_text = render_wrapped_html(compute_wrapped_stats(result, None))
        assert "no transcripts found" in html_text


class TestWrappedAchievements:
    """Tests for the achievements section of the wrapped page."""

    def test_stats_include_achievement_statuses(self):
        """compute_wrapped_stats carries evaluated achievement statuses."""
        stats = _fixture_stats()
        assert stats["achievements"]
        assert all(hasattr(s, "tier") for s in stats["achievements"])

    def test_section_renders_with_score_line(self):
        """The Achievements card renders with the tiers-unlocked score."""
        html_text = render_wrapped_html(_fixture_stats())
        assert "Achievements" in html_text
        assert "tiers unlocked" in html_text

    def test_score_matches_evaluated_tiers(self):
        """The rendered score equals the sum of earned tiers."""
        stats = _fixture_stats()
        earned = sum(s.tier for s in stats["achievements"])
        total = sum(len(s.achievement.tiers) for s in stats["achievements"])
        assert f"{earned}/{total} tiers unlocked" in render_wrapped_html(stats)

    def test_locked_achievements_are_dimmed(self):
        """Fixture data leaves some achievements locked, rendered dimmed."""
        stats = _fixture_stats()
        assert any(s.tier == 0 for s in stats["achievements"])
        html_text = render_wrapped_html(stats)
        assert 'class="locked"' in html_text
        assert "🔒" in html_text

    def test_unlocked_achievement_shows_medal_and_bar(self):
        """Fixture data unlocks at least one tier with a medal and CSS bar."""
        stats = _fixture_stats()
        assert any(s.tier > 0 for s in stats["achievements"])
        html_text = render_wrapped_html(stats)
        assert "🥉" in html_text or "🥈" in html_text or "🥇" in html_text
        assert 'class="bar"' in html_text

    def test_empty_result_still_renders(self):
        """An empty scan renders the section (everything locked) without error."""
        result = scan_directory(Path("/nonexistent/path"))
        stats = compute_wrapped_stats(result, None)
        html_text = render_wrapped_html(stats)
        assert "0/" in html_text
        assert "tiers unlocked" in html_text


class TestCLIWrapped:
    """Tests for the 'wrapped' CLI command."""

    def test_wrapped_writes_file_and_prints_path(self, tmp_path, capsys):
        """wrapped writes the HTML file and prints its path."""
        out = tmp_path / "wrapped.html"
        code = main(["--data-dir", "tests/fixtures", "wrapped", "-o", str(out)])
        assert code == 0
        assert out.exists()
        captured = capsys.readouterr()
        assert str(out) in captured.out
        assert "Claude Code Wrapped" in out.read_text(encoding="utf-8")

    def test_wrapped_respects_date_filters(self, tmp_path):
        """--since/--until narrow the data the page is built from."""
        out = tmp_path / "w.html"
        code = main([
            "--data-dir", "tests/fixtures",
            "--since", "2026-01-16", "--until", "2026-01-16",
            "wrapped", "-o", str(out),
        ])
        assert code == 0
        text = out.read_text(encoding="utf-8")
        # Only session-002 (3 haiku turns, 1,300 input tokens) is on Jan 16.
        assert "1,300" in text
        assert "claude-haiku-4-5-20251001" in text

    def test_wrapped_no_cost(self, tmp_path):
        """--no-cost still produces a page (cost shown as n/a)."""
        out = tmp_path / "w.html"
        code = main(["--data-dir", "tests/fixtures", "--no-cost", "wrapped", "-o", str(out)])
        assert code == 0
        assert "n/a" in out.read_text(encoding="utf-8")

    def test_wrapped_nonexistent_data_dir(self, tmp_path):
        """wrapped works even when the data directory is missing."""
        out = tmp_path / "w.html"
        code = main(["--data-dir", "/nonexistent/path", "wrapped", "-o", str(out)])
        assert code == 0
        assert out.exists()
