"""Pydantic request and response schemas for prompt and version endpoints."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PromptType = Literal[
    "Governance",
    "Analysis",
    "Comms",
    "Classification",
    "Summarisation",
    "Extraction",
    "Comparison",
    "Risk Review",
]

RiskTier = Literal["Minimal", "Limited", "High", "Prohibited"]

PromptStatus = Literal[
    "Draft",
    "Active",
    "Review Required",
    "Suspended",
    "Retired",
]


# ── Prompt schemas ───────────────────────────────────────────────────────────

class PromptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    prompt_type: PromptType
    deployment_target: str = Field(min_length=1)
    input_type: str = Field(min_length=1)
    output_type: str = Field(min_length=1)
    risk_tier: RiskTier
    review_cadence_days: int = Field(default=365, ge=1)
    # Initial v1 content
    prompt_text: str = Field(min_length=1)
    change_summary: str | None = None


class PromptUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: PromptStatus | None = None
    approver_id: str | None = None
    review_cadence_days: int | None = Field(default=None, ge=1)
    next_review_date: str | None = None


class PromptVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: str
    prompt_id: str
    version_number: int
    previous_version_id: str | None
    prompt_text: str
    change_summary: str | None
    created_by: str
    created_at: str
    approved_by: str | None
    approved_at: str | None
    is_active: bool


class PromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prompt_id: str
    title: str
    prompt_type: str
    deployment_target: str
    input_type: str
    output_type: str
    risk_tier: str
    owner_id: str
    approver_id: str | None
    status: str
    review_cadence_days: int
    next_review_date: str | None
    created_at: str
    updated_at: str


class PromptDetail(PromptOut):
    versions: list[PromptVersionOut] = []
    active_version: PromptVersionOut | None = None


# ── Version schemas ─────────────────────────────────────────────────────────

class VersionCreate(BaseModel):
    prompt_text: str = Field(min_length=1)
    change_summary: str | None = None


# ── Generate schema ─────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    title: str = Field(min_length=1)
    prompt_type: PromptType
    deployment_target: str = ""
    input_type: str = ""
    output_type: str = ""
    brief_text: str = ""
    constraints: list[str] = []
    selected_guardrails: list[str] | None = None  # dimension codes; None = auto-detect


class GenerateResponse(BaseModel):
    prompt_text: str


class ConversationEntry(BaseModel):
    question: str = ""
    answer: str = ""
    skipped: bool = False


class ValidateBriefRequest(BaseModel):
    description: str = Field(min_length=1)
    conversation_history: list[ConversationEntry] = []


class ValidateBriefResponse(BaseModel):
    tier: int  # 1=strong, 2=workable, 3=needs refinement
    accepted: bool
    question: str | None = None
    options: list[str] | None = None
    free_text_placeholder: str | None = None
    suggestion: str | None = None
    suggested_addition: str | None = None


class BriefScoreRequest(BaseModel):
    purpose: str = ""
    input_type: str = ""
    output_type: str = ""
    audience: str = ""
    constraints: list[str] = []
    deployment_target: str = ""
    skipped_steps: list[int] = []


class BriefScoreResponse(BaseModel):
    score: int
    label: str
    weakest_dimension: str
    improvement_tip: str
    dimensions: dict[str, int] = {}


class RestructureBriefRequest(BaseModel):
    brief_text: str = Field(min_length=1)


class RestructureBriefResponse(BaseModel):
    restructured: str
    title: str | None = None


# ── Brief schemas ───────────────────────────────────────────────────────────

class BriefCreate(BaseModel):
    client_name: str | None = None
    business_owner_name: str | None = None
    business_owner_role: str | None = None


class BriefUpdate(BaseModel):
    title: str | None = None
    step_progress: int | None = None
    step_answers: dict | None = None
    selected_guardrails: list[str] | None = None
    quality_score: int | None = None
    restructured_brief: str | None = None
    client_name: str | None = None
    business_owner_name: str | None = None
    business_owner_role: str | None = None


class BriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    brief_id: str
    title: str | None
    status: str
    quality_score: int
    step_progress: int
    client_name: str | None
    business_owner_name: str | None
    business_owner_role: str | None
    brief_builder_id: str
    interviewer_id: str | None
    step_answers: str
    selected_guardrails: str
    restructured_brief: str | None
    created_at: str
    updated_at: str
    submitted_at: str | None
    resulting_prompt_id: str | None


# ── Compliance schemas ───────────────────────────────────────────────────────

class ComplianceCheckRequest(BaseModel):
    version_id: str
    force_refresh: bool = False


class DimensionScoreOut(BaseModel):
    code: str
    score: int
    rationale: str


class AnomalyOut(BaseModel):
    result: str  # clean / suspicious / compromised
    confidence: float
    reason: str


class GoldStandardOut(BaseModel):
    composite: float
    framework_averages: dict[str, float]
    scale: str


class ComplianceCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_id: str
    version_id: str
    run_at: str
    run_by: str
    overall_result: str | None
    blocking_defects: int
    gold_standard: GoldStandardOut | None = None
    scores: list[DimensionScoreOut] = []
    anomaly: AnomalyOut | None = None
    flags: list[dict] = []


class ComplianceJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    version_id: str
    requested_by: str
    requested_at: str
    status: str
    started_at: str | None
    completed_at: str | None
    error_message: str | None
    force_refresh: bool
    result: ComplianceCheckOut | None = None


# ── Upgrade / Import schemas ────────────────────────────────────────────────

class AnalyseRequest(BaseModel):
    prompt_text: str = Field(min_length=1)
    prompt_name: str | None = None
    prompt_id: str | None = None
    source_version_id: str | None = None


class AnalyseResponse(BaseModel):
    proposal_id: str
    job_id: str
    status: str


class FindingOut(BaseModel):
    finding_id: str
    dimension_code: str
    dimension_name: str
    framework: str
    current_score: int
    current_finding: str
    severity: str
    source_reference: str


class SuggestionOut(BaseModel):
    suggestion_id: str
    finding_id: str | None = None
    dimension_code: str
    change_type: str
    description: str
    suggested_text: str
    rationale: str
    expected_score_improvement: dict | None = None
    insertion_hint: str | None = None


class UserResponseOut(BaseModel):
    suggestion_id: str
    response: str
    modified_text: str | None = None
    user_note: str | None = None
    responded_at: str
    responded_by: str


class UserResponseRequest(BaseModel):
    suggestion_id: str
    response: str = Field(pattern="^(Accepted|Rejected|Modified)$")
    modified_text: str | None = None
    user_note: str | None = None


class AbandonRequest(BaseModel):
    reason: str = Field(min_length=1)


class ApplyRequest(BaseModel):
    prompt_id: str | None = None


class ApplyResponse(BaseModel):
    version_id: str
    compliance_job_id: str


class ProposalOut(BaseModel):
    proposal_id: str
    prompt_id: str | None
    source_version_id: str | None
    proposed_at: str | None
    proposed_by: str
    status: str
    inferred_purpose: str | None
    inferred_prompt_type: str | None
    inferred_risk_tier: str | None
    classification_confidence: str | None
    findings: list[FindingOut] = []
    suggestions: list[SuggestionOut] = []
    user_responses: list[UserResponseOut] = []
    responses_recorded_at: str | None
    resulting_version_id: str | None
    applied_at: str | None
    applied_by: str | None
    abandoned_reason: str | None
