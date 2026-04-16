from datetime import datetime

from pydantic import BaseModel


# --- Prompt Version schemas ---

class PromptVersionCreate(BaseModel):
    content: str
    change_note: str = ""


class PromptVersionOut(BaseModel):
    id: int
    version: int
    content: str
    change_note: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Prompt schemas ---

class PromptCreate(BaseModel):
    name: str
    description: str = ""
    tags: list[str] = []
    content: str  # initial version content


class PromptUpdate(BaseModel):
    description: str | None = None
    tags: list[str] | None = None


class PromptOut(BaseModel):
    id: int
    name: str
    description: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    latest_version: PromptVersionOut | None = None

    model_config = {"from_attributes": True}


class PromptDetail(PromptOut):
    versions: list[PromptVersionOut] = []


# --- Scoring Dimension schemas ---

class ScoringDimensionOut(BaseModel):
    id: int
    framework: str
    code: str
    name: str
    description: str
    scoring_type: str
    is_mandatory: bool
    blocking_threshold: int | None
    score_5_criteria: str
    weight: float
    active: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Compliance schemas ---

class ComplianceCheckRequest(BaseModel):
    version_id: int
    requested_by: str = "system"
    force_refresh: bool = False


class DimensionScoreOut(BaseModel):
    code: str
    name: str
    framework: str
    score: int
    rationale: str


class AnomalyOut(BaseModel):
    result: str  # clean/suspicious/compromised
    confidence: float
    reason: str


class ComplianceResultOut(BaseModel):
    id: int
    version_id: int
    gold_score: float
    blocked: bool
    scores: list[DimensionScoreOut]
    anomaly: AnomalyOut
    cache_valid: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ComplianceJobOut(BaseModel):
    job_id: str
    version_id: int
    requested_by: str
    requested_at: datetime
    status: str  # Queued/Running/Complete/Failed
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str
    force_refresh: bool
    result: ComplianceResultOut | None = None

    model_config = {"from_attributes": True}


# --- Session 4: Import & Upgrade schemas ---

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
    finding_id: str
    dimension_code: str
    change_type: str
    description: str
    suggested_text: str
    rationale: str
    expected_score_improvement: dict
    insertion_hint: str


class UserResponseOut(BaseModel):
    suggestion_id: str
    response: str  # Accepted / Rejected / Modified
    modified_text: str | None = None
    user_note: str | None = None
    responded_at: datetime
    responded_by: str


class AnalyseRequest(BaseModel):
    prompt_text: str
    prompt_name: str | None = None


class AnalyseResponse(BaseModel):
    proposal_id: str
    job_id: str
    status: str


class UserResponseRequest(BaseModel):
    suggestion_id: str
    response: str  # Accepted / Rejected / Modified
    modified_text: str | None = None
    user_note: str | None = None
    responded_by: str = "user"


class AbandonRequest(BaseModel):
    reason: str


class ApplyResponse(BaseModel):
    version_id: int
    compliance_job_id: str


class ProposalOut(BaseModel):
    proposal_id: str
    prompt_id: int | None
    source_version_id: int | None
    proposed_at: datetime | None
    proposed_by: str
    status: str
    inferred_purpose: str
    inferred_prompt_type: str
    inferred_risk_tier: str
    classification_confidence: str
    findings: list[FindingOut]
    suggestions: list[SuggestionOut]
    user_responses: list[UserResponseOut]
    responses_recorded_at: datetime | None
    resulting_version_id: int | None
    applied_at: datetime | None
    applied_by: str
    abandoned_reason: str


class VersionTimelineEntry(BaseModel):
    version_number: int
    created_at: datetime
    created_by: str
    change_summary: str
    is_active: bool
    overall_result: str | None
    gold_standard_grade: float | None
    open_defects: int
    total_defects: int
    was_upgrade: bool
    defects: list[FindingOut]
