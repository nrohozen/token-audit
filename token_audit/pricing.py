import tomllib
from pathlib import Path
from typing import Optional

_BUNDLED_PRICES = Path(__file__).parent / "prices.toml"
_USER_PRICES = Path.home() / ".config" / "token-audit" / "prices.toml"


def _find_default_prices() -> Path:
    if _USER_PRICES.exists():
        return _USER_PRICES
    return _BUNDLED_PRICES


class PricingTable:
    def __init__(self, path: Optional[Path] = None):
        if path is None:
            path = _find_default_prices()
        self._path = path
        self._models: dict[str, dict[str, float]] = {}
        self._fallback: Optional[dict[str, float]] = None
        self._load(path)

    def _load(self, path: Path) -> None:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)

        for model, prices in (data.get("models") or {}).items():
            if isinstance(prices, dict):
                self._models[model] = {
                    "input": float(prices.get("input_per_mtok") or 0),
                    "output": float(prices.get("output_per_mtok") or 0),
                    "cache_write": float(prices.get("cache_write_per_mtok") or 0),
                    "cache_read": float(prices.get("cache_read_per_mtok") or 0),
                }

        fallback = data.get("unknown_model_fallback")
        if fallback and isinstance(fallback, dict):
            self._fallback = {
                "input": float(fallback.get("input_per_mtok") or 0),
                "output": float(fallback.get("output_per_mtok") or 0),
                "cache_write": float(fallback.get("cache_write_per_mtok") or 0),
                "cache_read": float(fallback.get("cache_read_per_mtok") or 0),
            }

    def get_prices(self, model: str) -> Optional[dict[str, float]]:
        if model in self._models:
            return self._models[model]
        return self._fallback

    def compute_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation_tokens: int,
        cache_read_tokens: int,
    ) -> Optional[float]:
        prices = self.get_prices(model)
        if prices is None:
            return None
        return (
            input_tokens * prices["input"] / 1_000_000
            + output_tokens * prices["output"] / 1_000_000
            + cache_creation_tokens * prices["cache_write"] / 1_000_000
            + cache_read_tokens * prices["cache_read"] / 1_000_000
        )
