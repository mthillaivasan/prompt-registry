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
            "role IN ('Maker','Checker','Admin')",
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
    instructional_text = Column(Text, nullable=True)
    # Three-category architecture: prompt_content dims are injected into the
    # generated prompt; wrapper_metadata and registry_policy are captured for
    # display/enforcement elsewhere but excluded from the prompt body.
    # See docs/CHECKLIST_DESIGN.md (not yet authored); classification map in
    # app/seed.py _CONTENT_TYPES_BY_CODE. NULL = treat as prompt_content for
    # backward compat during migration window.
    content_type = Column(String, nullable=True)
    updated_at = Column(String, nullable=True)
    updated_by = Column(String(36), ForeignKey("users.user_id"), nullable=True)

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
            "content_type IS NULL OR content_type IN ('prompt_content','wrapper_metadata','registry_policy')",
            name="ck_sd_content_type",
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
    # Transitional: deployment_target is deprecated in favour of
    # ai_platform + output_destination. Dual-write keeps the legacy
    # NOT-NULL column valid until it is dropped in a future migration.
    ai_platform = Column(String, nullable=True)
    output_destination = Column(String, nullable=True)
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
    token_count = Column(Integer, nullable=True)                    # approx; see services/pricing.py
    estimated_cost_usd = Column(String, nullable=True)              # stored as string for decimal safety
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
        default=_utcnow,
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
            "'ClassificationOverridden','PromptGenerated',"
            "'BriefCreated','BriefUpdated','BriefDeleted','BriefAbandoned','BriefCompleted','BriefStepSkipped','BriefQuestionSkipped','BriefTrackAbandoned','TokenRefreshed')",
            name="ck_al_action",
        ),
        CheckConstraint(
            "entity_type IN ('Prompt','PromptVersion','ComplianceCheck','User','UpgradeProposal','Brief')",
            name="ck_al_entity_type",
        ),
    )


class Brief(Base):
    __tablename__ = "briefs"

    brief_id = Column(String(36), primary_key=True, default=_uuid)
    title = Column(String, nullable=True)
    status = Column(String, nullable=False, default="In Progress")
    quality_score = Column(Integer, nullable=False, default=0)
    step_progress = Column(Integer, nullable=False, default=1)
    client_name = Column(String, nullable=True)
    business_owner_name = Column(String, nullable=True)
    business_owner_role = Column(String, nullable=True)
    brief_builder_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    interviewer_id = Column(String(36), ForeignKey("users.user_id"), nullable=True)
    step_answers = Column(Text, nullable=False, default="{}")
    selected_guardrails = Column(Text, nullable=False, default="[]")
    restructured_brief = Column(Text, nullable=True)
    created_at = Column(String, nullable=False, default=_utcnow)
    updated_at = Column(String, nullable=False, default=_utcnow)
    submitted_at = Column(String, nullable=True)
    resulting_prompt_id = Column(String(36), ForeignKey("prompts.prompt_id"), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('In Progress','Complete','Abandoned','Archived')",
            name="ck_briefs_status",
        ),
    )


class PromptComponent(Base):
    __tablename__ = "prompt_components"

    component_id = Column(String(36), primary_key=True, default=_uuid)
    code = Column(String, unique=True, nullable=False)
    category = Column(String, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    component_text = Column(Text, nullable=False)
    example_output = Column(Text, nullable=True)
    applicable_dimensions = Column(Text, nullable=False, default="[]")
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint(
            "category IN ('InputHandling','OutputFormat','RegulatoryGuardrail','Behavioural')",
            name="ck_pc_category",
        ),
    )


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    template_id = Column(String(36), primary_key=True, default=_uuid)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    use_case = Column(Text, nullable=True)
    prompt_type = Column(String, nullable=False)
    risk_tier = Column(String, nullable=False, default="Limited")
    input_type = Column(String, nullable=True)
    output_type = Column(String, nullable=True)
    component_codes = Column(Text, nullable=False, default="[]")
    prompt_text = Column(Text, nullable=True)
    output_example = Column(Text, nullable=True)
    gold_standard_grade = Column(String, nullable=True)
    applicable_to_client_types = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)


class PromptLibrary(Base):
    __tablename__ = "prompt_library"

    library_id = Column(String(36), primary_key=True, default=_uuid)
    title = Column(String, unique=True, nullable=False)
    full_text = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    prompt_type = Column(String, nullable=False)
    input_type = Column(String, nullable=True)
    output_type = Column(String, nullable=True)
    domain = Column(String, nullable=False, default="general")
    source_provenance = Column(Text, nullable=True)
    topic_coverage = Column(Text, nullable=False, default="[]")
    classification_notes = Column(Text, nullable=True)
    created_at = Column(String, nullable=False, default=_utcnow)
    updated_at = Column(String, nullable=False, default=_utcnow)

    __table_args__ = (
        CheckConstraint(
            "prompt_type IN ('Governance','Analysis','Comms','Classification',"
            "'Summarisation','Extraction','Comparison','Risk Review')",
            name="ck_prompt_library_type",
        ),
        CheckConstraint(
            "domain IN ('finance','general')",
            name="ck_prompt_library_domain",
        ),
    )


# ── Phase 2 schema (config-driven engine) ────────────────────────────────────
#
# Tables introduced by Block 7 of REFACTOR_PLAN.md / SCHEMA_V2.md.
# Legacy ScoringDimension and ComplianceCheck remain. The engine in Block 9
# reads from these new tables; the legacy tables stay populated as a
# fallback read-path during the transition.


class Standard(Base):
    __tablename__ = "standards"

    standard_id = Column(String(36), primary_key=True, default=_uuid)
    standard_code = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    version = Column(String, nullable=False)
    publisher = Column(String, nullable=False)
    url = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(String, nullable=False, default=_utcnow)
    updated_at = Column(String, nullable=False, default=_utcnow)


class Phase(Base):
    __tablename__ = "phases"

    phase_id = Column(String(36), primary_key=True, default=_uuid)
    code = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    purpose = Column(Text, nullable=False)
    scoring_input = Column(String, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    pass_threshold = Column(String, nullable=False, default="4.0")
    pass_with_warnings_threshold = Column(String, nullable=False, default="3.0")
    is_active = Column(Boolean, nullable=False, default=True)


class PhaseWeight(Base):
    __tablename__ = "phase_weights"

    phase_weight_id = Column(String(36), primary_key=True, default=_uuid)
    phase_id = Column(String(36), ForeignKey("phases.phase_id"), nullable=False)
    standard_id = Column(String(36), ForeignKey("standards.standard_id"), nullable=False)
    weight = Column(String, nullable=False, default="0.0")

    __table_args__ = (
        UniqueConstraint("phase_id", "standard_id", name="uq_pw_phase_standard"),
    )


class Dimension(Base):
    """
    Phase 2 dimension table. Distinct from legacy ScoringDimension.
    The engine loops over this; it never references rows by `code` in code.
    """
    __tablename__ = "dimensions"

    dimension_id = Column(String(36), primary_key=True, default=_uuid)
    code = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    phase_id = Column(String(36), ForeignKey("phases.phase_id"), nullable=False)
    standard_id = Column(String(36), ForeignKey("standards.standard_id"), nullable=False)
    clause = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    blocking_threshold = Column(Integer, nullable=False, default=2)
    is_mandatory = Column(Boolean, nullable=False, default=False)
    scoring_type = Column(String, nullable=False)
    content_type = Column(String, nullable=True)
    applicability = Column(Text, nullable=False, default='{"always": true}')
    score_5_criteria = Column(Text, nullable=False)
    score_3_criteria = Column(Text, nullable=False)
    score_1_criteria = Column(Text, nullable=False)
    instructional_text = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(String, nullable=False, default=_utcnow)
    updated_at = Column(String, nullable=False, default=_utcnow)

    __table_args__ = (
        CheckConstraint(
            "scoring_type IN ('Blocking','Advisory','Maturity','Alignment')",
            name="ck_dim_scoring_type",
        ),
        CheckConstraint(
            "content_type IS NULL OR content_type IN ('prompt_content','wrapper_metadata','registry_policy')",
            name="ck_dim_content_type",
        ),
    )


class Gate(Base):
    __tablename__ = "gates"

    gate_id = Column(String(36), primary_key=True, default=_uuid)
    code = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    from_phase_id = Column(String(36), ForeignKey("phases.phase_id"), nullable=False)
    min_grade = Column(String, nullable=False, default="3.0")
    approver_role = Column(String, nullable=False)
    rationale_required = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)


class GateMustPassDimension(Base):
    __tablename__ = "gate_must_pass_dimensions"

    gate_id = Column(String(36), ForeignKey("gates.gate_id"), primary_key=True)
    dimension_id = Column(String(36), ForeignKey("dimensions.dimension_id"), primary_key=True)


class FormField(Base):
    __tablename__ = "form_fields"

    field_id = Column(String(36), primary_key=True, default=_uuid)
    form_code = Column(String, nullable=False)
    field_code = Column(String, nullable=False)
    label = Column(String, nullable=False)
    help_text = Column(Text, nullable=True)
    field_type = Column(String, nullable=False)
    options = Column(Text, nullable=True)
    validation = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("form_code", "field_code", name="uq_ff_form_field"),
    )


class ComplianceRun(Base):
    """
    New phase-aware compliance run record. Coexists with legacy
    ComplianceCheck. New engine writes here; legacy engine still writes
    to compliance_checks during the transition.
    """
    __tablename__ = "compliance_runs"

    run_id = Column(String(36), primary_key=True, default=_uuid)
    phase_id = Column(String(36), ForeignKey("phases.phase_id"), nullable=False)
    subject_type = Column(String, nullable=False)
    subject_id = Column(String(36), nullable=False)
    run_at = Column(String, nullable=False, default=_utcnow)
    run_by = Column(String, nullable=False)
    overall_result = Column(String, nullable=True)
    composite_grade = Column(String, nullable=True)
    scores_json = Column(Text, nullable=False, default="[]")
    flags_json = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('prompt_version','deployment_record','operation_record')",
            name="ck_cr_subject_type",
        ),
        CheckConstraint(
            "overall_result IS NULL OR overall_result IN ('Pass','Pass with warnings','Fail')",
            name="ck_cr_result",
        ),
    )


class DeploymentRecord(Base):
    __tablename__ = "deployment_records"

    deployment_id = Column(String(36), primary_key=True, default=_uuid)
    prompt_id = Column(String(36), ForeignKey("prompts.prompt_id"), nullable=False)
    version_id = Column(String(36), nullable=False)
    invocation_context = Column(Text, nullable=True)
    ai_platform = Column(String, nullable=True)
    output_destination = Column(String, nullable=True)
    runtime_owner_id = Column(String(36), ForeignKey("users.user_id"), nullable=True)
    form_responses_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="Draft")
    created_at = Column(String, nullable=False, default=_utcnow)
    updated_at = Column(String, nullable=False, default=_utcnow)

    __table_args__ = (
        CheckConstraint(
            "status IN ('Draft','Pending Approval','Approved','Rejected','Withdrawn')",
            name="ck_dr_status",
        ),
    )


class OperationRecord(Base):
    __tablename__ = "operation_records"

    operation_id = Column(String(36), primary_key=True, default=_uuid)
    deployment_id = Column(String(36), ForeignKey("deployment_records.deployment_id"), nullable=False)
    state = Column(String, nullable=False, default="Active")
    next_review_date = Column(String, nullable=True)
    review_cadence_days = Column(Integer, nullable=False, default=365)
    incidents_json = Column(Text, nullable=False, default="[]")
    retired_at = Column(String, nullable=True)
    retired_reason = Column(Text, nullable=True)
    created_at = Column(String, nullable=False, default=_utcnow)
    updated_at = Column(String, nullable=False, default=_utcnow)

    __table_args__ = (
        CheckConstraint(
            "state IN ('Active','Under Review','Suspended','Retired')",
            name="ck_or_state",
        ),
    )


class GateDecision(Base):
    __tablename__ = "gate_decisions"

    decision_id = Column(String(36), primary_key=True, default=_uuid)
    gate_id = Column(String(36), ForeignKey("gates.gate_id"), nullable=False)
    subject_type = Column(String, nullable=False)
    subject_id = Column(String(36), nullable=False)
    run_id = Column(String(36), ForeignKey("compliance_runs.run_id"), nullable=False)
    decision = Column(String, nullable=False)
    decided_by = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    decided_at = Column(String, nullable=False, default=_utcnow)
    rationale = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "decision IN ('Approved','Rejected')",
            name="ck_gd_decision",
        ),
    )
