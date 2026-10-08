import json

import pytest

from arena.pricing import cost, load_prices
from arena.task import make_task

USAGE = {
    "input_tokens": 1_000_000,
    "input_tokens_details": {"cached_tokens": 500_000},
    "output_tokens": 200_000,
}


class SdkUsage:
    """Stands in for the openai SDK's usage object."""

    def model_dump(self):
        return USAGE


def test_cost():
    price = {"input": 0.1, "output": 0.5, "cached_input": 0.01}
    assert cost(USAGE, price) == pytest.approx(0.05 + 0.005 + 0.1)
    assert cost(SdkUsage(), price) == cost(USAGE, price)
    assert cost(USAGE, {"input": 0.1, "output": 0.5}) == pytest.approx(0.1 + 0.1)  # cached = input
    assert cost(None, price) == 0


LUNA = load_prices()["gpt-6-luna"]


def test_cache_writes_are_priced_separately():
    usage = {
        "input_tokens": 100_000,
        "input_tokens_details": {"cached_tokens": 40_000, "cache_write_tokens": 50_000},
        "output_tokens": 10_000,
    }
    # 10k uncached at 0.1, 40k cached at 0.01, 50k written at 0.125, 10k out at 0.5
    expected = (10_000 * 0.1 + 40_000 * 0.01 + 50_000 * 0.125 + 10_000 * 0.5) / 1e6
    assert cost(usage, LUNA) == pytest.approx(expected)


def test_long_context_prices_the_whole_call():
    above = LUNA["long_context"]["above_input_tokens"]
    at = {"input_tokens": above, "output_tokens": 1_000}
    over = {"input_tokens": above + 1, "output_tokens": 1_000}
    assert cost(at, LUNA) == pytest.approx((above * 0.1 + 1_000 * 0.5) / 1e6)
    assert cost(over, LUNA) == pytest.approx(((above + 1) * 0.2 + 1_000 * 0.75) / 1e6)


def test_arenas_table():
    prices = load_prices()
    assert {"gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"} <= set(prices)
    assert all({"input", "output"} <= set(p) for p in prices.values())


def test_tasks_get_the_prices_of_their_models(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# spec")
    out = make_task(spec, tmp_path / "t", game_name="g", allowed_models=["gpt-6-luna"])
    task = json.loads((out / "task.json").read_text())
    assert task["prices"] == {"gpt-6-luna": load_prices()["gpt-6-luna"]}
    with pytest.raises(ValueError, match="without a price"):
        make_task(spec, tmp_path / "u", game_name="g", allowed_models=["gpt-9-nope"])
