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


# ── generate_prompt_text: instructional_text rendering (Slot A3) ─────────────

def _mock_claude_returning(text: str) -> MagicMock:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_response
    return mock_client


def test_dimension_with_instructional_text_renders_clean(client, auth_headers):
    """REG_D2 has instructional_text seeded — its guardrail block must be the
    plain instructional_text, not '- REG_D2 (Transparency): ...'. No code
    prefix or framework label leaks into the prompt sent to Claude."""
    mock_client = _mock_claude_returning("body")

    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = client.post(
            "/prompts/generate",
            json={
                "title": "X",
                "prompt_type": "Summarisation",
                "selected_guardrails": ["REG_D2"],
            },
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    sent_system = mock_client.messages.create.call_args.kwargs["system"]
    assert "REG_" not in sent_system
    assert "OWASP_" not in sent_system
    assert "NIST_" not in sent_system
    assert "ISO42001_" not in sent_system
    assert "AI-generated and advisory" in sent_system  # confirms instructional_text was rendered
    assert "AUDIT" not in sent_system  # AUDIT scaffold split out — wrapper-metadata UI surfaces it now


def test_dimension_without_instructional_text_uses_fallback_format(client, auth_headers):
    """REG_D3 (prompt_content, no instructional_text) — the guardrail block
    must fall back to the legacy '- {code} ({name}): {description}' format.

    Previously exercised REG_D1; switched to REG_D3 after Drop 3 Item 3
    classified REG_D1 as wrapper_metadata (now filtered out of the prompt).
    """
    mock_client = _mock_claude_returning("body")

    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = client.post(
            "/prompts/generate",
            json={
                "title": "X",
                "prompt_type": "Summarisation",
                "selected_guardrails": ["REG_D3"],
            },
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    sent_system = mock_client.messages.create.call_args.kwargs["system"]
    assert "- REG_D3 (Data Minimisation):" in sent_system


# ── Drop 3 Item 3: content_type filter on generator output ───────────────────

def test_wrapper_metadata_dim_excluded_from_prompt(client, auth_headers):
    """REG_D1 is classified wrapper_metadata — it must NOT render into the
    generated prompt. Path #1 (dimension guardrail_block) filters it out."""
    mock_client = _mock_claude_returning("body")

    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = client.post(
            "/prompts/generate",
            json={
                "title": "X",
                "prompt_type": "Summarisation",
                "selected_guardrails": ["REG_D1"],
            },
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    sent_system = mock_client.messages.create.call_args.kwargs["system"]
    assert "REG_D1" not in sent_system
    assert "Human Oversight" not in sent_system


def test_registry_policy_dim_excluded_from_prompt(client, auth_headers):
    """REG_D6 is classified registry_policy — it must NOT render into the
    generated prompt."""
    mock_client = _mock_claude_returning("body")

    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = client.post(
            "/prompts/generate",
            json={
                "title": "X",
                "prompt_type": "Summarisation",
                "selected_guardrails": ["REG_D6"],
            },
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    sent_system = mock_client.messages.create.call_args.kwargs["system"]
    assert "REG_D6" not in sent_system
    assert "Outsourcing" not in sent_system


def test_mixed_selection_only_prompt_content_renders(client, auth_headers):
    """REG_D2 (prompt_content, has instructional_text) + REG_D1 (wrapper).
    Only REG_D2 content should reach the prompt."""
    mock_client = _mock_claude_returning("body")

    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = client.post(
            "/prompts/generate",
            json={
                "title": "X",
                "prompt_type": "Summarisation",
                "selected_guardrails": ["REG_D2", "REG_D1"],
            },
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    sent_system = mock_client.messages.create.call_args.kwargs["system"]
    assert "AI-generated and advisory" in sent_system  # REG_D2 instructional_text
    assert "AUDIT" not in sent_system  # AUDIT scaffold no longer in prompt body
    assert "REG_D1" not in sent_system
    assert "Human Oversight" not in sent_system


def test_reg_d3_prompt_content_renders_positive_case(client, auth_headers):
    """Positive lock-in: REG_D3 (prompt_content, no instructional_text) must
    render. Ensures the content_type filter isn't over-aggressive."""
    mock_client = _mock_claude_returning("body")

    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = client.post(
            "/prompts/generate",
            json={
                "title": "X",
                "prompt_type": "Summarisation",
                "selected_guardrails": ["REG_D3"],
            },
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    sent_system = mock_client.messages.create.call_args.kwargs["system"]
    assert "REG_D3" in sent_system
    assert "Data Minimisation" in sent_system
