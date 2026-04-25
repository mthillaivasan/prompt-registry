"""
Tests for the deployment form router (Block 13).

Covers:
  - GET /forms/deployment_form returns config-driven field list
  - POST /deployments creates a Draft record
  - PUT  /deployments/{id} saves form responses with non-blocking errors
  - POST /deployments/{id}/submit blocks transition when validation fails
  - submit dual-writes ai_platform / output_destination onto the prompt
"""

import json

from app.models import DeploymentRecord, FormField, Prompt


def _create_prompt(client, headers):
    payload = {
        "title": "Deployment test prompt",
        "prompt_type": "Summarisation",
        "deployment_target": "OpenAI",
        "input_type": "Plain text",
        "output_type": "Plain text",
        "risk_tier": "Limited",
        "review_cadence_days": 180,
        "prompt_text": "Summarise the input.",
        "change_summary": "v1",
    }
    return client.post("/prompts", json=payload, headers=headers)


def _create_deployment(client, headers, prompt_id, version_id):
    return client.post(
        "/deployments",
        json={"prompt_id": prompt_id, "version_id": version_id},
        headers=headers,
    )


def _full_responses():
    """A complete, valid deployment_form response payload."""
    return {
        "invocation_trigger": "manual_user_action",
        "invocation_frequency_per_day": "1-10",
        "latency_envelope_seconds": "5",
        "input_data_categories": ["public_information"],
        "input_redaction_applied": True,
        "input_size_p95_tokens": "1024",
        "input_user_supplied": False,
        "output_destination": "human_review_only",
        "output_executed_by_machine": False,
        "output_storage_retention_days": "30",
        "logging_destination": "audit_log_table",
        "metric_collection": ["latency", "error_rate"],
        "alerting_thresholds_defined": False,
        # runtime_owner_id and approver_id filled in per-test from real users
        "change_review_frequency_days": "90",
        "breaking_change_protocol": "Notify Maker via change-management mailbox.",
        "model_provider": "Anthropic",
        "data_residency": "UK",
        "sub_processing_disclosed": True,
        "audit_rights_in_contract": True,
    }


# ── Form config ─────────────────────────────────────────────────────────────

def test_form_config_requires_auth(client):
    resp = client.get("/forms/deployment_form")
    assert resp.status_code == 401


def test_form_config_returns_seeded_fields(client, auth_headers):
    resp = client.get("/forms/deployment_form", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["form_code"] == "deployment_form"
    field_codes = [f["field_code"] for f in body["fields"]]
    # The form should have all six groups; sample one from each.
    for expected in [
        "invocation_trigger",
        "input_data_categories",
        "output_destination",
        "logging_destination",
        "runtime_owner_id",
        "model_provider",
    ]:
        assert expected in field_codes, f"missing {expected}"


def test_form_config_sorts_fields(client, auth_headers):
    resp = client.get("/forms/deployment_form", headers=auth_headers)
    fields = resp.json()["fields"]
    sort_orders = [f["sort_order"] for f in fields]
    assert sort_orders == sorted(sort_orders)


def test_form_config_404_for_unknown_form(client, auth_headers):
    resp = client.get("/forms/non_existent_form", headers=auth_headers)
    assert resp.status_code == 404


def test_form_config_dynamic_user_options(client, auth_headers, second_user):
    """Owner / approver fields ship with empty options[] in seed; the
    server populates them from the users table."""
    resp = client.get("/forms/deployment_form", headers=auth_headers)
    fields = {f["field_code"]: f for f in resp.json()["fields"]}
    owner_field = fields["runtime_owner_id"]
    approver_field = fields["approver_id"]
    assert owner_field["options"] is not None
    assert len(owner_field["options"]) >= 1  # test_user is a Maker
    assert all(isinstance(o, dict) for o in owner_field["options"])
    # Approver field accepts only Checker or Admin
    approver_labels = " ".join(o["label"] for o in approver_field["options"])
    assert "Maker" not in approver_labels
    assert "Checker" in approver_labels


# ── Create / get / list ─────────────────────────────────────────────────────

def test_create_deployment_returns_draft(client, auth_headers):
    p = _create_prompt(client, auth_headers).json()
    resp = _create_deployment(
        client, auth_headers, p["prompt_id"], p["versions"][0]["version_id"]
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "Draft"
    assert body["prompt_id"] == p["prompt_id"]
    assert body["form_responses"] == {}


def test_create_deployment_unknown_version_404(client, auth_headers):
    p = _create_prompt(client, auth_headers).json()
    resp = client.post(
        "/deployments",
        json={"prompt_id": p["prompt_id"], "version_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_get_deployment(client, auth_headers):
    p = _create_prompt(client, auth_headers).json()
    d = _create_deployment(
        client, auth_headers, p["prompt_id"], p["versions"][0]["version_id"]
    ).json()
    resp = client.get(f"/deployments/{d['deployment_id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["deployment_id"] == d["deployment_id"]


def test_list_deployments_filters_by_prompt(client, auth_headers):
    p1 = _create_prompt(client, auth_headers).json()
    p2 = _create_prompt(client, auth_headers).json()
    _create_deployment(client, auth_headers, p1["prompt_id"], p1["versions"][0]["version_id"])
    _create_deployment(client, auth_headers, p2["prompt_id"], p2["versions"][0]["version_id"])
    resp = client.get(f"/deployments?prompt_id={p1['prompt_id']}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["prompt_id"] == p1["prompt_id"]


# ── PUT / submit ────────────────────────────────────────────────────────────

def test_put_responses_persists_and_validates(client, auth_headers, test_user):
    p = _create_prompt(client, auth_headers).json()
    d = _create_deployment(
        client, auth_headers, p["prompt_id"], p["versions"][0]["version_id"]
    ).json()
    responses = _full_responses()
    responses["runtime_owner_id"] = test_user.user_id
    responses["approver_id"] = test_user.user_id  # any user_id; validation only checks shape
    resp = client.put(
        f"/deployments/{d['deployment_id']}",
        json={"responses": responses},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["errors"] == {}
    assert body["record"]["form_responses"]["invocation_trigger"] == "manual_user_action"
    assert body["record"]["ai_platform"] == "Anthropic"
    assert body["record"]["output_destination"] == "human_review_only"


def test_put_responses_returns_validation_errors_on_partial_save(client, auth_headers):
    p = _create_prompt(client, auth_headers).json()
    d = _create_deployment(
        client, auth_headers, p["prompt_id"], p["versions"][0]["version_id"]
    ).json()
    # Missing required fields
    resp = client.put(
        f"/deployments/{d['deployment_id']}",
        json={"responses": {"invocation_trigger": "manual_user_action"}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    errors = resp.json()["errors"]
    # Several required fields should be flagged
    assert "input_data_categories" in errors
    assert "model_provider" in errors
    # The provided field is fine
    assert "invocation_trigger" not in errors


def test_submit_blocks_on_validation_errors(client, auth_headers):
    p = _create_prompt(client, auth_headers).json()
    d = _create_deployment(
        client, auth_headers, p["prompt_id"], p["versions"][0]["version_id"]
    ).json()
    resp = client.post(
        f"/deployments/{d['deployment_id']}/submit",
        headers=auth_headers,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "errors" in body["detail"]


def test_submit_dual_writes_to_prompt(client, auth_headers, test_user, db):
    p = _create_prompt(client, auth_headers).json()
    d = _create_deployment(
        client, auth_headers, p["prompt_id"], p["versions"][0]["version_id"]
    ).json()
    responses = _full_responses()
    responses["runtime_owner_id"] = test_user.user_id
    responses["approver_id"] = test_user.user_id
    client.put(
        f"/deployments/{d['deployment_id']}",
        json={"responses": responses},
        headers=auth_headers,
    )
    resp = client.post(
        f"/deployments/{d['deployment_id']}/submit",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "Pending Approval"

    # Verify prompt row got the dual-writes
    db.expire_all()
    prompt = db.query(Prompt).filter(Prompt.prompt_id == p["prompt_id"]).first()
    assert prompt.ai_platform == "Anthropic"
    assert prompt.output_destination == "human_review_only"


def test_cannot_edit_after_submit(client, auth_headers, test_user):
    p = _create_prompt(client, auth_headers).json()
    d = _create_deployment(
        client, auth_headers, p["prompt_id"], p["versions"][0]["version_id"]
    ).json()
    responses = _full_responses()
    responses["runtime_owner_id"] = test_user.user_id
    responses["approver_id"] = test_user.user_id
    client.put(
        f"/deployments/{d['deployment_id']}",
        json={"responses": responses},
        headers=auth_headers,
    )
    submit = client.post(
        f"/deployments/{d['deployment_id']}/submit",
        headers=auth_headers,
    )
    assert submit.status_code == 200

    # Now PUT should be blocked
    resp = client.put(
        f"/deployments/{d['deployment_id']}",
        json={"responses": responses},
        headers=auth_headers,
    )
    assert resp.status_code == 409


# ── Form-validation helper (unit) ───────────────────────────────────────────

def test_validation_helper_handles_all_shapes(db):
    from services import form_validation

    fields = (
        db.query(FormField)
        .filter(FormField.form_code == "deployment_form", FormField.is_active == True)  # noqa: E712
        .all()
    )
    # Empty responses → required-fields all flag, no other errors.
    errors, normalised = form_validation.validate_form_response(fields, {})
    for code, errs in errors.items():
        assert errs == ["required"], f"{code} unexpected errors {errs}"
    # All responses keys are present in `normalised`, even if blank.
    for f in fields:
        assert f.field_code in normalised


def test_validation_helper_rejects_unknown_select_value(db):
    from services import form_validation
    fields = [f for f in db.query(FormField).filter(
        FormField.form_code == "deployment_form",
        FormField.is_active == True,  # noqa: E712
    ).all() if f.field_code == "model_provider"]
    errors, _ = form_validation.validate_form_response(fields, {"model_provider": "Foobar"})
    assert "model_provider" in errors
    assert "not_in_options" in errors["model_provider"]


def test_validation_helper_pattern_check(db):
    from services import form_validation
    fields = [f for f in db.query(FormField).filter(
        FormField.form_code == "deployment_form",
        FormField.is_active == True,  # noqa: E712
    ).all() if f.field_code == "change_review_frequency_days"]
    errors, _ = form_validation.validate_form_response(fields, {"change_review_frequency_days": "abc"})
    assert "change_review_frequency_days" in errors
