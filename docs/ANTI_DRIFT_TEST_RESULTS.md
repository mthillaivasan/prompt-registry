# Anti-drift rule — validate-topic results

- Protocol: docs/CHECKLIST_DESIGN.md §B4
- Fixtures: 5 cases with deliberate sibling-topic gaps
- Model: claude-sonnet-4-20250514
- PASS: **5/5**
- MIXED (manual review): **0/5**
- DRIFT: **0/5 = 0%**
- Errors: **0**

## Recommendation

**SHIP AS-IS.** Zero drift across all 5 cases; anti-drift rule holds.

## Case-by-case

### 1. focal=data_points (rich), sibling gap=output_format
- Focal: `topic_6_data_points` — `subscription cut-off time (HH:MM with timezone, Dealing Procedures section), ISIN (ISO 6166, Share Class Details), minim`
- Sibling gap: (absent from sibling_answers)
- Classification: **PASS (state=green, no probe emitted)**
- State: `green` · Latency: 1.3s
- Probe text: `(no probe)`

### 2. focal=field_format (answered), sibling gap=data_points
- Focal: `topic_7_field_format` — `times normalised to UTC offset. amounts as float without currency symbol.`
- Sibling gap: (absent from sibling_answers)
- Classification: **PASS**
- State: `red` · Latency: 4.08s
- Probe text: `you've specified formats for times and amounts, but what format rules should apply to the other data fields that will be extracted? | dates in iso format (yyyy-mm-dd) | text fields as-is with no normalisation | percentages as decimal values (e.g. 0.05 for 5%) | boolean values as true/false lowercase`

### 3. focal=confidence_traceability (structured pick), sibling gap=risk_tier
- Focal: `topic_9_confidence_traceability` — `Yes — page refs only`
- Sibling gap: (absent from sibling_answers)
- Classification: **PASS**
- State: `amber` · Latency: 2.1s
- Probe text: `you chose 'page refs only' for traceability | page number level`

### 4. focal=error_modes (answered briefly), sibling gap=target_system
- Focal: `topic_10_error_modes` — `partial document — skip the missing section and flag`
- Sibling gap: (absent from sibling_answers)
- Classification: **PASS**
- State: `amber` · Latency: 2.85s
- Probe text: `you've specified handling for partial documents, but other error modes like malformed pages or conflicting values across pages aren't addressed. | malformed pages — return error with page reference; conflicting values — flag all instances for manual review`

### 5. focal=null_handling (preset pick), sibling gap=data_points
- Focal: `topic_8_null_handling` — `null with confidence: low`
- Sibling gap: (absent from sibling_answers)
- Classification: **PASS**
- State: `red` · Latency: 4.5s
- Probe text: `what should the ai do when a requested field is not found in the prospectus? | return 'not found' for missing fields | return 'n/a' for missing fields | return empty string for missing fields | return 'information not available in source document' for missing fields | skip missing fields entirely in`
