"""Tests for POST /prompts/briefs/validate-topic (Phase A).

Covers: happy paths for structured and prose topics, sibling context
plumbing through to the user message, per-topic conversation-history
filtering, 502 on Claude failure, 400 on unknown topic_id, 501 on
prompt_type without a rubric set.

All Claude calls mocked — pytest stays deterministic and free.
"""

import json
from unittest.mock import MagicMock, patch


def _mock_claude_returning(text: str) -> MagicMock:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_response
    return mock_client


def _post(client, auth_headers, body):
    return client.post("/prompts/briefs/validate-topic", json=body, headers=auth_headers)


def test_structured_topic_happy_path_returns_green(client, auth_headers):
    """Topic 1 (Prompt Type) with a valid pick — Claude returns green."""
    mock_client = _mock_claude_returning('{"state": "green"}')

    body = {
        "topic_id": "topic_1_prompt_type",
        "prompt_type": "Extraction",
        "topic_answer": "Extraction",
        "sibling_answers": {},
        "conversation_history": [],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = _post(client, auth_headers, body)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["state"] == "green"
    assert data["question"] is None
    assert data["suggestion"] is None


def test_prose_topic_returns_red_with_question_and_options(client, auth_headers):
    """Topic 6 (Data points) with empty answer — Claude returns red + probe."""
    claude_reply = json.dumps({
        "state": "red",
        "question": "What specific fields should the prompt extract from the prospectus?",
        "options": [
            "subscription cut-off times",
            "minimum investment amounts",
            "ISINs and share class names",
            "fund domicile",
            "management fees",
            "dealing frequency",
        ],
        "free_text_placeholder": "Or describe the fields in your own words...",
    })
    mock_client = _mock_claude_returning(claude_reply)

    body = {
        "topic_id": "topic_6_data_points",
        "prompt_type": "Extraction",
        "topic_answer": "",
        "sibling_answers": {"topic_2_source_doc": "Prospectus"},
        "conversation_history": [],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = _post(client, auth_headers, body)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["state"] == "red"
    assert "extract" in data["question"].lower()
    assert len(data["options"]) == 6
    assert data["free_text_placeholder"].startswith("Or describe")


def test_sibling_context_reaches_claude_user_message(client, auth_headers):
    """sibling_answers must appear in the user turn verbatim so Claude can
    cross-reference. The anti-drift rule (system prompt) then prevents
    probing gaps — but the sibling facts must be delivered."""
    mock_client = _mock_claude_returning('{"state": "amber", "suggestion": "x", "suggested_addition": "y"}')

    body = {
        "topic_id": "topic_7_field_format",
        "prompt_type": "Extraction",
        "topic_answer": "times as HH:MM",
        "sibling_answers": {
            "topic_6_data_points": "subscription cut-off time, ISIN",
            "topic_4_target_system": "Simcorp Dimension",
        },
        "conversation_history": [],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = _post(client, auth_headers, body)

    assert resp.status_code == 200, resp.text
    sent_user_msg = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "SIBLING ANSWERS FOR CONTEXT ONLY:" in sent_user_msg
    assert "subscription cut-off time, ISIN" in sent_user_msg
    assert "Simcorp Dimension" in sent_user_msg


def test_conversation_history_filtered_to_focal_topic(client, auth_headers):
    """Entries with topic_id != focal must be excluded from the user message.
    Entries with skipped=True must also be excluded. Validation/track markers
    are dropped. Real Q&A for the focal topic passes through."""
    mock_client = _mock_claude_returning('{"state": "amber", "suggestion": "a", "suggested_addition": "b"}')

    body = {
        "topic_id": "topic_6_data_points",
        "prompt_type": "Extraction",
        "topic_answer": "cut-off time",
        "sibling_answers": {},
        "conversation_history": [
            {"question": "focal Q kept", "answer": "focal A kept", "skipped": False,
             "topic_id": "topic_6_data_points"},
            {"question": "other topic Q", "answer": "other topic A", "skipped": False,
             "topic_id": "topic_7_field_format"},
            {"question": "skipped Q", "answer": "skipped A", "skipped": True,
             "topic_id": "topic_6_data_points"},
            {"question": "validation", "answer": "accepted", "skipped": False,
             "topic_id": "topic_6_data_points"},
        ],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = _post(client, auth_headers, body)

    assert resp.status_code == 200, resp.text
    sent_user_msg = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "focal Q kept" in sent_user_msg
    assert "focal A kept" in sent_user_msg
    assert "other topic Q" not in sent_user_msg
    assert "skipped Q" not in sent_user_msg
    # "validation" as a conversation question marker is dropped; it may appear
    # incidentally elsewhere (system prompt etc.), so we check the dropped Q's
    # answer which is uniquely identifying
    assert "A: accepted" not in sent_user_msg


def test_claude_api_failure_returns_502(client, auth_headers):
    """F2 pattern: upstream failure propagates as 502, not silent pass."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("upstream boom")

    body = {
        "topic_id": "topic_6_data_points",
        "prompt_type": "Extraction",
        "topic_answer": "something",
        "sibling_answers": {},
        "conversation_history": [],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = _post(client, auth_headers, body)

    assert resp.status_code == 502, resp.text
    assert "Topic validation unavailable" in resp.json()["detail"]
    assert "upstream boom" in resp.json()["detail"]


def test_unknown_topic_id_returns_400(client, auth_headers):
    """Bogus topic_id must be rejected before any Claude call."""
    mock_client = _mock_claude_returning('{"state": "green"}')

    body = {
        "topic_id": "topic_99_nonexistent",
        "prompt_type": "Extraction",
        "topic_answer": "",
        "sibling_answers": {},
        "conversation_history": [],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = _post(client, auth_headers, body)

    assert resp.status_code == 400, resp.text
    assert "Unknown topic_id" in resp.json()["detail"]
    assert mock_client.messages.create.call_count == 0


def test_reference_examples_injected_into_system_prompt(client, auth_headers):
    """Drop L2: when reference_examples is non-empty, the block must reach
    Claude's system prompt with title + excerpt, and an explicit "do not copy"
    framing. Empty list must leave the system prompt unchanged."""
    mock_client = _mock_claude_returning('{"state": "green"}')

    body = {
        "topic_id": "topic_6_data_points",
        "prompt_type": "Extraction",
        "topic_answer": "fields to extract: cut-off time, ISIN",
        "sibling_answers": {},
        "conversation_history": [],
        "reference_examples": [
            {"title": "Prospectus extraction", "excerpt": "Fields to extract include subscription cut-off time and minimum investment."},
            {"title": "Policy clause extraction", "excerpt": "Extract every clause matching one of eight regulated topics."},
        ],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = _post(client, auth_headers, body)

    assert resp.status_code == 200, resp.text
    sent_system = mock_client.messages.create.call_args.kwargs["system"]
    assert "REFERENCE EXAMPLES" in sent_system
    assert "do not copy verbatim" in sent_system
    assert "Prospectus extraction" in sent_system
    assert "subscription cut-off time" in sent_system
    assert "Policy clause extraction" in sent_system
    # Block must sit BEFORE the response shape so it stays context, not contract
    assert sent_system.index("REFERENCE EXAMPLES") < sent_system.index("RESPONSE SHAPE")


def test_empty_reference_examples_leaves_system_prompt_clean(client, auth_headers):
    mock_client = _mock_claude_returning('{"state": "green"}')

    body = {
        "topic_id": "topic_6_data_points",
        "prompt_type": "Extraction",
        "topic_answer": "a",
        "sibling_answers": {},
        "conversation_history": [],
        "reference_examples": [],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = _post(client, auth_headers, body)

    assert resp.status_code == 200, resp.text
    sent_system = mock_client.messages.create.call_args.kwargs["system"]
    assert "REFERENCE EXAMPLES" not in sent_system


def test_reference_examples_field_is_optional(client, auth_headers):
    """Back-compat: callers that don't send reference_examples still work."""
    mock_client = _mock_claude_returning('{"state": "green"}')

    body = {
        "topic_id": "topic_6_data_points",
        "prompt_type": "Extraction",
        "topic_answer": "a",
        "sibling_answers": {},
        "conversation_history": [],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = _post(client, auth_headers, body)

    assert resp.status_code == 200, resp.text
    sent_system = mock_client.messages.create.call_args.kwargs["system"]
    assert "REFERENCE EXAMPLES" not in sent_system


def test_unsupported_prompt_type_returns_501(client, auth_headers):
    """Only Extraction has a rubric set in Phase A; others return 501."""
    mock_client = _mock_claude_returning('{"state": "green"}')

    body = {
        "topic_id": "topic_1_prompt_type",
        "prompt_type": "Classification",  # no rubric set yet
        "topic_answer": "Classification",
        "sibling_answers": {},
        "conversation_history": [],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = _post(client, auth_headers, body)

    assert resp.status_code == 501, resp.text
    assert "not yet available" in resp.json()["detail"]
    assert mock_client.messages.create.call_count == 0
