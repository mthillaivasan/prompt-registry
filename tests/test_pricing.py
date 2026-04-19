"""Tests for services.pricing — token counting + cost estimation."""

import sys
from unittest.mock import patch

from services import pricing
from services.pricing import (
    DEFAULT_OUTPUT_TOKENS_ESTIMATE,
    INPUT_RATE_PER_MTOK,
    OUTPUT_RATE_PER_MTOK,
    count_tokens,
    estimate_cost_usd,
)


# ── Token counting ───────────────────────────────────────────────────────────

def test_count_tokens_empty_is_zero():
    assert count_tokens("") == 0
    assert count_tokens(None) == 0


def test_count_tokens_tiktoken_path_known_value():
    """tiktoken cl100k_base: fixed sample returns deterministic count."""
    # "Hello, world!" tokenises to 4 tokens in cl100k_base.
    assert count_tokens("Hello, world!") == 4


def test_count_tokens_heuristic_fallback_when_tiktoken_missing():
    """With tiktoken import masked, fall back to ceil(chars / 3.8)."""
    # Force the module-level import in _count_tokens_via_tiktoken to raise.
    with patch.dict(sys.modules, {"tiktoken": None}):
        # 38 chars / 3.8 = 10
        assert count_tokens("x" * 38) == 10
        # 39 chars / 3.8 = 10.26 → ceil → 11
        assert count_tokens("x" * 39) == 11


def test_count_tokens_heuristic_returns_zero_for_empty():
    with patch.dict(sys.modules, {"tiktoken": None}):
        assert count_tokens("") == 0


# ── Cost estimation ──────────────────────────────────────────────────────────

def test_estimate_cost_usd_default_output_estimate():
    """Default output estimate is applied when omitted."""
    # 10_000 input tokens × $3/MTok = $0.03
    # 500 output tokens × $15/MTok = $0.0075
    # Total = $0.0375 → rounded to $0.0375
    cost = estimate_cost_usd(10_000)
    assert cost == round(0.03 + 0.0075, 4)


def test_estimate_cost_usd_custom_output():
    # 1_000 input × $3/MTok = $0.003
    # 2_000 output × $15/MTok = $0.03
    # Total = $0.033
    assert estimate_cost_usd(1_000, output_tokens=2_000) == round(0.003 + 0.03, 4)


def test_estimate_cost_usd_zero_input():
    # 0 input tokens × anything = 0; default output cost still applies
    cost = estimate_cost_usd(0)
    assert cost == round(0 + 500 * OUTPUT_RATE_PER_MTOK / 1_000_000, 4)


def test_rates_are_public_sonnet_4_values():
    """Guards against accidental rate drift without a deliberate update."""
    assert INPUT_RATE_PER_MTOK == 3.00
    assert OUTPUT_RATE_PER_MTOK == 15.00
    assert DEFAULT_OUTPUT_TOKENS_ESTIMATE == 500


# ── Realistic prompt spot-check ──────────────────────────────────────────────

def test_sample_generated_prompt_sanity_check():
    """A ~4,000-char generated prompt should land in the expected ballpark:
    roughly 800-1,200 tokens and sub-cent input cost + ~$0.0075 output.
    This is a sanity check, not a contract; fine to update when rates shift.
    """
    sample = (
        "You are a financial-document analyst. Extract subscription-terms "
        "data from the provided fund prospectus excerpt.\n\n"
        "Fields to extract (in this order):\n"
        "  - Subscription cut-off time (include timezone)\n"
        "  - Minimum initial investment (currency + amount)\n"
        "  - Minimum subsequent investment\n"
        "  - Subscription fee percent\n"
        "  - Redemption cut-off time\n"
        "  - Settlement days T+N\n"
        "  - Lock-up period months\n\n"
        "For every extracted value, cite the source page and section "
        "heading. If a value is not stated, render 'not found' and mark "
        "confidence low with a one-line explanation note.\n\n"
        "Do not infer values. Do not aggregate across fields. If the "
        "prospectus contains conflicting values across pages, report both "
        "with a terminal CONFLICTS section.\n\n"
        "OUTPUT FORMAT — review-optimised bulleted layout. One block per "
        "field. Each block: Field, Value, Source, Confidence, Note.\n"
    ) * 4  # roughly 4 KB of prose
    tokens = count_tokens(sample)
    assert 500 <= tokens <= 2_000
    cost = estimate_cost_usd(tokens)
    assert 0.005 < cost < 0.05  # should be sub-5 cents per invocation
