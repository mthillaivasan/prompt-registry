# DEPLOYMENT_FORM_SPEC.md — Block 12

The Deployment form captures runtime context for a Build-approved
prompt: invocation context, input sources, output handling, monitoring
cadence, runtime owner, incident response, change management.

Field definitions are **data**, not code. They live in the `form_fields`
table seeded from `seed/form_fields.yml`. Block 13 builds the form;
Block 14 wires the Deployment compliance engine; Block 16 wires the
gate.

---

## Field set

Six field groups, each capturing one Deployment-phase concern. Adding
a field is a YAML edit; the rendered form regenerates.

### 1. Invocation context

| Field | Type | Required | Notes |
|---|---|---|---|
| invocation_trigger | select | yes | `manual_user_action`, `scheduled_job`, `event_driven`, `api_callout`, `agent_chain` |
| invocation_frequency_per_day | select | yes | `<1`, `1-10`, `10-100`, `100-1000`, `>1000` |
| latency_envelope_seconds | text | no | numeric, free; null if no constraint |

Drives `OWASP_LLM10` (unbounded consumption) Deployment-side
applicability and informs cost projections in Block 17.

### 2. Input sources

| Field | Type | Required | Notes |
|---|---|---|---|
| input_data_categories | multiselect | yes | `personal_data`, `client_confidential`, `regulatory_filings`, `internal_documentation`, `public_information`, `model_generated` |
| input_redaction_applied | boolean | yes | true if a redaction step runs upstream of the LLM |
| input_size_p95_tokens | text | no | numeric estimate |
| input_user_supplied | boolean | yes | true if any portion of the input is user-provided rather than system-controlled |

`input_user_supplied=true` raises `OWASP_LLM01` (prompt injection)
applicability at Deployment. `personal_data` in `input_data_categories`
raises `REG_DATA_MINIMISATION` and `ISO42001_DATA_GOVERNANCE` Deployment
checks.

### 3. Output handling

| Field | Type | Required | Notes |
|---|---|---|---|
| output_destination | select | yes | `human_review_only`, `report_render`, `automated_action`, `feed_into_downstream_llm`, `stored_no_display` |
| output_executed_by_machine | boolean | yes | true if any output is parsed and acted on without human review |
| output_storage_retention_days | text | no | numeric; null if not stored |

`output_executed_by_machine=true` raises `OWASP_EXCESSIVE_AGENCY`
Deployment-side and `OWASP_LLM05` Improper Output Handling.

### 4. Monitoring and observability

| Field | Type | Required | Notes |
|---|---|---|---|
| logging_destination | select | yes | `application_logs`, `audit_log_table`, `siem`, `none` |
| metric_collection | multiselect | yes | `latency`, `token_count`, `error_rate`, `output_quality_sample`, `none` |
| alerting_thresholds_defined | boolean | yes | true if any metric has an alerting threshold |

Drives `NIST_MEASURE_QUALITY` Deployment binding.

### 5. Ownership and change management

| Field | Type | Required | Notes |
|---|---|---|---|
| runtime_owner_id | select | yes | populated from users with role Maker/Checker/Admin |
| approver_id | select | yes | populated from users with role Checker/Admin |
| change_review_frequency_days | text | yes | numeric; default 90 |
| breaking_change_protocol | textarea | no | free text |

Drives `NIST_GOVERN_ROLES` Deployment binding (declared owner must be
the runtime owner here).

### 6. Outsourcing and residency

| Field | Type | Required | Notes |
|---|---|---|---|
| model_provider | select | yes | `Anthropic`, `OpenAI`, `Azure_OpenAI`, `Vertex`, `internal_model`, `other` |
| data_residency | select | yes | `UK`, `EEA`, `US`, `mixed`, `unknown` |
| sub_processing_disclosed | boolean | yes | true if all sub-processors are documented |
| audit_rights_in_contract | boolean | yes | true if the contract grants third-party audit rights |

Drives `REG_OUTSOURCING_CONTROLS` (the only currently-seeded Deployment
dimension).

---

## Validation rules

Validation is a JSON object on each `form_fields.validation`. Generic
shapes:

```
{ "required": true }
{ "min": 0 }
{ "max": 1000 }
{ "pattern": "^[0-9]+$" }
{ "in": ["A", "B", "C"] }
```

The form renderer enforces these client-side. The submission endpoint
re-validates server-side. Both consume the same JSON.

---

## What this spec does *not* introduce

- **No new tables.** Form responses go into
  `deployment_records.form_responses_json`. Adding a field is a
  `form_fields` row; no schema change.
- **No per-field Python validators.** All validation is generic JSON.
- **No client-name field.** Per Block 1 finding F4, the `Client` entity
  is parked for Phase 3.

---

## Relationship to existing `prompts.ai_platform` and `prompts.output_destination`

The transitional split flagged in Block 1 finding F3 is the seam this
form lands on. The Deployment form's `model_provider` field and
`output_destination` field correspond to those columns; on submission
the deployment record's values dual-write to `prompts.ai_platform` and
`prompts.output_destination` to keep the legacy column populated until
post-Block-22 cleanup drops them.

---

*Block 12 complete. Block 13 builds the form.*
