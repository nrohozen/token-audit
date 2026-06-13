"""Test suite for token_audit.pricing module."""

import pytest
import tempfile
from pathlib import Path

from token_audit.pricing import PricingTable


class TestPricingTableCostComputation:
    """Tests for PricingTable.compute_cost."""

    def test_compute_cost_sonnet(self):
        """Cost for claude-sonnet-4-6 is correctly calculated."""
        pricing = PricingTable()
        cost = pricing.compute_cost(
            "claude-sonnet-4-6",
            input_tokens=1000,
            output_tokens=200,
            cache_creation_tokens=500,
            cache_read_tokens=800,
        )
        expected = (
            1000 * 3.00 / 1e6
            + 200 * 15.00 / 1e6
            + 500 * 3.75 / 1e6
            + 800 * 0.30 / 1e6
        )
        assert cost == pytest.approx(expected, rel=1e-9)

    def test_compute_cost_haiku(self):
        """Cost for claude-haiku-4-5-20251001 is correctly calculated."""
        pricing = PricingTable()
        cost = pricing.compute_cost(
            "claude-haiku-4-5-20251001",
            input_tokens=500,
            output_tokens=100,
            cache_creation_tokens=0,
            cache_read_tokens=400,
        )
        expected = (
            500 * 0.80 / 1e6
            + 100 * 4.00 / 1e6
            + 0 * 1.00 / 1e6
            + 400 * 0.08 / 1e6
        )
        assert cost == pytest.approx(expected, rel=1e-9)

    def test_compute_cost_fable(self):
        """Cost for claude-fable-5 is correctly calculated."""
        pricing = PricingTable()
        cost = pricing.compute_cost(
            "claude-fable-5",
            input_tokens=5000,
            output_tokens=1000,
            cache_creation_tokens=2500,
            cache_read_tokens=4000,
        )
        expected = (
            5000 * 3.00 / 1e6
            + 1000 * 15.00 / 1e6
            + 2500 * 3.75 / 1e6
            + 4000 * 0.30 / 1e6
        )
        assert cost == pytest.approx(expected, rel=1e-9)

    def test_compute_cost_synthetic_is_zero(self):
        """Cost for <synthetic> model is exactly 0.0."""
        pricing = PricingTable()
        cost = pricing.compute_cost(
            "<synthetic>",
            input_tokens=1000,
            output_tokens=200,
            cache_creation_tokens=500,
            cache_read_tokens=800,
        )
        assert cost == 0.0

    def test_compute_cost_zero_tokens(self):
        """Cost with all zero tokens is 0.0."""
        pricing = PricingTable()
        cost = pricing.compute_cost(
            "claude-sonnet-4-6",
            input_tokens=0,
            output_tokens=0,
            cache_creation_tokens=0,
            cache_read_tokens=0,
        )
        assert cost == 0.0

    def test_compute_cost_unknown_model_uses_fallback(self):
        """Unknown model uses fallback pricing (sonnet-equivalent)."""
        pricing = PricingTable()
        cost = pricing.compute_cost(
            "some-unknown-model",
            input_tokens=1000,
            output_tokens=100,
            cache_creation_tokens=0,
            cache_read_tokens=0,
        )
        expected = (
            1000 * 3.00 / 1e6
            + 100 * 15.00 / 1e6
        )
        assert cost == pytest.approx(expected, rel=1e-9)


class TestPricingTableGetPrices:
    """Tests for PricingTable.get_prices."""

    def test_get_prices_sonnet(self):
        """get_prices returns correct dict for claude-sonnet-4-6."""
        pricing = PricingTable()
        prices = pricing.get_prices("claude-sonnet-4-6")
        assert prices is not None
        assert prices["input"] == 3.00
        assert prices["output"] == 15.00
        assert prices["cache_write"] == 3.75
        assert prices["cache_read"] == 0.30

    def test_get_prices_haiku(self):
        """get_prices returns correct dict for claude-haiku-4-5-20251001."""
        pricing = PricingTable()
        prices = pricing.get_prices("claude-haiku-4-5-20251001")
        assert prices is not None
        assert prices["input"] == 0.80
        assert prices["output"] == 4.00
        assert prices["cache_write"] == 1.00
        assert prices["cache_read"] == 0.08

    def test_get_prices_unknown_model(self):
        """get_prices returns fallback for unknown model."""
        pricing = PricingTable()
        prices = pricing.get_prices("some-unknown-model")
        assert prices is not None
        assert prices["input"] == 3.00
        assert prices["output"] == 15.00

    def test_get_prices_synthetic(self):
        """get_prices returns zero prices for <synthetic> model."""
        pricing = PricingTable()
        prices = pricing.get_prices("<synthetic>")
        assert prices is not None
        assert prices["input"] == 0.0
        assert prices["output"] == 0.0
        assert prices["cache_write"] == 0.0
        assert prices["cache_read"] == 0.0


class TestPricingTableCustomFile:
    """Tests for loading custom prices.toml."""

    def test_load_custom_prices_file(self):
        """Can load a custom prices.toml file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("""
version = "1"

[models."test-model"]
input_per_mtok = 10.00
output_per_mtok = 50.00
cache_write_per_mtok = 12.50
cache_read_per_mtok = 1.00

[unknown_model_fallback]
input_per_mtok = 10.00
output_per_mtok = 50.00
cache_write_per_mtok = 12.50
cache_read_per_mtok = 1.00
""")
            f.flush()
            pricing = PricingTable(Path(f.name))
            cost = pricing.compute_cost(
                "test-model",
                input_tokens=1000,
                output_tokens=100,
                cache_creation_tokens=0,
                cache_read_tokens=0,
            )
            expected = (
                1000 * 10.00 / 1e6
                + 100 * 50.00 / 1e6
            )
            assert cost == pytest.approx(expected, rel=1e-9)

    def test_load_custom_prices_changes_cost(self):
        """Custom pricing produces different costs than defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write("""
version = "1"

[models."claude-sonnet-4-6"]
input_per_mtok = 1.00
output_per_mtok = 5.00
cache_write_per_mtok = 1.25
cache_read_per_mtok = 0.10

[unknown_model_fallback]
input_per_mtok = 1.00
output_per_mtok = 5.00
cache_write_per_mtok = 1.25
cache_read_per_mtok = 0.10
""")
            f.flush()
            pricing = PricingTable(Path(f.name))
            cost = pricing.compute_cost(
                "claude-sonnet-4-6",
                input_tokens=1000,
                output_tokens=200,
                cache_creation_tokens=0,
                cache_read_tokens=0,
            )
            expected = (
                1000 * 1.00 / 1e6
                + 200 * 5.00 / 1e6
            )
            assert cost == pytest.approx(expected, rel=1e-9)


class TestPricingTableEdgeCases:
    """Tests for edge cases and error handling."""

    def test_compute_cost_with_large_numbers(self):
        """compute_cost handles large token counts correctly."""
        pricing = PricingTable()
        cost = pricing.compute_cost(
            "claude-sonnet-4-6",
            input_tokens=1_000_000,
            output_tokens=500_000,
            cache_creation_tokens=250_000,
            cache_read_tokens=100_000,
        )
        expected = (
            1_000_000 * 3.00 / 1e6
            + 500_000 * 15.00 / 1e6
            + 250_000 * 3.75 / 1e6
            + 100_000 * 0.30 / 1e6
        )
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_pricing_table_initialization_with_none_path(self):
        """PricingTable(None) loads default prices successfully."""
        pricing = PricingTable(None)
        prices = pricing.get_prices("claude-sonnet-4-6")
        assert prices is not None
        assert "input" in prices

    def test_all_bundled_models_have_prices(self):
        """All expected bundled models have pricing data."""
        pricing = PricingTable()
        models = [
            "claude-opus-4-8",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            "claude-fable-5",
            "<synthetic>",
        ]
        for model in models:
            prices = pricing.get_prices(model)
            assert prices is not None
            assert prices["input"] is not None
            assert prices["output"] is not None
