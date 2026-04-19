"""Per-topic rubric registry for the Step 1 topic-checklist (Phase A).

Only Extraction is specced in Phase A. Other prompt_types (Classification,
Summarisation, Comparison, etc.) are defined in follow-up design sessions;
validate_topic returns 501 for those until the relevant registry lands.

Each rubric entry drives one topic card and the Claude coaching call that
reviews the user's answer. Shape:

    {
        "name":              user-visible topic name
        "interaction":       "structured" | "prose"
        "options":           (structured only) list[str] of fixed picks; the
                             last entry MAY be a free-text fallback (e.g.
                             "Other" — treat with care at the UI layer)
        "rag_rules":         plain-English description of when the topic is
                             red / amber / green (used in the system prompt
                             so Claude can classify consistently)
        "rubric_fragment":   prose block inserted into the shared system
                             prompt at the {=== TOPIC ===} marker, describing
                             what to probe on (prose topics) or what a
                             "complete" answer looks like (structured topics)
    }

See docs/CHECKLIST_DESIGN.md §B1, §B2 for the source design.
"""

from app.schemas import PromptType


EXTRACTION_RUBRICS: dict[str, dict] = {
    "topic_1_prompt_type": {
        "name": "Prompt Type",
        "interaction": "structured",
        "options": [
            "Governance", "Analysis", "Comms", "Classification",
            "Summarisation", "Extraction", "Comparison", "Risk Review",
        ],
        "rag_rules": "red until picked; green on any pick; no amber state.",
        "rubric_fragment": (
            "This topic is a structured pick. If the user has picked a value from the allowed "
            "options, return state=green. Otherwise return state=red with a short question "
            "prompting the user to pick. Do not probe."
        ),
    },
    "topic_2_source_doc": {
        "name": "Source document type",
        "interaction": "structured",
        "options": [
            "Prospectus", "Policy", "Circular", "Regulatory filing", "Report",
            "Contract", "Email thread", "Form responses", "Data table", "Free text",
            "Other",
        ],
        "rag_rules": (
            "red until picked; green on a non-Other pick; amber if 'Other' is selected "
            "without a free-text follow-up."
        ),
        "rubric_fragment": (
            "Structured pick. Green on a concrete document type. Amber only if the user "
            "picked 'Other' and the answer is empty or generic — prompt them to name the "
            "specific document type."
        ),
    },
    "topic_3_output_format": {
        "name": "Output format",
        "interaction": "structured",
        "options": [
            "JSON object", "Table/CSV", "Markdown extraction report",
            "Flag report", "Data extraction payload", "Other",
        ],
        "rag_rules": "red until picked; green on any concrete pick.",
        "rubric_fragment": (
            "Structured pick. Green on any concrete output format. If 'Other' is picked "
            "without free-text, amber."
        ),
    },
    "topic_4_target_system": {
        "name": "Target system (where the output goes)",
        "interaction": "structured",
        "options": [
            "Simcorp", "Temenos", "Charles River", "Bloomberg AIM", "Murex",
            "Internal spreadsheet", "Downstream AI or pipeline",
            "Advisory only — no system", "Other",
        ],
        "rag_rules": (
            "red until picked; amber if 'Other' with free-text < 3 words; green otherwise."
        ),
        "rubric_fragment": (
            "Structured pick for the business system receiving the output. This is NOT "
            "the AI platform (see topic_4b_ai_platform for that). Green on any concrete "
            "pick. Amber if 'Other' with too-vague free-text."
        ),
    },
    "topic_4b_ai_platform": {
        "name": "AI platform (what runs the prompt)",
        "interaction": "structured",
        "options": [
            "Claude", "MS Copilot — Declarative", "MS Copilot — Custom Engine",
            "OpenAI", "Multi-model", "Other",
        ],
        "rag_rules": "auto-green on default (Claude); stays green on any valid pick.",
        "rubric_fragment": (
            "Structured pick for the AI platform running the prompt. Defaults to Claude. "
            "Return state=green for any pick in the allowed list."
        ),
    },
    "topic_5_risk_tier": {
        "name": "Risk tier",
        "interaction": "structured",
        "options": ["Minimal", "Limited", "High", "Prohibited"],
        "rag_rules": (
            "red until picked; amber if High/Prohibited picked but no critical-process "
            "or personal-data trigger is evident in sibling prose topics; green otherwise."
        ),
        "rubric_fragment": (
            "Structured pick from {Minimal, Limited, High, Prohibited}. Cross-check "
            "against sibling prose topics: if the user picked High or Prohibited but no "
            "sibling answer mentions personal data, critical operations, or regulatory "
            "reporting, return state=amber with a question asking what triggered the "
            "elevated tier. Otherwise green."
        ),
    },
    "topic_6_data_points": {
        "name": "Data points to extract",
        "interaction": "prose",
        "options": None,
        "rag_rules": (
            "red if < 1 field named; amber if 1-2 fields OR any field missing type/source; "
            "green if >= 3 fields each with name + type + rough source location."
        ),
        "rubric_fragment": (
            "Evaluate whether the user has named enough data points to build an extraction "
            "prompt. For each mentioned field, the user should state: (a) field name, "
            "(b) expected type or form (date, currency, name, HH:MM time, ISIN, etc.), "
            "(c) roughly where it appears in the source document. "
            "If < 1 field: state=red with a question asking what to extract, options drawn "
            "from likely fields based on the source document type in sibling_answers. "
            "If 1-2 fields, or any field missing type/source: state=amber with a suggestion "
            "naming the specific field that needs more detail. "
            "If >= 3 fields each complete: state=green."
        ),
    },
    "topic_7_field_format": {
        "name": "Per-field format / normalisation",
        "interaction": "prose",
        "options": None,
        "rag_rules": (
            "red if the data-points topic is non-empty and no formats are given; "
            "amber if some fields have formats but not all; green if every named field "
            "has a format rule OR explicit 'output as-is, no normalisation'."
        ),
        "rubric_fragment": (
            "Evaluate per-field output format rules. Cross-reference the field list from "
            "sibling topic_6_data_points. For each field there, the user should state a "
            "format convention (time zone form, decimal format, date format, unit "
            "conventions) OR explicitly declare 'no normalisation'. "
            "Red if topic_6 has fields but this topic is empty. "
            "Amber if some fields specified, not all — name which specific field lacks a "
            "format rule. "
            "Green if every topic_6 field has a format convention."
        ),
    },
    "topic_8_null_handling": {
        "name": "Null / missing handling",
        "interaction": "prose",
        "options": [
            "null with confidence: low",
            "explicit 'not-found' marker",
            "skip the record",
            "raise an error",
        ],
        "rag_rules": "red until answered; green on any explicit policy (preset or prose).",
        "rubric_fragment": (
            "Evaluate the user's policy for fields not found in the source document. "
            "Acceptable answers: a preset policy from the four options, or a prose "
            "description of equivalent specificity. "
            "Red if empty or generic ('handle missing fields'). "
            "Green on any explicit policy."
        ),
    },
    "topic_9_confidence_traceability": {
        "name": "Confidence and traceability",
        "interaction": "structured",
        "options": [
            "Yes — confidence + page/section ref per field",
            "Yes — confidence only",
            "Yes — page refs only",
            "No — values only",
        ],
        "rag_rules": (
            "red until answered; amber if 'page refs' option picked without granularity "
            "specified; green otherwise."
        ),
        "rubric_fragment": (
            "Structured pick with a potential amber follow-up. If the user picked 'page "
            "refs' and has not yet specified granularity (page number / section title / "
            "paragraph), state=amber with a follow-up question. Otherwise green."
        ),
    },
    "topic_10_error_modes": {
        "name": "Error / exception modes",
        "interaction": "prose",
        "options": None,
        "rag_rules": (
            "red if empty; amber if one mode stated; green if >= 2 modes OR explicit "
            "'out of scope, fail loudly' policy."
        ),
        "rubric_fragment": (
            "Evaluate handling of error / exception modes: partial document, malformed "
            "pages, conflicting values across pages. "
            "Red if empty. Amber if exactly one mode is handled. Green if >= 2 modes "
            "OR an explicit 'out of scope — fail loudly' policy."
        ),
    },
}


_RUBRICS_BY_TYPE: dict[str, dict[str, dict]] = {
    "Extraction": EXTRACTION_RUBRICS,
}


class UnsupportedPromptTypeError(Exception):
    """Raised when validate_topic is called for a prompt_type without a rubric set."""


class UnknownTopicError(Exception):
    """Raised when validate_topic is called with a topic_id not in the relevant rubric set."""


def get_rubric(prompt_type: PromptType, topic_id: str) -> dict:
    rubrics = _RUBRICS_BY_TYPE.get(prompt_type)
    if rubrics is None:
        raise UnsupportedPromptTypeError(prompt_type)
    if topic_id not in rubrics:
        raise UnknownTopicError(topic_id)
    return rubrics[topic_id]


def has_rubric_set(prompt_type: str) -> bool:
    return prompt_type in _RUBRICS_BY_TYPE


# ── System-prompt builder ────────────────────────────────────────────────────
#
# One shared template; the {rubric_fragment} and {rag_rules} markers are filled
# by build_validate_topic_system_prompt() for the focal topic. Anti-drift rule
# is verbatim from docs/CHECKLIST_DESIGN.md §B4. Response shape uses labelled
# placeholders (not "...") to avoid example leakage — same anti-leakage
# convention as restructure_brief.

_VALIDATE_TOPIC_TEMPLATE = """\
You are a coaching reviewer helping a prompt engineer shape one topic of a brief for an AI prompt in a regulated financial services firm. The brief is being built topic-by-topic; you review only one topic at a time.

=== ANTI-DRIFT RULE — READ CAREFULLY ===
You are reviewing ONLY the focal topic. Sibling answers are provided for context — you may reference them to understand the brief's shape, but you MUST NOT probe gaps in sibling topics. If a gap exists in a sibling topic, silently ignore it. The user will address sibling topics separately.

=== FOCAL TOPIC ===
{topic_name}

=== RAG STATE RULES FOR THIS TOPIC ===
{rag_rules}

=== COACHING INSTRUCTIONS FOR THIS TOPIC ===
{rubric_fragment}

=== RESPONSE SHAPE ===
Return one JSON object. Use these keys exactly. Do not add keys.

If state is green:
{"state": "green"}

If state is amber (an inferable gap remains; propose a specific addition):
{"state": "amber", "suggestion": "<one sentence referencing the user's own words>", "suggested_addition": "<the specific phrase to add>"}

If state is red (a material gap remains; ask one targeted question):
{"state": "red", "question": "<one targeted question grounded in the focal topic>", "options": ["<option 1>", "<option 2>", "<option 3>", "<option 4>", "<option 5>", "<option 6>"], "free_text_placeholder": "<short hint for free-text entry>"}

OPTIONS RULES when state is red:
- Exactly 6 options
- Orthogonal — no option may be a subset, rewording, or special case of another
- Each option is a complete phrase the user could pick as their answer, not a category label
- Grounded in the specific brief — do not paraphrase generic prompt-engineering concerns
- The user may pick more than one at the UI layer, so options should plausibly combine where the real workflow has multiple concerns

Return ONLY valid JSON. No preamble, no markdown fences."""


_REFERENCE_EXAMPLES_HEADER = (
    "=== REFERENCE EXAMPLES (for illustration only — do not copy verbatim) ===\n"
    "These are excerpts from other prompts in the registry that have addressed "
    "the focal topic. They are context for your coaching, not a script. Do not "
    "quote them at the user. Do not probe gaps just because the user's brief "
    "does not match them.\n\n"
)


def _format_reference_examples(examples) -> str:
    blocks = []
    for ex in examples or []:
        title = getattr(ex, "title", None) or (ex.get("title") if isinstance(ex, dict) else None)
        excerpt = getattr(ex, "excerpt", None) or (ex.get("excerpt") if isinstance(ex, dict) else None)
        if not title or not excerpt:
            continue
        blocks.append(f"### {title}\n{excerpt}")
    return "\n\n".join(blocks)


def build_validate_topic_system_prompt(prompt_type: str, topic_id: str, reference_examples=None) -> str:
    # .replace() rather than .format() — the template contains literal JSON
    # braces (the response-shape examples) that str.format would try to
    # interpret as format specifiers.
    rubric = get_rubric(prompt_type, topic_id)
    base = (
        _VALIDATE_TOPIC_TEMPLATE
        .replace("{topic_name}", rubric["name"])
        .replace("{rag_rules}", rubric["rag_rules"])
        .replace("{rubric_fragment}", rubric["rubric_fragment"])
    )

    if not reference_examples:
        return base

    formatted = _format_reference_examples(reference_examples)
    if not formatted:
        return base

    # Insert the reference-examples block between COACHING INSTRUCTIONS and
    # RESPONSE SHAPE — it is context for the coaching, not part of the
    # response contract.
    marker = "=== RESPONSE SHAPE ==="
    insertion = _REFERENCE_EXAMPLES_HEADER + formatted + "\n\n"
    return base.replace(marker, insertion + marker, 1)
