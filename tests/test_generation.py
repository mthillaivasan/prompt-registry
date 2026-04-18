"""Tests for generation router — brief validation, scoring, generation."""

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
