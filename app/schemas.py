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
