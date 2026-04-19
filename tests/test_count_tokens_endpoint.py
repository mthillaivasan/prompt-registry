"""Tests for POST /prompts/count-tokens endpoint."""


def test_requires_auth(client):
    resp = client.post("/prompts/count-tokens", json={"text": "hello"})
    assert resp.status_code == 401


def test_happy_path_returns_expected_shape(client, auth_headers):
    resp = client.post(
        "/prompts/count-tokens",
        json={"text": "You are a financial analyst. Extract fields from the prospectus."},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) == {"token_count", "estimated_cost_usd", "output_tokens_estimate"}
    assert isinstance(body["token_count"], int)
    assert body["token_count"] > 0
    assert isinstance(body["estimated_cost_usd"], (int, float))
    assert body["estimated_cost_usd"] > 0
    assert body["output_tokens_estimate"] == 500


def test_empty_text_returns_zero_tokens(client, auth_headers):
    resp = client.post("/prompts/count-tokens", json={"text": ""}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_count"] == 0


def test_missing_text_field_defaults_to_empty(client, auth_headers):
    resp = client.post("/prompts/count-tokens", json={}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["token_count"] == 0
