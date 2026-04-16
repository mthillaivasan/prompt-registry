import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class User(Base):
    __tablename__ = "users"

    user_id = Column(String(36), primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(String, nullable=False, default=_utcnow)
    last_login_at = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "role IN ('Author','Approver','Auditor','Admin','SuperAdmin')",
            name="ck_users_role",
        ),
    )


class ScoringDimension(Base):
    __tablename__ = "scoring_dimensions"

    dimension_id = Column(String(36), primary_key=True, default=_uuid)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    framework = Column(String, nullable=False)
    source_reference = Column(String, nullable=True)
    description = Column(Text, nullable=False)
    score_5_criteria = Column(Text, nullable=False)
    score_3_criteria = Column(Text, nullable=False)
    score_1_criteria = Column(Text, nullable=False)
    is_mandatory = Column(Boolean, nullable=False, default=False)
    blocking_threshold = Column(Integer, nullable=False, default=2)
    applies_to_types = Column(Text, nullable=False, default="[]")  # JSON array
    applies_if = Column(Text, nullable=True)                        # JSON object or null
    scoring_type = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    tier = Column(Integer, nullable=False, default=3)  # 1=always, 2=conditional, 3=optional
    tier2_trigger = Column(Text, nullable=True)  # JSON: condition description for tier 2

    __table_args__ = (
        CheckConstraint(
            "framework IN ('REGULATORY','OWASP','NIST','ISO42001')",
            name="ck_sd_framework",
        ),
        CheckConstraint(
            "scoring_type IN ('Blocking','Advisory','Maturity','Alignment')",
            name="ck_sd_scoring_type",
        ),
        CheckConstraint(
            "tier IN (1, 2, 3)",
            name="ck_sd_tier",
        ),
    )


class InjectionPattern(Base):
    __tablename__ = "injection_patterns"

    pattern_id = Column(String(36), primary_key=True, default=_uuid)
    category = Column(String, nullable=False)
    pattern_text = Column(Text, nullable=False)
    match_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    source = Column(String, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "category IN ('Instruction override','Persona hijack','Exfiltration',"
            "'Delimiter attack','Unicode manipulation','Structural anomaly')",
            name="ck_ip_category",
        ),
        CheckConstraint(
            "match_type IN ('substring','regex','unicode_range')",
            name="ck_ip_match_type",
        ),
        CheckConstraint(
            "severity IN ('Critical','High','Medium')",
            name="ck_ip_severity",
        ),
        CheckConstraint(
            "source IN ('OWASP_ATLAS','MITRE_ATLAS','INTERNAL')",
            name="ck_ip_source",
        ),
    )


class Prompt(Base):
    __tablename__ = "prompts"

    prompt_id = Column(String(36), primary_key=True, default=_uuid)
    title = Column(String, nullable=False)
    prompt_type = Column(String, nullable=False)
    deployment_target = Column(String, nullable=False)
    input_type = Column(String, nullable=False)
    output_type = Column(String, nullable=False)
    risk_tier = Column(String, nullable=False)
    owner_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    approver_id = Column(String(36), ForeignKey("users.user_id"), nullable=True)
    status = Column(String, nullable=False, default="Draft")
    review_cadence_days = Column(Integer, nullable=False, default=365)
    next_review_date = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=_utcnow)
    updated_at = Column(String, nullable=False, default=_utcnow)

    __table_args__ = (
        CheckConstraint(
            "risk_tier IN ('Minimal','Limited','High','Prohibited')",
            name="ck_prompts_risk_tier",
        ),
        CheckConstraint(
            "status IN ('Draft','Active','Review Required','Suspended','Retired')",
            name="ck_prompts_status",
        ),
        CheckConstraint(
            "prompt_type IN ('Governance','Analysis','Comms','Classification',"
            "'Summarisation','Extraction','Comparison','Risk Review')",
            name="ck_prompts_type",
        ),
    )


class UpgradeProposal(Base):
    """
    Created by the system before the user sees suggestions.
    source_version_id and resulting_version_id reference prompt_versions
    but are stored as plain strings to avoid the circular FK that SQLite
    cannot resolve at DDL time. Integrity enforced at application level;
    full FK constraints are present in migrations/001_initial.sql for Postgres.
    """
    __tablename__ = "upgrade_proposals"

    proposal_id = Column(String(36), primary_key=True, default=_uuid)
    prompt_id = Column(String(36), ForeignKey("prompts.prompt_id"), nullable=True)
    source_version_id = Column(String(36), nullable=True)       # FK prompt_versions (circular)
    proposed_at = Column(String, nullable=False, default=_utcnow)
    proposed_by = Column(String, nullable=False, default="SYSTEM")
    status = Column(String, nullable=False, default="Pending")
    inferred_purpose = Column(Text, nullable=True)
    inferred_prompt_type = Column(String, nullable=True)
    inferred_risk_tier = Column(String, nullable=True)
    classification_confidence = Column(String, nullable=True)
    findings = Column(Text, nullable=True)      # JSON array
    suggestions = Column(Text, nullable=True)   # JSON array
    user_responses = Column(Text, nullable=True)  # JSON array
    responses_recorded_at = Column(String, nullable=True)
    resulting_version_id = Column(String(36), nullable=True)    # FK prompt_versions (circular)
    applied_at = Column(String, nullable=True)
    applied_by = Column(String(36), ForeignKey("users.user_id"), nullable=True)
    abandoned_reason = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('Pending','Partially Accepted','Accepted','Rejected','Applied','Abandoned')",
            name="ck_up_status",
        ),
        CheckConstraint(
            "classification_confidence IN ('Low','Medium','High') OR classification_confidence IS NULL",
            name="ck_up_confidence",
        ),
    )


class ComplianceCheck(Base):
    """
    version_id references prompt_versions but stored as plain string
    to avoid the circular FK. See UpgradeProposal note above.
    """
    __tablename__ = "compliance_checks"

    check_id = Column(String(36), primary_key=True, default=_uuid)
    version_id = Column(String(36), nullable=False)             # FK prompt_versions (circular)
    job_id = Column(String(36), nullable=True)                  # FK compliance_check_jobs (set after job created)
    run_at = Column(String, nullable=False, default=_utcnow)
    run_by = Column(String, nullable=False)                     # user_id UUID or literal 'SYSTEM'
    overall_result = Column(String, nullable=True)
    scores = Column(Text, nullable=True)                        # JSON
    blocking_defects = Column(Integer, nullable=False, default=0)
    gold_standard = Column(Text, nullable=True)                 # JSON
    flags = Column(Text, nullable=True)                         # JSON array
    human_reviewed_by = Column(String(36), ForeignKey("users.user_id"), nullable=True)
    human_reviewed_at = Column(String, nullable=True)
    human_review_notes = Column(Text, nullable=True)
    output_validation_result = Column(Text, nullable=True)      # JSON

    __table_args__ = (
        CheckConstraint(
            "overall_result IN ('Pass','Pass with warnings','Fail') OR overall_result IS NULL",
            name="ck_cc_result",
        ),
    )


class ComplianceCheckJob(Base):
    __tablename__ = "compliance_check_jobs"

    job_id = Column(String(36), primary_key=True, default=_uuid)
    version_id = Column(String(36), nullable=False)             # FK prompt_versions (circular)
    requested_by = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    requested_at = Column(String, nullable=False, default=_utcnow)
    status = Column(String, nullable=False, default="Queued")
    started_at = Column(String, nullable=True)
    completed_at = Column(String, nullable=True)
    result_id = Column(String(36), ForeignKey("compliance_checks.check_id"), nullable=True)
    error_message = Column(Text, nullable=True)
    force_refresh = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('Queued','Running','Complete','Failed')",
            name="ck_ccj_status",
        ),
    )


class PromptVersion(Base):
    """
    Immutable version record. DB triggers (see app/triggers.py) prevent
    updates to content fields (prompt_text, version_number, prompt_id,
    previous_version_id, created_by, created_at) and prevent deletion.
    Operational fields (cache_valid, compliance_check_id, is_active,
    approved_by, approved_at) may be updated.
    compliance_check_id and upgrade_proposal_id are stored as plain strings
    to avoid the circular FK that SQLite cannot resolve at DDL time.
    """
    __tablename__ = "prompt_versions"

    version_id = Column(String(36), primary_key=True, default=_uuid)
    prompt_id = Column(String(36), ForeignKey("prompts.prompt_id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    previous_version_id = Column(
        String(36), ForeignKey("prompt_versions.version_id"), nullable=True
    )
    prompt_text = Column(Text, nullable=False)
    change_summary = Column(Text, nullable=True)
    defects_found = Column(Text, nullable=False, default="[]")      # JSON array
    corrections_made = Column(Text, nullable=False, default="[]")   # JSON array
    compliance_check_id = Column(String(36), nullable=True)         # FK compliance_checks (circular)
    regulatory_scores = Column(Text, nullable=True)                 # JSON object
    cache_valid = Column(Boolean, nullable=False, default=True)
    upgrade_proposal_id = Column(String(36), nullable=True)         # FK upgrade_proposals (circular)
    injection_scan_result = Column(Text, nullable=True)             # JSON
    created_by = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    created_at = Column(String, nullable=False, default=_utcnow)
    approved_by = Column(String(36), ForeignKey("users.user_id"), nullable=True)
    approved_at = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("prompt_id", "version_number", name="uq_pv_prompt_version"),
    )


class AuditLog(Base):
    """
    Immutable audit record. DB triggers prevent deletion and prevent updates
    to core fields. resolved/resolved_at/resolved_by may be updated to
    support the review-queue resolve endpoint (per Q2 clarification).
    timestamp is set by DB server_default — never by the application.
    """
    __tablename__ = "audit_log"

    log_id = Column(String(36), primary_key=True, default=_uuid)
    timestamp = Column(
        String,
        nullable=False,
        server_default=text("(strftime('%Y-%m-%dT%H:%M:%SZ','now'))"),
    )
    user_id = Column(String, nullable=True)     # user UUID or literal 'SYSTEM'
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    detail = Column(Text, nullable=True)        # JSON
    ip_address = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    # Review-queue resolution fields (Q2 answer)
    resolved = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(String, nullable=True)
    resolved_by = Column(String(36), ForeignKey("users.user_id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "action IN ("
            "'Created','Edited','Activated','Retired','ComplianceChecked',"
            "'Approved','DefectLogged','Corrected','InjectionDetected',"
            "'ValidationFailed','Accessed','PromptImported','UpgradeProposed',"
            "'UpgradeResponseRecorded','UpgradeApplied','UpgradeAbandoned',"
            "'ClassificationOverridden','PromptGenerated')",
            name="ck_al_action",
        ),
        CheckConstraint(
            "entity_type IN ('Prompt','PromptVersion','ComplianceCheck','User','UpgradeProposal')",
            name="ck_al_entity_type",
        ),
    )
