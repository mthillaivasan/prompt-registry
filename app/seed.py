"""
Idempotent seed script.
Run once on startup via run_seed(). Safe to call on every restart.
"""

import uuid
from datetime import datetime, timezone

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import InjectionPattern, PromptComponent, PromptTemplate, ScoringDimension, User

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ── Scoring dimensions ────────────────────────────────────────────────────────

# Drop 3 Item 3: three-category classification for generator filtering.
# prompt_content = injected into the generated prompt body.
# wrapper_metadata = registry-side context about the prompt (owner, reviewer, cadence).
# registry_policy = registry-side rules (decommission trigger, audit programmes).
# See docs/CHECKLIST_DESIGN.md follow-up for the classification reasoning.
_CONTENT_TYPES_BY_CODE = {
    "REG_D1":          "wrapper_metadata",
    "REG_D2":          "prompt_content",
    "REG_D3":          "prompt_content",
    "REG_D4":          "wrapper_metadata",
    "REG_D5":          "wrapper_metadata",
    "REG_D6":          "registry_policy",
    "OWASP_LLM01":     "prompt_content",
    "OWASP_LLM02":     "prompt_content",
    "OWASP_LLM06":     "prompt_content",
    "OWASP_LLM08":     "prompt_content",
    "OWASP_LLM09":     "prompt_content",
    "NIST_GOVERN_1":   "wrapper_metadata",
    "NIST_MAP_1":      "wrapper_metadata",
    "NIST_MEASURE_1":  "registry_policy",
    "NIST_MANAGE_1":   "registry_policy",
    "ISO42001_6_1":    "registry_policy",
    "ISO42001_8_4":    "registry_policy",
}

_REG_D2_INSTRUCTIONAL_TEXT = (
    "Always end your output with a section titled AUDIT. Inside the AUDIT "
    "section, render each audit field provided to you on its own line, in "
    "the format 'field name: field value'. The audit fields and their "
    "values will be provided in the user message. Do not modify field "
    "names, do not omit any field, do not add commentary or explanation "
    "inside the AUDIT section, and do not omit the AUDIT section under any "
    "circumstances. If a field value is missing, render the literal "
    "placeholder string (such as '{generation_date}') in its place so the "
    "missing value is visible."
)

_DIMENSIONS = [
    # ── Regulatory — Blocking ────────────────────────────────────────────────
    dict(
        code="REG_D1", name="Human Oversight",
        framework="REGULATORY",
        source_reference="EU AI Act Article 14 / FINMA Circular",
        description="Assesses whether the prompt explicitly requires human review and defines the oversight mechanism.",
        score_5_criteria="Explicitly requires human review, names the oversight mechanism, defines what the reviewer assesses, and states the override path.",
        score_3_criteria="Human review is mentioned but the mechanism, reviewer role, or override path is only partially defined.",
        score_1_criteria="No human oversight requirement stated. AI output may be used without human review. Blocking defect.",
        is_mandatory=True, blocking_threshold=2, scoring_type="Blocking",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=10,
        tier=1, tier2_trigger=None,
    ),
    dict(
        code="REG_D2", name="Transparency",
        framework="REGULATORY",
        source_reference="EU AI Act Article 13 / FCA Consumer Duty",
        description="Assesses whether AI-generated output is clearly disclosed and limitations are communicated.",
        score_5_criteria="Output declared AI-generated, advisory not authoritative, limitations stated, AI identity not suppressed.",
        score_3_criteria="AI nature of output is implied but not explicit, or limitations are only partially stated.",
        score_1_criteria="No transparency requirement. Output could be mistaken for human-produced authoritative content. Blocking defect.",
        is_mandatory=True, blocking_threshold=2, scoring_type="Blocking",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=20,
        tier=2, tier2_trigger="Output visible externally OR deployment_target contains Agent",
        instructional_text=_REG_D2_INSTRUCTIONAL_TEXT,
    ),
    dict(
        code="REG_D3", name="Data Minimisation",
        framework="REGULATORY",
        source_reference="nDSG Article 6 / GDPR Article 5",
        description="Assesses whether the prompt limits data collection to what is necessary and declares the legal basis for personal data.",
        score_5_criteria="Purpose declared, only necessary data used, retention prohibition stated, legal basis declared if personal data.",
        score_3_criteria="Purpose is stated but data scope is broader than necessary, or retention/legal basis is only partially addressed.",
        score_1_criteria="No data minimisation controls. Personal data may be processed without declared purpose or legal basis. Blocking defect.",
        is_mandatory=True, blocking_threshold=2, scoring_type="Blocking",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=30,
        tier=2, tier2_trigger="Input type contains personal data OR prompt text contains personal/client data",
    ),
    dict(
        code="REG_D4", name="Audit Trail",
        framework="REGULATORY",
        source_reference="FINMA Circular 2023/1 / MAS TRM",
        description="Assesses whether reasoning is traceable and output is storable as an audit record with named human accountability.",
        score_5_criteria="Reasoning traceable, output storable as audit record, named human accountable before output used in regulated process.",
        score_3_criteria="Output can be stored but reasoning traceability or named accountability is only partially defined.",
        score_1_criteria="No audit trail requirement. Output not traceable or accountable. Blocking defect.",
        is_mandatory=True, blocking_threshold=2, scoring_type="Blocking",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=40,
        tier=1, tier2_trigger=None,
    ),
    dict(
        code="REG_D5", name="Operational Resilience",
        framework="REGULATORY",
        source_reference="FINMA Circular 2023/1 / FCA PS21/3",
        description="Assesses whether failure modes and fallback procedures are defined.",
        score_5_criteria="Failure modes defined, fallback declared, no single point of failure in critical process.",
        score_3_criteria="Some failure handling described but fallback is incomplete or a single point of failure exists.",
        score_1_criteria="No failure or fallback handling. Prompt creates single point of failure in critical process. Blocking defect.",
        is_mandatory=True, blocking_threshold=2, scoring_type="Blocking",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=50,
        tier=2, tier2_trigger="Risk tier is High OR prompt text contains critical",
    ),
    dict(
        code="REG_D6", name="Outsourcing Controls",
        framework="REGULATORY",
        source_reference="FINMA Circular 2018/3 / MAS Notice 655",
        description="Assesses whether data residency, sub-processing restrictions, and audit rights are documented for third-party deployments.",
        score_5_criteria="Data residency declared, sub-processing restricted, audit rights documented for third-party deployments.",
        score_3_criteria="Data residency is stated but sub-processing restrictions or audit rights are incomplete.",
        score_1_criteria="No outsourcing controls. Third-party deployment has no data residency or audit rights documentation. Blocking defect.",
        is_mandatory=True, blocking_threshold=2, scoring_type="Blocking",
        applies_to_types="[]",
        applies_if='{"deployment_target":["MS Copilot Agent Declarative","MS Copilot Agent Custom Engine","OpenAI","Multi-model"]}',
        is_active=True, sort_order=60,
        tier=2, tier2_trigger="Deployment target is not Internal or Claude",
    ),
    # ── OWASP LLM Top 10 — Advisory ──────────────────────────────────────────
    dict(
        code="OWASP_LLM01", name="Prompt Injection Resistance",
        framework="OWASP",
        source_reference="OWASP LLM Top 10 LLM01:2025",
        description="Assesses whether the prompt is designed to resist injection attacks and instructs the AI to treat user content as data only.",
        score_5_criteria="Delimiter wrapping declared. AI instructed to treat user content as data only. Injection resistance tested. Suspicious input escalation path defined.",
        score_3_criteria="Some injection resistance instruction present but delimiter wrapping or escalation path is missing.",
        score_1_criteria="No injection resistance. User content not isolated. AI may follow injected instructions.",
        is_mandatory=False, blocking_threshold=2, scoring_type="Advisory",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=110,
        tier=2, tier2_trigger="Input type includes user-supplied free text or form responses",
    ),
    dict(
        code="OWASP_LLM02", name="Sensitive Information Disclosure",
        framework="OWASP",
        source_reference="OWASP LLM Top 10 LLM02:2025",
        description="Assesses whether the AI is instructed not to reproduce system prompt contents or leak internal configuration.",
        score_5_criteria="AI instructed not to reproduce system prompt contents. Output does not leak configuration, keys, or internal process details.",
        score_3_criteria="Partial instruction to protect sensitive content but some categories of leakage are not addressed.",
        score_1_criteria="No instruction preventing system prompt reproduction or configuration leakage.",
        is_mandatory=False, blocking_threshold=2, scoring_type="Advisory",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=120,
        tier=3, tier2_trigger=None,
    ),
    dict(
        code="OWASP_LLM06", name="Excessive Agency",
        framework="OWASP",
        source_reference="OWASP LLM Top 10 LLM06:2025",
        description="Assesses whether the scope of AI actions is explicitly limited to prevent unintended downstream actions.",
        score_5_criteria="Scope of AI actions explicitly limited. AI cannot instruct downstream systems or initiate processes beyond declared output type.",
        score_3_criteria="Output scope is partially limited but edge cases or downstream system interactions are not fully addressed.",
        score_1_criteria="No scope limitation. AI may initiate downstream actions or produce instructions that trigger other systems.",
        is_mandatory=False, blocking_threshold=2, scoring_type="Advisory",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=130,
        tier=2, tier2_trigger="Deployment target contains Agent or Automation",
    ),
    dict(
        code="OWASP_LLM08", name="Overreliance",
        framework="OWASP",
        source_reference="OWASP LLM Top 10 LLM08:2025",
        description="Assesses whether output is explicitly advisory and human review is required before action.",
        score_5_criteria="Output explicitly advisory. Human review required before action. Confidence levels declared. Limitations stated.",
        score_3_criteria="Output is advisory but confidence levels or specific limitations are not fully declared.",
        score_1_criteria="Output presented as authoritative. No advisory qualification or human review requirement.",
        is_mandatory=False, blocking_threshold=2, scoring_type="Advisory",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=140,
        tier=1, tier2_trigger=None,
    ),
    dict(
        code="OWASP_LLM09", name="Misinformation",
        framework="OWASP",
        source_reference="OWASP LLM Top 10 LLM09:2025",
        description="Assesses whether the AI is instructed not to fabricate regulatory references and to declare uncertainty explicitly.",
        score_5_criteria="AI instructed not to fabricate regulatory references or citations. Uncertainty declared explicitly rather than inferred.",
        score_3_criteria="Some instruction against fabrication but uncertainty handling or citation verification is incomplete.",
        score_1_criteria="No instruction against fabrication. AI may produce false regulatory references presented as fact.",
        is_mandatory=False, blocking_threshold=2, scoring_type="Advisory",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=150,
        tier=1, tier2_trigger=None,
    ),
    # ── NIST AI RMF — Maturity ────────────────────────────────────────────────
    dict(
        code="NIST_GOVERN_1", name="Governance Accountability",
        framework="NIST",
        source_reference="NIST AI RMF Govern 1.1",
        description="Assesses whether the governance accountability chain is complete: named owner, approver, and review cadence.",
        score_5_criteria="Named owner, approver, and review cadence all declared. Accountability chain complete.",
        score_3_criteria="Owner and approver named but review cadence is absent or vague.",
        score_1_criteria="No named owner or approver. Accountability chain absent.",
        is_mandatory=False, blocking_threshold=2, scoring_type="Maturity",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=210,
        tier=3, tier2_trigger=None,
    ),
    dict(
        code="NIST_MAP_1", name="Context and Limitations",
        framework="NIST",
        source_reference="NIST AI RMF Map 1.1",
        description="Assesses whether context of use, intended user base, and known limitations are declared.",
        score_5_criteria="Context of use, intended user base, and known limitations all declared clearly.",
        score_3_criteria="Context of use is described but intended user base or limitations are only partially stated.",
        score_1_criteria="No context, user base, or limitation declarations present.",
        is_mandatory=False, blocking_threshold=2, scoring_type="Maturity",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=220,
        tier=3, tier2_trigger=None,
    ),
    dict(
        code="NIST_MEASURE_1", name="Output Quality Measurement",
        framework="NIST",
        source_reference="NIST AI RMF Measure 2.5",
        description="Assesses whether output quality measurement and monitoring over time is defined.",
        score_5_criteria="How output quality will be measured and monitored over time is fully defined.",
        score_3_criteria="Quality monitoring is mentioned but metrics or monitoring frequency are not specified.",
        score_1_criteria="No output quality measurement or monitoring defined.",
        is_mandatory=False, blocking_threshold=2, scoring_type="Maturity",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=230,
    ),
    dict(
        code="NIST_MANAGE_1", name="Decommission Trigger",
        framework="NIST",
        source_reference="NIST AI RMF Manage 1.3",
        description="Assesses whether a decommission or review trigger is declared.",
        score_5_criteria="Decommission or review trigger declared. Prompt cannot be used indefinitely without reassessment.",
        score_3_criteria="Review is implied by business context but no explicit trigger or decommission condition is stated.",
        score_1_criteria="No decommission or review trigger. Prompt may be used indefinitely without reassessment.",
        is_mandatory=False, blocking_threshold=2, scoring_type="Maturity",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=240,
        tier=3, tier2_trigger=None,
    ),
    # ── ISO 42001 — Alignment ─────────────────────────────────────────────────
    dict(
        code="ISO42001_6_1", name="Risk Assessment",
        framework="ISO42001",
        source_reference="ISO 42001 Clause 6.1",
        description="Assesses whether a risk assessment is present covering impact on individuals, operational risk, and mitigants.",
        score_5_criteria="Risk assessment present. Impact on individuals, operational risk, and mitigant documented.",
        score_3_criteria="Risk is acknowledged but impact assessment or mitigants are only partially documented.",
        score_1_criteria="No risk assessment. Prompt deployed without documented risk consideration.",
        is_mandatory=False, blocking_threshold=2, scoring_type="Alignment",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=310,
        tier=3, tier2_trigger=None,
    ),
    dict(
        code="ISO42001_8_4", name="Data Quality and Bias",
        framework="ISO42001",
        source_reference="ISO 42001 Clause 8.4",
        description="Assesses whether data sources, data quality requirements, and bias considerations are declared.",
        score_5_criteria="Data sources, data quality requirements, and bias considerations all declared.",
        score_3_criteria="Data sources are named but quality requirements or bias considerations are incomplete.",
        score_1_criteria="No data source, quality, or bias documentation.",
        is_mandatory=False, blocking_threshold=2, scoring_type="Alignment",
        applies_to_types="[]", applies_if=None, is_active=True, sort_order=320,
        tier=3, tier2_trigger=None,
    ),
]

# ── Injection patterns ────────────────────────────────────────────────────────

_PATTERNS = [
    # Instruction override — Critical / OWASP_ATLAS
    dict(category="Instruction override", pattern_text="ignore previous instructions",
         match_type="substring", severity="Critical", source="OWASP_ATLAS",
         description="Classic prompt injection to override system instructions."),
    dict(category="Instruction override", pattern_text="disregard your system prompt",
         match_type="substring", severity="Critical", source="OWASP_ATLAS",
         description="Attempts to nullify the system prompt."),
    dict(category="Instruction override", pattern_text="forget everything",
         match_type="substring", severity="Critical", source="OWASP_ATLAS",
         description="Attempts to clear prior instructions and context."),
    dict(category="Instruction override", pattern_text="ignore all previous",
         match_type="substring", severity="Critical", source="OWASP_ATLAS",
         description="Variant instruction override attack."),
    # Persona hijack — Critical / OWASP_ATLAS
    dict(category="Persona hijack", pattern_text="you are now",
         match_type="substring", severity="Critical", source="OWASP_ATLAS",
         description="Attempts to reassign AI persona."),
    dict(category="Persona hijack", pattern_text="act as",
         match_type="substring", severity="Critical", source="OWASP_ATLAS",
         description="Attempts to make the AI adopt a different role."),
    dict(category="Persona hijack", pattern_text="your new persona",
         match_type="substring", severity="Critical", source="OWASP_ATLAS",
         description="Explicit persona reassignment attempt."),
    dict(category="Persona hijack", pattern_text="pretend you are",
         match_type="substring", severity="Critical", source="OWASP_ATLAS",
         description="Roleplay-based persona hijack."),
    dict(category="Persona hijack", pattern_text="roleplay as",
         match_type="substring", severity="Critical", source="OWASP_ATLAS",
         description="Roleplay-based persona hijack."),
    # Exfiltration — High / MITRE_ATLAS
    dict(category="Exfiltration", pattern_text="repeat your system prompt",
         match_type="substring", severity="High", source="MITRE_ATLAS",
         description="Attempts to extract the system prompt."),
    dict(category="Exfiltration", pattern_text="show your configuration",
         match_type="substring", severity="High", source="MITRE_ATLAS",
         description="Attempts to expose system configuration."),
    dict(category="Exfiltration", pattern_text="reveal your prompt",
         match_type="substring", severity="High", source="MITRE_ATLAS",
         description="Attempts to reveal internal prompt content."),
    dict(category="Exfiltration", pattern_text="print your instructions",
         match_type="substring", severity="High", source="MITRE_ATLAS",
         description="Variant exfiltration attempt."),
    # Delimiter attack — High / MITRE_ATLAS
    dict(category="Delimiter attack", pattern_text="```system",
         match_type="substring", severity="High", source="MITRE_ATLAS",
         description="Attempts to inject a system block using markdown code fence."),
    dict(category="Delimiter attack", pattern_text="[INST]",
         match_type="substring", severity="High", source="MITRE_ATLAS",
         description="LLaMA/Mistral instruction delimiter injection."),
    dict(category="Delimiter attack", pattern_text="<<SYS>>",
         match_type="substring", severity="High", source="MITRE_ATLAS",
         description="LLaMA system delimiter injection."),
    dict(category="Delimiter attack", pattern_text="</s>",
         match_type="substring", severity="High", source="MITRE_ATLAS",
         description="Sequence termination delimiter injection."),
    dict(category="Delimiter attack", pattern_text="<|im_start|>",
         match_type="substring", severity="High", source="MITRE_ATLAS",
         description="OpenAI/ChatML conversation delimiter injection."),
    # Unicode manipulation — High / INTERNAL
    dict(category="Unicode manipulation", pattern_text="\u200b",
         match_type="unicode_range", severity="High", source="INTERNAL",
         description="Zero-width space (U+200B) used to hide content or bypass filters."),
    dict(category="Unicode manipulation", pattern_text="\u200c",
         match_type="unicode_range", severity="High", source="INTERNAL",
         description="Zero-width non-joiner (U+200C) used to hide content or bypass filters."),
    dict(category="Unicode manipulation", pattern_text="\u202e",
         match_type="unicode_range", severity="High", source="INTERNAL",
         description="Right-to-left override (U+202E) used to reverse displayed text and deceive reviewers."),
    # Structural anomaly — Medium / INTERNAL
    dict(category="Structural anomaly", pattern_text=r"\n{5,}",
         match_type="regex", severity="Medium", source="INTERNAL",
         description="Five or more consecutive newlines — may indicate hidden content or section injection."),
    dict(category="Structural anomaly", pattern_text=r"\S{500,}",
         match_type="regex", severity="Medium", source="INTERNAL",
         description="500+ characters with no spaces — may indicate encoded or obfuscated content."),
    dict(category="Structural anomaly", pattern_text=r"[A-Za-z0-9+/]{100,}={0,2}",
         match_type="regex", severity="Medium", source="INTERNAL",
         description="Base64-encoded content over 100 characters — may hide injected instructions."),
]


# ── Seed functions ────────────────────────────────────────────────────────────

def _seed_admin(db: Session) -> None:
    if db.query(User).filter(User.email == "admin@promptregistry.local").first():
        return
    db.add(User(
        user_id=_uuid(),
        email="admin@promptregistry.local",
        name="System Administrator",
        role="Admin",
        password_hash=_pwd.hash("ChangeMe123!"),
        is_active=True,
        created_at=_utcnow(),
    ))
    db.commit()


def _seed_dimensions(db: Session) -> None:
    if db.query(ScoringDimension).count() == 0:
        for d in _DIMENSIONS:
            db.add(ScoringDimension(dimension_id=_uuid(), **d))
        db.commit()
    _sync_instructional_text(db)
    _sync_content_types(db)


def _sync_instructional_text(db: Session) -> None:
    # Targeted per-dimension sync. See PHASE2.md "Dimension migration pattern".
    # Only touches instructional_text — other admin-editable fields are preserved.
    row = db.query(ScoringDimension).filter_by(code="REG_D2").first()
    if row and row.instructional_text != _REG_D2_INSTRUCTIONAL_TEXT:
        row.instructional_text = _REG_D2_INSTRUCTIONAL_TEXT
        db.commit()


def _sync_content_types(db: Session) -> None:
    # Idempotent classification sync — runs every startup, updates rows whose
    # content_type differs from the map. Same pattern as _sync_instructional_text.
    changed = False
    for code, content_type in _CONTENT_TYPES_BY_CODE.items():
        row = db.query(ScoringDimension).filter_by(code=code).first()
        if row and row.content_type != content_type:
            row.content_type = content_type
            changed = True
    if changed:
        db.commit()


def _seed_patterns(db: Session) -> None:
    if db.query(InjectionPattern).count() > 0:
        return
    for p in _PATTERNS:
        db.add(InjectionPattern(pattern_id=_uuid(), is_active=True, **p))
    db.commit()


def _seed_components(db: Session) -> None:
    if db.query(PromptComponent).count() > 0:
        return
    from services.prompt_components import INPUT_HANDLERS, OUTPUT_HANDLERS, REGULATORY_COMPONENTS, BEHAVIOUR_COMPONENTS
    seen_codes = set()
    order = 0
    for key, h in INPUT_HANDLERS.items():
        if h["code"] in seen_codes:
            continue
        seen_codes.add(h["code"])
        order += 10
        db.add(PromptComponent(code=h["code"], category="InputHandling", name=h["name"], description=key, component_text=h["text"], sort_order=order))
    for key, h in OUTPUT_HANDLERS.items():
        if h["code"] in seen_codes:
            continue
        seen_codes.add(h["code"])
        order += 10
        db.add(PromptComponent(code=h["code"], category="OutputFormat", name=h["name"], description=key, component_text=h["text"], example_output=h.get("example_output"), sort_order=order))
    for code, c in REGULATORY_COMPONENTS.items():
        seen_codes.add(c["code"])
        order += 10
        db.add(PromptComponent(code=c["code"], category="RegulatoryGuardrail", name=c["name"], description=code, component_text=c["text"], applicable_dimensions=f'["{code}"]', sort_order=order))
    for code, c in BEHAVIOUR_COMPONENTS.items():
        seen_codes.add(code)
        order += 10
        db.add(PromptComponent(code=code, category="Behavioural", name=c["name"], description=c.get("trigger", "always"), component_text=c["text"], sort_order=order))
    db.commit()


_TEMPLATES = [
    dict(code="T01", name="Governance Assessment", description="Structured governance review with regulatory scoring and compliance flags",
         use_case="Committee papers, project approvals, change governance", prompt_type="Governance", risk_tier="Limited",
         input_type="Form responses", output_type="Structured assessment",
         component_codes='["COMP-IN-02","COMP-OUT-01","COMP-REG-D1","COMP-REG-D2","COMP-REG-D4","COMP-BEH-01","COMP-BEH-05"]',
         output_example="## Assessment Summary\nOverall: APPROVE TO PROCEED\n\n## Scores\n| Dimension | Score | Finding |\n|---|---|---|\n| Strategic alignment | 4/5 | Clear business case |\n| Risk | 3/5 | Mitigation plan incomplete |\n\n## Open Questions\n1. Who is the named human reviewer?\n\n## Regulatory Flags\n- EU AI Act: Human oversight mechanism not declared",
         gold_standard_grade="B+", sort_order=10),
    dict(code="T02", name="FINMA Circular Summary", description="Plain language summary of regulatory circulars with obligation flags",
         use_case="Regulatory change management, compliance briefings", prompt_type="Summarisation", risk_tier="Limited",
         input_type="Document or report", output_type="Executive narrative",
         component_codes='["COMP-IN-01","COMP-OUT-02","COMP-REG-D1","COMP-REG-D2","COMP-BEH-01","COMP-BEH-02"]',
         output_example="Three paragraph plain language summary. First paragraph: situation and key changes. Second: implications for the institution. Third: recommended actions with deadlines.",
         gold_standard_grade="B+", sort_order=20),
    dict(code="T03", name="Risk Register Executive Summary", description="CRO-level risk summary with ratings and trends",
         use_case="Board reporting, risk committee papers", prompt_type="Summarisation", risk_tier="Limited",
         input_type="Data table", output_type="Executive narrative",
         component_codes='["COMP-IN-03","COMP-OUT-02","COMP-REG-D1","COMP-REG-D4","COMP-BEH-01","COMP-BEH-02"]',
         output_example="Top 5 risks with rating, trend, mitigation status. CRO-level language suitable for board presentation.",
         gold_standard_grade="B", sort_order=30),
    dict(code="T04", name="Settlement Failure Communication", description="Professional email draft for settlement issues with no-liability language",
         use_case="Operations settlement failures, counterparty communication", prompt_type="Comms", risk_tier="Limited",
         input_type="Free text", output_type="Draft comms",
         component_codes='["COMP-IN-04","COMP-OUT-04","COMP-REG-D1","COMP-REG-D2","COMP-BEH-03","COMP-BEH-04"]',
         output_example="Subject: Settlement Query — [Trade Ref]\n\nDear [name],\n\n[body with no liability language]\n\n--- HUMAN REVIEW REQUIRED ---",
         gold_standard_grade="B", sort_order=40),
    dict(code="T05", name="Trade Confirmation Data Extraction", description="Structured data extraction from trade confirmations with confidence scoring",
         use_case="Operations trade processing, STP enrichment", prompt_type="Extraction", risk_tier="High",
         input_type="Document or report", output_type="Data extraction",
         component_codes='["COMP-IN-01","COMP-OUT-03","COMP-REG-D1","COMP-REG-D3","COMP-REG-D4","COMP-BEH-01","COMP-BEH-02"]',
         output_example='{"counterparty": {"value": "ABC Bank", "confidence": "high"}, "ISIN": {"value": null, "confidence": "low"}, "settlement_date": {"value": "2026-04-20", "confidence": "high"}}',
         gold_standard_grade="B+", sort_order=50),
    dict(code="T06", name="Compliance Gap Analysis", description="Regulatory gap identification with remediation steps",
         use_case="Regulatory readiness, audit preparation", prompt_type="Risk Review", risk_tier="High",
         input_type="Document or report", output_type="Flag report",
         component_codes='["COMP-IN-01","COMP-OUT-06","COMP-REG-D1","COMP-REG-D2","COMP-REG-D4","COMP-BEH-01","COMP-BEH-05"]',
         output_example="- SEVERITY: High\n  FINDING: No human oversight declared\n  REFERENCE: EU AI Act Article 14\n  ACTION: Add oversight clause to prompt",
         gold_standard_grade="A-", sort_order=60),
    dict(code="T07", name="Meeting Notes Summarisation", description="Decision and action extraction from meeting notes",
         use_case="Committee meetings, project stand-ups", prompt_type="Summarisation", risk_tier="Minimal",
         input_type="Free text", output_type="Executive narrative",
         component_codes='["COMP-IN-04","COMP-OUT-02","COMP-REG-D1","COMP-BEH-01"]',
         output_example="Decisions: [numbered list]\nActions: [owner, action, deadline]\nParking lot: [deferred items]",
         gold_standard_grade="B", sort_order=70),
    dict(code="T08", name="Policy Document Q&A", description="Direct answers from policy documents with page references",
         use_case="Policy queries, compliance helpdesk", prompt_type="Analysis", risk_tier="Minimal",
         input_type="Document or report", output_type="Executive narrative",
         component_codes='["COMP-IN-01","COMP-OUT-02","COMP-REG-D1","COMP-BEH-01","COMP-BEH-02","COMP-BEH-05"]',
         output_example="Answer: [direct answer]\nSource: [page/section reference]\nNote: [caveats or if not found in document]",
         gold_standard_grade="B", sort_order=80),
    dict(code="T09", name="Incident Report Drafting", description="Structured incident report with timeline and root cause",
         use_case="Operational incidents, near-miss reporting", prompt_type="Governance", risk_tier="Limited",
         input_type="Free text", output_type="Structured assessment",
         component_codes='["COMP-IN-04","COMP-OUT-01","COMP-REG-D1","COMP-REG-D4","COMP-BEH-04"]',
         output_example="## Assessment Summary\nOverall: REFER FOR REVIEW\n\n## Timeline\n[chronological events]\n\n## Root Cause\n[analysis]\n\n## Remediation\n[steps]",
         gold_standard_grade="B", sort_order=90),
    dict(code="T10", name="Client Communication Review", description="Review client-facing communications for tone, accuracy, and compliance",
         use_case="Client letters, marketing material review", prompt_type="Risk Review", risk_tier="High",
         input_type="Document or report", output_type="Flag report",
         component_codes='["COMP-IN-01","COMP-OUT-06","COMP-REG-D1","COMP-REG-D2","COMP-BEH-03","COMP-BEH-04"]',
         output_example="- SEVERITY: Medium\n  FINDING: Tone implies certainty where outcome is uncertain\n  REFERENCE: FCA Consumer Duty\n  ACTION: Reword paragraph 3 to include advisory qualification",
         gold_standard_grade="B+", sort_order=100),
]


def _seed_templates(db: Session) -> None:
    if db.query(PromptTemplate).count() > 0:
        return
    for t in _TEMPLATES:
        db.add(PromptTemplate(template_id=_uuid(), is_active=True, **t))
    db.commit()


def run_seed() -> None:
    db = SessionLocal()
    try:
        _seed_admin(db)
        _seed_dimensions(db)
        _seed_patterns(db)
        _seed_components(db)
        _seed_templates(db)
    finally:
        db.close()
