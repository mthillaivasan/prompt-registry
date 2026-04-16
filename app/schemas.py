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
