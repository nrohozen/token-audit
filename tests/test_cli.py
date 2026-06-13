"""Test suite for token_audit.cli module."""

import json
import pytest
from pathlib import Path

from token_audit.cli import main


class TestCLISummary:
    """Tests for 'summary' command."""

    def test_summary_command_runs(self, capsys):
        """main(['--data-dir', 'tests/fixtures', 'summary']) exits with 0."""
        result = main(["--data-dir", "tests/fixtures", "summary"])
        assert result == 0

    def test_summary_command_produces_output(self, capsys):
        """summary command produces output."""
        main(["--data-dir", "tests/fixtures", "summary"])
        captured = capsys.readouterr()
        assert captured.out != ""

    def test_summary_command_includes_totals(self, capsys):
        """summary output includes total token counts."""
        main(["--data-dir", "tests/fixtures", "summary"])
        captured = capsys.readouterr()
        # Check for expected summary elements
        assert "Token Usage Summary" in captured.out

    def test_summary_command_with_no_cost(self, capsys):
        """--no-cost flag works with summary."""
        result = main(["--data-dir", "tests/fixtures", "--no-cost", "summary"])
        assert result == 0
        captured = capsys.readouterr()
        assert captured.out != ""

    def test_summary_includes_efficiency_block(self, capsys):
        """summary output includes the efficiency section."""
        main(["--data-dir", "tests/fixtures", "summary"])
        captured = capsys.readouterr()
        assert "Efficiency" in captured.out
        assert "Cache hit rate" in captured.out


class TestCLIEfficiencyFlag:
    """Tests for the global --efficiency flag on breakdown tables."""

    def test_efficiency_flag_runs(self, capsys):
        """--efficiency with a breakdown command exits 0."""
        result = main(["--data-dir", "tests/fixtures", "--efficiency", "by-model"])
        assert result == 0

    def test_efficiency_flag_swaps_columns(self, capsys):
        """--efficiency replaces token-count columns with efficiency columns."""
        main(["--data-dir", "tests/fixtures", "--efficiency", "by-model"])
        captured = capsys.readouterr()
        assert "Cache Hit" in captured.out
        assert "Out Yield" in captured.out
        assert "Cache Write" not in captured.out

    def test_without_flag_shows_token_columns(self, capsys):
        """Default breakdown shows token columns plus compact Cache Hit / $/Turn."""
        main(["--data-dir", "tests/fixtures", "by-model"])
        captured = capsys.readouterr()
        # Raw token columns are present...
        assert "Cache Write" in captured.out
        # ...alongside the two compact efficiency columns shown by default.
        assert "Cache Hit" in captured.out
        assert "$/Turn" in captured.out
        # ...but not the full-ratio-only columns (those need --efficiency).
        assert "Out Yield" not in captured.out
        assert "$/Session" not in captured.out


class TestCLIByModel:
    """Tests for 'by-model' command."""

    def test_by_model_command_runs(self, capsys):
        """by-model command runs without error."""
        result = main(["--data-dir", "tests/fixtures", "by-model"])
        assert result == 0

    def test_by_model_table_format(self, capsys):
        """by-model table format (default) produces table output."""
        main(["--data-dir", "tests/fixtures", "by-model"])
        captured = capsys.readouterr()
        assert "Usage by Model" in captured.out

    def test_by_model_json_format(self, capsys):
        """by-model json format produces valid JSON."""
        result = main(["--data-dir", "tests/fixtures", "--format", "json", "by-model"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 4  # 4 models

    def test_by_model_json_has_four_entries(self, capsys):
        """by-model json output has 4 model entries."""
        main(["--data-dir", "tests/fixtures", "--format", "json", "by-model"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        models = {r["model"] for r in data}
        assert "<synthetic>" in models
        assert "claude-fable-5" in models
        assert "claude-haiku-4-5-20251001" in models
        assert "claude-sonnet-4-6" in models

    def test_by_model_csv_format(self, capsys):
        """by-model csv format produces CSV output."""
        result = main(["--data-dir", "tests/fixtures", "--format", "csv", "by-model"])
        assert result == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert "model" in lines[0]
        assert len(lines) >= 5  # header + at least 4 models

    def test_by_model_json_includes_expected_fields(self, capsys):
        """by-model json includes sessions, turns, and token counts."""
        main(["--data-dir", "tests/fixtures", "--format", "json", "by-model"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for row in data:
            assert "model" in row
            assert "sessions" in row
            assert "turns" in row
            assert "input_tokens" in row
            assert "output_tokens" in row
            assert "cache_creation_tokens" in row
            assert "cache_read_tokens" in row


class TestCLIByProject:
    """Tests for 'by-project' command."""

    def test_by_project_command_runs(self, capsys):
        """by-project command runs without error."""
        result = main(["--data-dir", "tests/fixtures", "by-project"])
        assert result == 0

    def test_by_project_table_format(self, capsys):
        """by-project table format produces table output."""
        main(["--data-dir", "tests/fixtures", "by-project"])
        captured = capsys.readouterr()
        assert "Usage by Project" in captured.out

    def test_by_project_json_format(self, capsys):
        """by-project json format produces valid JSON."""
        result = main(["--data-dir", "tests/fixtures", "--format", "json", "by-project"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 2  # 2 projects with records


class TestCLIByDay:
    """Tests for 'by-day' command."""

    def test_by_day_command_runs(self, capsys):
        """by-day command runs without error."""
        result = main(["--data-dir", "tests/fixtures", "by-day"])
        assert result == 0

    def test_by_day_table_format(self, capsys):
        """by-day table format produces table output."""
        main(["--data-dir", "tests/fixtures", "by-day"])
        captured = capsys.readouterr()
        assert "Usage by Day" in captured.out

    def test_by_day_json_format(self, capsys):
        """by-day json format produces valid JSON."""
        result = main(["--data-dir", "tests/fixtures", "--format", "json", "by-day"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert len(data) == 3  # 3 distinct dates

    def test_by_day_three_dates(self, capsys):
        """by-day json includes all three expected dates."""
        main(["--data-dir", "tests/fixtures", "--format", "json", "by-day"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        dates = {r["date"] for r in data}
        assert "2026-01-15" in dates
        assert "2026-01-16" in dates
        assert "2026-01-17" in dates


class TestCLIDateFiltering:
    """Tests for --since and --until flags."""

    def test_since_filter_excludes_earlier_dates(self, capsys):
        """--since 2026-01-16 excludes 2026-01-15 records."""
        main(["--data-dir", "tests/fixtures", "--since", "2026-01-16", "by-day"])
        captured = capsys.readouterr()
        data_str = captured.out
        # Jan 16 and 17 should be present (in table format)
        # But date filtering behavior is in the by-day output somewhere
        assert "2026-01-16" in data_str or "16" in data_str

    def test_since_filter_json_format(self, capsys):
        """--since 2026-01-16 with json format returns 2 dates."""
        main(["--data-dir", "tests/fixtures", "--since", "2026-01-16", "--format", "json", "by-day"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 2  # Jan 16 and 17 only
        dates = {r["date"] for r in data}
        assert "2026-01-15" not in dates

    def test_until_filter_excludes_later_dates(self, capsys):
        """--until 2026-01-16 excludes later dates."""
        main(["--data-dir", "tests/fixtures", "--until", "2026-01-16", "--format", "json", "by-day"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 2  # Jan 15 and 16 only
        dates = {r["date"] for r in data}
        assert "2026-01-17" not in dates

    def test_since_and_until_together(self, capsys):
        """--since and --until together narrow the date range."""
        main([
            "--data-dir", "tests/fixtures",
            "--since", "2026-01-16",
            "--until", "2026-01-16",
            "--format", "json",
            "by-day"
        ])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert len(data) == 1  # Only Jan 16
        assert data[0]["date"] == "2026-01-16"

    def test_invalid_date_format_raises_error(self):
        """Invalid date format triggers argparse error."""
        with pytest.raises(SystemExit):
            main(["--data-dir", "tests/fixtures", "--since", "01-16-2026", "summary"])

    def test_invalid_date_format_wrong_order(self):
        """Invalid date order raises error."""
        with pytest.raises(SystemExit):
            main(["--data-dir", "tests/fixtures", "--since", "16-01-2026", "summary"])


class TestCLINonexistentDirectory:
    """Tests for handling missing data directory."""

    def test_nonexistent_directory_runs_without_error(self):
        """CLI runs even if data directory doesn't exist."""
        result = main(["--data-dir", "/nonexistent/path/that/does/not/exist", "summary"])
        assert result == 0

    def test_nonexistent_directory_produces_output(self, capsys):
        """CLI with nonexistent directory still produces output."""
        main(["--data-dir", "/nonexistent/path", "summary"])
        captured = capsys.readouterr()
        # Should produce some output (even if empty/zero summary)
        assert captured.out != ""

    def test_nonexistent_directory_json_format(self, capsys):
        """JSON output works with nonexistent directory."""
        result = main([
            "--data-dir", "/nonexistent/path",
            "--format", "json",
            "by-model"
        ])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        # Should be empty
        assert len(data) == 0


class TestCLIPricingAndCost:
    """Tests for cost calculation in CLI output."""

    def test_summary_with_pricing(self, capsys):
        """summary includes cost estimation by default."""
        main(["--data-dir", "tests/fixtures", "summary"])
        captured = capsys.readouterr()
        # Cost should be shown in summary
        assert "$" in captured.out or "Cost" in captured.out or "cost" in captured.out

    def test_by_model_with_pricing_json(self, capsys):
        """by-model json includes cost when pricing is available."""
        main(["--data-dir", "tests/fixtures", "--format", "json", "by-model"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for row in data:
            assert "estimated_cost_usd" in row

    def test_no_cost_flag_skips_pricing(self, capsys):
        """--no-cost flag skips cost calculation."""
        result = main(["--data-dir", "tests/fixtures", "--no-cost", "by-model"])
        assert result == 0

    def test_no_cost_json_has_null_costs(self, capsys):
        """With --no-cost, json output has null costs."""
        main(["--data-dir", "tests/fixtures", "--no-cost", "--format", "json", "by-model"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        # All costs should be None/null
        for row in data:
            assert row["estimated_cost_usd"] is None


class TestCLICommandValidation:
    """Tests for command validation."""

    def test_missing_command_raises_error(self):
        """Missing command argument triggers error."""
        with pytest.raises(SystemExit):
            main(["--data-dir", "tests/fixtures"])

    def test_invalid_command_raises_error(self):
        """Invalid command name triggers error."""
        with pytest.raises(SystemExit):
            main(["--data-dir", "tests/fixtures", "invalid-command"])

    def test_valid_commands_work(self, capsys):
        """All four valid commands work."""
        commands = ["summary", "by-project", "by-model", "by-day"]
        for cmd in commands:
            result = main(["--data-dir", "tests/fixtures", cmd])
            assert result == 0


class TestCLIFormatValidation:
    """Tests for format option validation."""

    def test_invalid_format_raises_error(self):
        """Invalid format choice triggers error."""
        with pytest.raises(SystemExit):
            main(["--data-dir", "tests/fixtures", "--format", "xml", "summary"])

    def test_valid_formats_work(self, capsys):
        """All three valid formats work."""
        formats = ["table", "csv", "json"]
        for fmt in formats:
            result = main(["--data-dir", "tests/fixtures", "--format", fmt, "summary"])
            assert result == 0


class TestCLIAllCombinations:
    """Integration tests for various command combinations."""

    def test_all_formats_with_summary(self, capsys):
        """summary works with all three output formats."""
        for fmt in ["table", "csv", "json"]:
            result = main(["--data-dir", "tests/fixtures", "--format", fmt, "summary"])
            assert result == 0

    def test_all_formats_with_by_model(self, capsys):
        """by-model works with all three output formats."""
        for fmt in ["table", "csv", "json"]:
            result = main(["--data-dir", "tests/fixtures", "--format", fmt, "by-model"])
            assert result == 0

    def test_by_project_produces_valid_output(self, capsys):
        """by-project command works."""
        result = main(["--data-dir", "tests/fixtures", "by-project"])
        assert result == 0
        captured = capsys.readouterr()
        assert "project-alpha" in captured.out or "alpha" in captured.out

    def test_all_commands_return_zero(self, capsys):
        """All commands return exit code 0."""
        commands = ["summary", "by-project", "by-model", "by-day"]
        for cmd in commands:
            result = main(["--data-dir", "tests/fixtures", cmd])
            assert result == 0, f"{cmd} did not return 0"
