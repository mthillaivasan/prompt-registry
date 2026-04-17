"""
Idempotent seed script.
Run once on startup via run_seed(). Safe to call on every restart.
"""

import uuid
from datetime import datetime, timezone

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import InjectionPattern, ScoringDimension, User

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ── Scoring dimensions ────────────────────────────────────────────────────────

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
    if db.query(ScoringDimension).count() > 0:
        return
    for d in _DIMENSIONS:
        db.add(ScoringDimension(dimension_id=_uuid(), **d))
    db.commit()


def _seed_patterns(db: Session) -> None:
    if db.query(InjectionPattern).count() > 0:
        return
    for p in _PATTERNS:
        db.add(InjectionPattern(pattern_id=_uuid(), is_active=True, **p))
    db.commit()


def run_seed() -> None:
    db = SessionLocal()
    try:
        _seed_admin(db)
        _seed_dimensions(db)
        _seed_patterns(db)
    finally:
        db.close()
