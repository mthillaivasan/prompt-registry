# Haiku vs Sonnet — per-topic validate results

- Protocol: docs/CHECKLIST_DESIGN.md §B5
- Fixtures: 3 briefs × 4 topics each = 12 paired calls
- State-agreement rate: **11/12 = 92%**
- Red↔green disagreements: **0**
- Errors: **0**

## Recommendation

**SHIP HAIKU.** State agreement 92% meets the ≥90% threshold, no red↔green disagreements.

## Paired calls

### A — early stage · `topic_1_prompt_type`
- Answer: `Extraction`
- **Sonnet** (1.49s): `{"state": "green"}`
- **Haiku** (0.74s): `{"state": "green"}`
- Agree on state: yes

### A — early stage · `topic_6_data_points`
- Answer: `(empty)`
- **Sonnet** (6.92s): `{"state": "red", "question": "What specific data points do you need to extract from the prospectus?", "options": ["Fund name, ISIN, and launch date", "Investment objectives and strategy descriptions", "Fee structure including management fees and expense ratios", "Risk factors and regulatory disclosu`
- **Haiku** (2.36s): `{"state": "red", "question": "What specific data fields should the extraction prompt pull from the prospectus?", "options": ["Fund name, ISIN, fund type, inception date, and annual management fee", "Investment objective, key risk factors, and fund benchmark reference", "Minimum investment amount, sh`
- Agree on state: yes

### A — early stage · `topic_7_field_format`
- Answer: `(empty)`
- **Sonnet** (4.49s): `{"state": "red", "question": "What output format conventions should be applied to extracted data fields?", "options": ["Use ISO 8601 format for all dates (YYYY-MM-DD)", "Express monetary amounts with 2 decimal places and currency symbols", "Convert all percentages to decimal format (0.05 not 5%)", "`
- **Haiku** (5.29s): `{"state": "red", "question": "What per-field format rules should the AI apply when extracting data from the prospectus? For each field you named in topic_6_data_points, specify the output format convention (e.g., date format, number of decimal places, time zone, currency symbol, unit notation) or ex`
- Agree on state: yes

### A — early stage · `topic_9_confidence_traceability`
- Answer: `(empty)`
- **Sonnet** (4.5s): `{"state": "red", "question": "How should the AI handle confidence and traceability in its responses?", "options": ["Express uncertainty when information is unclear or missing", "Include page references for all extracted information", "Provide confidence scores for each piece of information", "Flag w`
- **Haiku** (3.08s): `{"state": "red", "question": "When the extraction model returns results from the prospectus, what confidence and traceability outputs do you need?", "options": ["Confidence scores for each extracted data point with direct page or section references", "A yes/no flag showing whether the model found th`
- Agree on state: yes

### B — mid stage · `topic_1_prompt_type`
- Answer: `Extraction`
- **Sonnet** (5.92s): `{"state": "green"}`
- **Haiku** (0.54s): `{"state": "green"}`
- Agree on state: yes

### B — mid stage · `topic_6_data_points`
- Answer: `subscription cut-off times`
- **Sonnet** (5.1s): `{"state": "red", "question": "What specific details about subscription cut-off times should be extracted from the prospectus?", "options": ["Cut-off time in HH:MM format from the dealing and settlement section", "Business day definitions and holiday calendars from terms and conditions", "Different c`
- **Haiku** (2.14s): `{"state": "red", "question": "What specific fields within subscription cut-off times do you need to extract from the prospectus?", "options": ["Cut-off time only (e.g. 14:00 or 2:00 PM)", "Cut-off time + timezone (e.g. 14:00 CET)", "Cut-off time + currency or share class identifier", "Cut-off time +`
- Agree on state: yes

### B — mid stage · `topic_7_field_format`
- Answer: `times as HH:MM`
- **Sonnet** (1.37s): `{"state": "green"}`
- **Haiku** (1.46s): `{"state": "amber", "suggestion": "You've specified time format as HH:MM, but haven't declared a time zone convention for the subscription cut-off times field.", "suggested_addition": "Add: 'times in HH:MM format, timezone: [UTC / London / New York / as stated in source document / other]'"}`
- Agree on state: NO

### B — mid stage · `topic_9_confidence_traceability`
- Answer: `Yes — page refs only`
- **Sonnet** (1.96s): `{"state": "amber", "suggestion": "You picked 'page refs only' but haven't specified how granular those references should be.", "suggested_addition": "with page numbers"}`
- **Haiku** (1.12s): `{"state": "amber", "suggestion": "You've chosen to include page references for traceability, but you haven't yet specified the granularity\u2014whether you need exact page numbers, section titles, or paragraph-level pointers.", "suggested_addition": "Please specify: page number, section title, or pa`
- Agree on state: yes

### C — late stage · `topic_1_prompt_type`
- Answer: `Extraction`
- **Sonnet** (1.29s): `{"state": "green"}`
- **Haiku** (0.56s): `{"state": "green"}`
- Agree on state: yes

### C — late stage · `topic_6_data_points`
- Answer: `subscription cut-off time (HH:MM with timezone, found in Dealing Procedures), ISIN (ISO 6166 format, found in Share Clas`
- **Sonnet** (2.03s): `{"state": "green"}`
- **Haiku** (0.93s): `{"state": "green"}`
- Agree on state: yes

### C — late stage · `topic_7_field_format`
- Answer: `times normalised to UTC offset like +01:00. amounts as float. ISINs validated as 12-char alphanumeric.`
- **Sonnet** (2.39s): `{"state": "amber", "suggestion": "You've specified formats for times, amounts, and ISINs, but your data points include minimum investment amount with currency code.", "suggested_addition": "currency codes as ISO 4217 3-letter format"}`
- **Haiku** (1.86s): `{"state": "amber", "suggestion": "You've specified formats for times, amounts, and ISINs, but the minimum investment amount field requires both a float AND a currency code \u2014 your current rule 'amounts as float' doesn't clarify how to handle or position the currency code in the output.", "sugges`
- Agree on state: yes

### C — late stage · `topic_9_confidence_traceability`
- Answer: `Yes — confidence + page/section ref per field`
- **Sonnet** (1.95s): `{"state": "amber", "suggestion": "You chose 'page/section ref per field' but haven't specified the granularity level for references", "suggested_addition": "page number level"}`
- **Haiku** (1.54s): `{"state": "amber", "suggestion": "You've selected 'page/section ref per field' but haven't yet specified whether you want page numbers, section titles, paragraph markers, or another granularity level.", "suggested_addition": "Please specify the granularity: page number, section title, paragraph iden`
- Agree on state: yes
