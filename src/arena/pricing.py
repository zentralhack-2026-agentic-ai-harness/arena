"""Prices and the cost of one API call: the formula the evaluation charges by, and that a
harness can use to track its own spend.

    from arena.pricing import cost
    spent += cost(response.usage, task["prices"][model])

Prices are USD per 1M tokens, OpenAI's Standard tier (other tiers are refused at evaluation):

    {"model": {"input": .., "cached_input": .., "cache_write": .., "output": ..,
               "long_context": {"above_input_tokens": N, "input": .., ...}}}

A call costs

    (uncached * input + cached * cached_input + cache_write * cache_write + output * output) / 1e6

with `cached` and `cache_write` from `usage.input_tokens_details`, uncached = the rest of the
input tokens, and reasoning tokens counted in the output tokens. A call whose input tokens
exceed `long_context.above_input_tokens` is charged entirely at the long-context prices.
Missing `cached_input` or `cache_write` prices default to `input`. The table tasks get by
default ships with arena (prices.json).
"""

import json
from pathlib import Path

PRICES = Path(__file__).with_name("prices.json")


def load_prices(path: Path | None = None) -> dict[str, dict]:
    """The price table: arena's own, or the one at `path`."""
    return json.loads((path or PRICES).read_text())


def cost(usage, price: dict) -> float:
    """USD for one call: its `usage` (a Responses API dict, or the openai SDK's object) at
    `price` (one model's entry of the price table)."""
    if usage is None:
        return 0.0
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    inp, out = usage.get("input_tokens") or 0, usage.get("output_tokens") or 0
    details = usage.get("input_tokens_details") or {}
    cached = details.get("cached_tokens") or 0
    written = details.get("cache_write_tokens") or 0
    uncached = max(0, inp - cached - written)
    long = price.get("long_context")
    if long and inp > long["above_input_tokens"]:
        price = long
    p_in = price["input"]
    return (
        uncached * p_in
        + cached * price.get("cached_input", p_in)
        + written * price.get("cache_write", p_in)
        + out * price["output"]
    ) / 1e6
