"""Test suite for token_audit.report module."""

import csv
import json
import pytest
from pathlib import Path

from token_audit.scanner import scan_directory
from token_audit.pricing import PricingTable
from token_audit.report import (
    agg_summary,
    agg_by_project,
    agg_by_model,
    agg_by_day,
    AggRow,
    format_csv,
    format_json,
    format_table,
)


@pytest.fixture
def scan_result():
    """Fixture: scan all test fixtures."""
    return scan_directory(Path("tests/fixtures"))


@pytest.fixture
def pricing():
    """Fixture: load default pricing."""
    return PricingTable()


class TestAggSummary:
    """Tests for agg_summary function."""

    def test_agg_summary_returns_aggrow(self, scan_result):
        """agg_summary returns an AggRow object."""
        row = agg_summary(scan_result, None)
        assert isinstance(row, AggRow)

    def test_agg_summary_total_input_tokens(self, scan_result):
        """Total input tokens is 26800 (5800+1300+19700 from projects)."""
        row = agg_summary(scan_result, None)
        assert row.input_tokens == 26800

    def test_agg_summary_total_output_tokens(self, scan_result):
        """Total output tokens is 5200."""
        row = agg_summary(scan_result, None)
        assert row.output_tokens == 5200

    def test_agg_summary_total_cache_creation(self, scan_result):
        """Total cache creation tokens is 11250."""
        row = agg_summary(scan_result, None)
        assert row.cache_creation_tokens == 11250

    def test_agg_summary_total_cache_read(self, scan_result):
        """Total cache read tokens is 19000."""
        row = agg_summary(scan_result, None)
        assert row.cache_read_tokens == 19000

    def test_agg_summary_key_is_total(self, scan_result):
        """Summary row key is 'TOTAL'."""
        row = agg_summary(scan_result, None)
        assert row.key == "TOTAL"

    def test_agg_summary_with_pricing(self, scan_result, pricing):
        """agg_summary with pricing returns non-None cost."""
        row = agg_summary(scan_result, pricing)
        assert row.cost is not None
        assert row.cost > 0.0

    def test_agg_summary_cost_breakdown(self, scan_result, pricing):
        """agg_summary cost is reasonable based on token counts and pricing."""
        row = agg_summary(scan_result, pricing)
        assert row.cost is not None
        # Rough check: cost should be at least ~$0.02 (26800*3/1e6 for input alone)
        assert row.cost > 0.05


class TestAggByProject:
    """Tests for agg_by_project function."""

    def test_agg_by_project_returns_list(self, scan_result):
        """agg_by_project returns a list of AggRow."""
        rows = agg_by_project(scan_result, None)
        assert isinstance(rows, list)
        assert all(isinstance(r, AggRow) for r in rows)

    def test_agg_by_project_has_two_rows(self, scan_result):
        """agg_by_project returns 2 rows (alpha and beta; empty has no records)."""
        rows = agg_by_project(scan_result, None)
        assert len(rows) == 2

    def test_agg_by_project_keys_are_sorted(self, scan_result):
        """agg_by_project rows are sorted by key."""
        rows = agg_by_project(scan_result, None)
        keys = [r.key for r in rows]
        assert keys == sorted(keys)

    def test_agg_by_project_alpha_exists(self, scan_result):
        """project-alpha row exists in results."""
        rows = agg_by_project(scan_result, None)
        keys = {r.key for r in rows}
        assert "project-alpha" in keys

    def test_agg_by_project_beta_exists(self, scan_result):
        """project-beta row exists in results."""
        rows = agg_by_project(scan_result, None)
        keys = {r.key for r in rows}
        assert "project-beta" in keys

    def test_agg_by_project_alpha_tokens(self, scan_result):
        """project-alpha has correct token aggregates."""
        rows = agg_by_project(scan_result, None)
        alpha = next(r for r in rows if r.key == "project-alpha")
        assert alpha.input_tokens == 5800
        assert alpha.output_tokens == 1150
        assert alpha.cache_creation_tokens == 2250
        assert alpha.cache_read_tokens == 4600

    def test_agg_by_project_beta_tokens(self, scan_result):
        """project-beta has correct token aggregates."""
        rows = agg_by_project(scan_result, None)
        beta = next(r for r in rows if r.key == "project-beta")
        assert beta.input_tokens == 21000
        assert beta.output_tokens == 4050
        assert beta.cache_creation_tokens == 9000
        assert beta.cache_read_tokens == 14400

    def test_agg_by_project_sessions_counts(self, scan_result):
        """agg_by_project includes session count per project."""
        rows = agg_by_project(scan_result, None)
        for row in rows:
            assert row.sessions > 0

    def test_agg_by_project_turns_counts(self, scan_result):
        """agg_by_project includes turns (record count) per project."""
        rows = agg_by_project(scan_result, None)
        assert sum(r.turns for r in rows) == 12


class TestAggByModel:
    """Tests for agg_by_model function."""

    def test_agg_by_model_returns_list(self, scan_result):
        """agg_by_model returns a list of AggRow."""
        rows = agg_by_model(scan_result, None)
        assert isinstance(rows, list)
        assert all(isinstance(r, AggRow) for r in rows)

    def test_agg_by_model_has_four_models(self, scan_result):
        """agg_by_model returns 4 models (sonnet, haiku, fable, synthetic)."""
        rows = agg_by_model(scan_result, None)
        assert len(rows) == 4

    def test_agg_by_model_keys_are_sorted(self, scan_result):
        """agg_by_model rows are sorted by key."""
        rows = agg_by_model(scan_result, None)
        keys = [r.key for r in rows]
        assert keys == sorted(keys)

    def test_agg_by_model_includes_sonnet(self, scan_result):
        """claude-sonnet-4-6 model exists."""
        rows = agg_by_model(scan_result, None)
        keys = {r.key for r in rows}
        assert "claude-sonnet-4-6" in keys

    def test_agg_by_model_includes_haiku(self, scan_result):
        """claude-haiku-4-5-20251001 model exists."""
        rows = agg_by_model(scan_result, None)
        keys = {r.key for r in rows}
        assert "claude-haiku-4-5-20251001" in keys

    def test_agg_by_model_includes_fable(self, scan_result):
        """claude-fable-5 model exists."""
        rows = agg_by_model(scan_result, None)
        keys = {r.key for r in rows}
        assert "claude-fable-5" in keys

    def test_agg_by_model_includes_synthetic(self, scan_result):
        """<synthetic> model exists."""
        rows = agg_by_model(scan_result, None)
        keys = {r.key for r in rows}
        assert "<synthetic>" in keys

    def test_agg_by_model_sonnet_tokens(self, scan_result):
        """claude-sonnet-4-6 has correct token aggregates."""
        rows = agg_by_model(scan_result, None)
        sonnet = next(r for r in rows if r.key == "claude-sonnet-4-6")
        assert sonnet.input_tokens == 10000
        assert sonnet.output_tokens == 1850
        assert sonnet.cache_creation_tokens == 3500
        assert sonnet.cache_read_tokens == 5600

    def test_agg_by_model_haiku_tokens(self, scan_result):
        """claude-haiku-4-5-20251001 has correct token aggregates."""
        rows = agg_by_model(scan_result, None)
        haiku = next(r for r in rows if r.key == "claude-haiku-4-5-20251001")
        assert haiku.input_tokens == 1300
        assert haiku.output_tokens == 250
        assert haiku.cache_creation_tokens == 0
        assert haiku.cache_read_tokens == 1000

    def test_agg_by_model_fable_tokens(self, scan_result):
        """claude-fable-5 has correct token aggregates."""
        rows = agg_by_model(scan_result, None)
        fable = next(r for r in rows if r.key == "claude-fable-5")
        assert fable.input_tokens == 15500
        assert fable.output_tokens == 3100
        assert fable.cache_creation_tokens == 7750
        assert fable.cache_read_tokens == 12400

    def test_agg_by_model_synthetic_zero_tokens(self, scan_result):
        """<synthetic> model has all zero tokens."""
        rows = agg_by_model(scan_result, None)
        synthetic = next(r for r in rows if r.key == "<synthetic>")
        assert synthetic.input_tokens == 0
        assert synthetic.output_tokens == 0
        assert synthetic.cache_creation_tokens == 0
        assert synthetic.cache_read_tokens == 0

    def test_agg_by_model_haiku_cost(self, scan_result, pricing):
        """claude-haiku-4-5-20251001 cost calculation is correct."""
        rows = agg_by_model(scan_result, pricing)
        haiku = next(r for r in rows if r.key == "claude-haiku-4-5-20251001")
        assert haiku.cost is not None
        expected = (
            1300 * 1.00 / 1e6
            + 250 * 5.00 / 1e6
            + 0 * 1.25 / 1e6
            + 1000 * 0.10 / 1e6
        )
        assert haiku.cost == pytest.approx(expected, rel=1e-9)

    def test_agg_by_model_synthetic_cost_is_zero(self, scan_result, pricing):
        """<synthetic> model cost is exactly 0.0."""
        rows = agg_by_model(scan_result, pricing)
        synthetic = next(r for r in rows if r.key == "<synthetic>")
        assert synthetic.cost == 0.0


class TestAggByDay:
    """Tests for agg_by_day function."""

    def test_agg_by_day_returns_list(self, scan_result):
        """agg_by_day returns a list of AggRow."""
        rows = agg_by_day(scan_result, None)
        assert isinstance(rows, list)
        assert all(isinstance(r, AggRow) for r in rows)

    def test_agg_by_day_has_three_days(self, scan_result):
        """agg_by_day returns 3 rows (three distinct dates)."""
        rows = agg_by_day(scan_result, None)
        assert len(rows) == 3

    def test_agg_by_day_keys_are_sorted(self, scan_result):
        """agg_by_day rows are sorted chronologically."""
        rows = agg_by_day(scan_result, None)
        keys = [r.key for r in rows]
        assert keys == sorted(keys)

    def test_agg_by_day_includes_jan_15(self, scan_result):
        """2026-01-15 exists in results."""
        rows = agg_by_day(scan_result, None)
        keys = {r.key for r in rows}
        assert "2026-01-15" in keys

    def test_agg_by_day_includes_jan_16(self, scan_result):
        """2026-01-16 exists in results."""
        rows = agg_by_day(scan_result, None)
        keys = {r.key for r in rows}
        assert "2026-01-16" in keys

    def test_agg_by_day_includes_jan_17(self, scan_result):
        """2026-01-17 exists in results."""
        rows = agg_by_day(scan_result, None)
        keys = {r.key for r in rows}
        assert "2026-01-17" in keys

    def test_agg_by_day_jan_15_tokens(self, scan_result):
        """2026-01-15 has correct token aggregates."""
        rows = agg_by_day(scan_result, None)
        day = next(r for r in rows if r.key == "2026-01-15")
        assert day.input_tokens == 14000
        assert day.output_tokens == 2800
        assert day.cache_creation_tokens == 7000
        assert day.cache_read_tokens == 11200

    def test_agg_by_day_jan_16_tokens(self, scan_result):
        """2026-01-16 has correct token aggregates."""
        rows = agg_by_day(scan_result, None)
        day = next(r for r in rows if r.key == "2026-01-16")
        assert day.input_tokens == 1300
        assert day.output_tokens == 250
        assert day.cache_creation_tokens == 0
        assert day.cache_read_tokens == 1000

    def test_agg_by_day_jan_17_tokens(self, scan_result):
        """2026-01-17 has correct token aggregates."""
        rows = agg_by_day(scan_result, None)
        day = next(r for r in rows if r.key == "2026-01-17")
        assert day.input_tokens == 11500
        assert day.output_tokens == 2150
        assert day.cache_creation_tokens == 4250
        assert day.cache_read_tokens == 6800


class TestFormatCSV:
    """Tests for format_csv function."""

    def test_format_csv_returns_string(self, scan_result):
        """format_csv returns a string."""
        rows = agg_by_model(scan_result, None)
        output = format_csv(rows, "model")
        assert isinstance(output, str)

    def test_format_csv_valid_csv(self, scan_result):
        """format_csv output is valid CSV."""
        rows = agg_by_model(scan_result, None)
        output = format_csv(rows, "model")
        lines = output.strip().split("\n")
        assert len(lines) > 0
        reader = csv.DictReader(lines)
        rows_read = list(reader)
        assert len(rows_read) == 4

    def test_format_csv_has_expected_headers(self, scan_result):
        """format_csv output has expected column headers."""
        rows = agg_by_model(scan_result, None)
        output = format_csv(rows, "model")
        lines = output.strip().split("\n")
        header_line = lines[0]
        assert "model" in header_line
        assert "sessions" in header_line
        assert "input_tokens" in header_line
        assert "output_tokens" in header_line
        assert "estimated_cost_usd" in header_line

    def test_format_csv_empty_rows(self):
        """format_csv with empty list produces header only."""
        output = format_csv([], "key")
        lines = output.strip().split("\n")
        assert len(lines) == 1  # Just the header

    def test_format_csv_custom_key_label(self, scan_result):
        """format_csv respects custom key label parameter."""
        rows = agg_by_project(scan_result, None)
        output = format_csv(rows, "project")
        assert "project" in output.split("\n")[0]


class TestFormatJSON:
    """Tests for format_json function."""

    def test_format_json_returns_string(self, scan_result):
        """format_json returns a string."""
        rows = agg_by_model(scan_result, None)
        output = format_json(rows, "model")
        assert isinstance(output, str)

    def test_format_json_valid_json(self, scan_result):
        """format_json output is valid JSON."""
        rows = agg_by_model(scan_result, None)
        output = format_json(rows, "model")
        data = json.loads(output)
        assert isinstance(data, list)
        assert len(data) == 4

    def test_format_json_has_expected_fields(self, scan_result):
        """format_json output has expected fields."""
        rows = agg_by_model(scan_result, None)
        output = format_json(rows, "model")
        data = json.loads(output)
        assert len(data) > 0
        first = data[0]
        assert "model" in first
        assert "sessions" in first
        assert "input_tokens" in first
        assert "output_tokens" in first
        assert "estimated_cost_usd" in first

    def test_format_json_empty_rows(self):
        """format_json with empty list produces empty array."""
        output = format_json([], "key")
        data = json.loads(output)
        assert data == []

    def test_format_json_custom_key_label(self, scan_result):
        """format_json respects custom key label parameter."""
        rows = agg_by_project(scan_result, None)
        output = format_json(rows, "project")
        data = json.loads(output)
        assert "project" in data[0]


class TestFormatTable:
    """Tests for format_table function."""

    def test_format_table_returns_string(self, scan_result):
        """format_table returns a string."""
        rows = agg_by_model(scan_result, None)
        total = agg_summary(scan_result, None)
        output = format_table("Test Table", rows, total)
        assert isinstance(output, str)

    def test_format_table_includes_title(self, scan_result):
        """format_table output includes the title."""
        rows = agg_by_model(scan_result, None)
        total = agg_summary(scan_result, None)
        output = format_table("Usage Report", rows, total)
        assert "Usage Report" in output

    def test_format_table_includes_rows(self, scan_result):
        """format_table output includes row data."""
        rows = agg_by_model(scan_result, None)
        total = agg_summary(scan_result, None)
        output = format_table("Test", rows, total)
        for row in rows:
            assert row.key in output

    def test_format_table_includes_total(self, scan_result):
        """format_table output includes TOTAL row."""
        rows = agg_by_model(scan_result, None)
        total = agg_summary(scan_result, None)
        output = format_table("Test", rows, total)
        assert "TOTAL" in output

    def test_format_table_empty_rows(self):
        """format_table with empty rows returns gracefully."""
        output = format_table("Empty Test", [], None)
        assert isinstance(output, str)
        assert "Empty Test" in output

    def test_format_table_with_none_total(self, scan_result):
        """format_table with None total row works."""
        rows = agg_by_model(scan_result, None)
        output = format_table("Test", rows, None)
        assert isinstance(output, str)
        assert "TOTAL" not in output

    def test_format_table_efficiency_columns(self, scan_result):
        """format_table(efficiency=True) shows efficiency columns, not token counts."""
        rows = agg_by_model(scan_result, None)
        total = agg_summary(scan_result, None)
        output = format_table("Test", rows, total, "Model", efficiency=True)
        assert "Cache Hit" in output
        assert "Out Yield" in output
        assert "$/Turn" in output
        assert "$/Session" in output
        # Raw token-count headers should be absent in efficiency mode.
        assert "Cache Write" not in output


def _row(**kw) -> AggRow:
    """Build an AggRow with sensible defaults for property tests."""
    base = dict(
        key="k", sessions=1, turns=1,
        input_tokens=0, output_tokens=0,
        cache_creation_tokens=0, cache_read_tokens=0,
        cost=None,
    )
    base.update(kw)
    return AggRow(**base)


class TestEfficiencyProperties:
    """Tests for the derived efficiency properties on AggRow."""

    def test_cache_hit_rate_known(self):
        """cache_hit_rate = cache_read / (cache_read + cache_write + input)."""
        row = _row(input_tokens=100, cache_creation_tokens=300, cache_read_tokens=600)
        assert row.cache_hit_rate == pytest.approx(600 / 1000)

    def test_cache_hit_rate_zero_denominator_is_none(self):
        """No input-side tokens -> cache_hit_rate is None (no divide-by-zero)."""
        row = _row()
        assert row.cache_hit_rate is None

    def test_output_yield_known(self):
        """output_yield = output / (input + cache_write + cache_read)."""
        row = _row(
            input_tokens=100, output_tokens=50,
            cache_creation_tokens=300, cache_read_tokens=600,
        )
        assert row.output_yield == pytest.approx(50 / 1000)

    def test_output_yield_zero_denominator_is_none(self):
        """No input-side tokens -> output_yield is None."""
        row = _row(output_tokens=50)
        assert row.output_yield is None

    def test_cost_per_turn_known(self):
        """cost_per_turn = cost / turns."""
        row = _row(turns=4, cost=2.0)
        assert row.cost_per_turn == pytest.approx(0.5)

    def test_cost_per_turn_none_when_cost_none(self):
        """cost_per_turn is None when cost is unavailable."""
        row = _row(turns=4, cost=None)
        assert row.cost_per_turn is None

    def test_cost_per_turn_none_when_zero_turns(self):
        """cost_per_turn is None when there are no turns."""
        row = _row(turns=0, cost=2.0)
        assert row.cost_per_turn is None

    def test_cost_per_session_known(self):
        """cost_per_session = cost / sessions."""
        row = _row(sessions=2, cost=5.0)
        assert row.cost_per_session == pytest.approx(2.5)

    def test_cost_per_session_none_when_cost_none(self):
        """cost_per_session is None when cost is unavailable."""
        row = _row(sessions=2, cost=None)
        assert row.cost_per_session is None

    def test_cost_per_session_none_when_zero_sessions(self):
        """cost_per_session is None when there are no sessions."""
        row = _row(sessions=0, cost=5.0)
        assert row.cost_per_session is None

    def test_synthetic_zero_token_model_rates_are_none(self, scan_result):
        """The all-zero <synthetic> model yields None rates from real aggregation."""
        rows = agg_by_model(scan_result, None)
        synthetic = next(r for r in rows if r.key == "<synthetic>")
        assert synthetic.cache_hit_rate is None
        assert synthetic.output_yield is None


class TestEfficiencyInSerialization:
    """Efficiency fields are always present in CSV/JSON output."""

    def test_csv_includes_efficiency_headers(self, scan_result):
        rows = agg_by_model(scan_result, None)
        header = format_csv(rows, "model").split("\n")[0]
        for col in ("cache_hit_rate", "output_yield",
                    "cost_per_turn_usd", "cost_per_session_usd"):
            assert col in header

    def test_csv_empty_value_when_rate_undefined(self, scan_result):
        """Undefined rate (synthetic model) serializes as empty CSV cell, not '0'."""
        rows = agg_by_model(scan_result, None)
        output = format_csv(rows, "model")
        reader = csv.DictReader(output.strip().split("\n"))
        synthetic = next(r for r in reader if r["model"] == "<synthetic>")
        assert synthetic["cache_hit_rate"] == ""
        assert synthetic["output_yield"] == ""

    def test_json_includes_efficiency_fields(self, scan_result, pricing):
        rows = agg_by_model(scan_result, pricing)
        data = json.loads(format_json(rows, "model"))
        for entry in data:
            assert "cache_hit_rate" in entry
            assert "output_yield" in entry
            assert "cost_per_turn_usd" in entry
            assert "cost_per_session_usd" in entry

    def test_json_null_when_rate_undefined(self, scan_result):
        """Undefined rate serializes as JSON null."""
        rows = agg_by_model(scan_result, None)
        data = json.loads(format_json(rows, "model"))
        synthetic = next(e for e in data if e["model"] == "<synthetic>")
        assert synthetic["cache_hit_rate"] is None
        assert synthetic["output_yield"] is None
