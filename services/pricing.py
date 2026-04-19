"""Token-counting and cost estimation for generated prompts.

Model: Claude Sonnet 4 (current production default per app/routers/generation.py
ANTHROPIC_MODEL). Rates are public pricing per million input/output tokens.
Update the constants below when the model or rates change.

Token counter:
  - Primary path: tiktoken cl100k_base. Approximate for Claude (OpenAI's BPE
    is not Claude's tokenizer) but within ~5–10% for English prose. Zero
    latency, zero cost per count. Display always renders the value with a
    "~" prefix so the approximation is visible to users.
  - Fallback: CLAUDE_CHARS_PER_TOKEN (3.8 chars/token — Anthropic's published
    rule of thumb) when tiktoken cannot be imported. Used transparently so
    production code need not care which path fired.

Future: swap to the official POST /v1/messages/count_tokens HTTP endpoint
when the pinned anthropic SDK (0.40.0) is upgraded to a version that binds
it natively. Until then, approximation is acceptable for a display figure.
"""

from __future__ import annotations

import math


# ── Pricing — Claude Sonnet 4 (update when rates change) ─────────────────────

INPUT_RATE_PER_MTOK: float = 3.00    # USD per million input tokens
OUTPUT_RATE_PER_MTOK: float = 15.00  # USD per million output tokens
DEFAULT_OUTPUT_TOKENS_ESTIMATE: int = 500

# Fallback heuristic — Anthropic's published rule of thumb for English prose.
CLAUDE_CHARS_PER_TOKEN: float = 3.8


# ── Token counting ───────────────────────────────────────────────────────────

def _count_tokens_via_tiktoken(text: str) -> int | None:
    """Try tiktoken cl100k_base. Return None if tiktoken is unavailable."""
    try:
        import tiktoken
    except ImportError:
        return None
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        # Tiktoken is installed but failed (missing BPE data, etc.) — fall back.
        return None


def _count_tokens_via_heuristic(text: str) -> int:
    if not text:
        return 0
    return math.ceil(len(text) / CLAUDE_CHARS_PER_TOKEN)


def count_tokens(text: str) -> int:
    """Return approximate token count for `text`. Never raises."""
    if not text:
        return 0
    via_tiktoken = _count_tokens_via_tiktoken(text)
    if via_tiktoken is not None:
        return via_tiktoken
    return _count_tokens_via_heuristic(text)


# ── Cost estimation ──────────────────────────────────────────────────────────

def estimate_cost_usd(
    input_tokens: int,
    output_tokens: int = DEFAULT_OUTPUT_TOKENS_ESTIMATE,
) -> float:
    """Estimate USD cost per invocation of a prompt with `input_tokens` in the
    system prompt and `output_tokens` produced. Returns a float rounded to
    four decimal places (sub-cent granularity is meaningful at scale)."""
    input_cost = (input_tokens / 1_000_000) * INPUT_RATE_PER_MTOK
    output_cost = (output_tokens / 1_000_000) * OUTPUT_RATE_PER_MTOK
    return round(input_cost + output_cost, 4)
