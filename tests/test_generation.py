"""Tests for generation router — brief validation, scoring, generation."""

from datetime import datetime
from unittest.mock import MagicMock, patch


# ── validate_brief: F2 regression ────────────────────────────────────────────

def test_validate_brief_returns_502_when_claude_fails(client, auth_headers):
    """F2 regression: Claude API failure must NOT silently accept the brief.

    Previously, any exception from the Claude call was swallowed and the
    endpoint returned tier=1 accepted=True. This let vague briefs through
    whenever validation was unavailable. The fix propagates a 502 so the
    frontend can show 'validation unavailable'.
    """
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("upstream unavailable")

    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = client.post(
            "/prompts/validate-brief",
            json={"description": "summarise documents for core systems"},
            headers=auth_headers,
        )

    assert resp.status_code == 502, resp.text
    body = resp.json()
    assert "Brief validation unavailable" in body["detail"]
    assert "upstream unavailable" in body["detail"]


# ── generate_prompt_text: VariableResolver integration (Slot A2 part 2) ──────

def test_generate_substitutes_variable_placeholders(client, auth_headers):
    """REG_D2: {generation_date} and {author} are substituted before the
    response leaves /prompts/generate; {version_number} stays literal because
    no PromptVersion exists at first-generation time."""
    claude_text = (
        "Generated on {generation_date} by {author}, version {version_number}."
    )
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=claude_text)]
    mock_client.messages.create.return_value = mock_response

    fixed_now = datetime(2026, 4, 19, 12, 0, 0)
    fake_datetime = MagicMock(wraps=datetime)
    fake_datetime.utcnow.return_value = fixed_now

    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client), \
         patch("app.routers.generation.datetime", fake_datetime):
        resp = client.post(
            "/prompts/generate",
            json={"title": "Test prompt", "prompt_type": "Summarisation"},
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    text = resp.json()["prompt_text"]
    assert "2026-04-19" in text
    assert "Test Maker" in text
    assert "{version_number}" in text
