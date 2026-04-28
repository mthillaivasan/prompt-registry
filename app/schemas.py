"""Pydantic request and response schemas for prompt and version endpoints."""

from typing import Literal

import json

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

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

TopicState = Literal["red", "amber", "green"]


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
    # Transitional: deployment_target is deprecated in favour of
    # ai_platform + output_destination. Dual-write keeps the legacy
    # NOT-NULL column valid until it is dropped in a future migration.
    ai_platform: str = "Claude"
    output_destination: str | None = None


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
    token_count: int | None = None
    estimated_cost_usd: str | None = None


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
    # Transitional: see PromptCreate above.
    ai_platform: str = "Claude"
    output_destination: str | None = None


class GenerateResponse(BaseModel):
    prompt_text: str


class ConversationEntry(BaseModel):
    question: str = ""
    answer: str = ""
    skipped: bool = False
    topic_id: str | None = None


class ValidateBriefRequest(BaseModel):
    description: str = Field(min_length=1)
    conversation_history: list[ConversationEntry] = []


class BriefTopicEntry(BaseModel):
    """Per-topic answer within Brief.step_answers (Phase A model).

    When the Phase B UI lands, writers of step_answers will use this
    shape: {topic_id: BriefTopicEntry.model_dump()}. Phase A does not
    yet have any UI writers; the model exists so API callers can
    round-trip the shape via the existing /briefs/{id} PATCH.
    """
    value: str
    state: TopicState
    updated_at: str
    conversation_history: list[ConversationEntry] = []


class ReferenceExample(BaseModel):
    title: str
    excerpt: str


class ValidateTopicRequest(BaseModel):
    topic_id: str = Field(min_length=1)
    prompt_type: PromptType
    topic_answer: str = ""
    sibling_answers: dict[str, str] = {}
    conversation_history: list[ConversationEntry] = []
    reference_examples: list[ReferenceExample] = []


class ValidateTopicResponse(BaseModel):
    state: TopicState
    suggestion: str | None = None
    suggested_addition: str | None = None
    question: str | None = None
    options: list[str] | None = None
    free_text_placeholder: str | None = None


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
    approved_library_refs: list[str] | None = None


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
    approved_library_refs: list[str] = Field(default_factory=list)
    restructured_brief: str | None
    created_at: str
    updated_at: str
    submitted_at: str | None
    resulting_prompt_id: str | None

    @field_validator("approved_library_refs", mode="before")
    @classmethod
    def _parse_approved_library_refs(cls, v):
        if isinstance(v, str):
            return json.loads(v) if v else []
        return v or []


# ── Compliance schemas ───────────────────────────────────────────────────────

class ComplianceCheckRequest(BaseModel):
    version_id: str
    force_refresh: bool = False


class StandardLabel(BaseModel):
    """Block 10: standards labelling for graded dimensions."""
    standard_code: str
    title: str
    version: str
    clause: str = ""


class DimensionScoreOut(BaseModel):
    code: str
    score: int
    rationale: str
    # Block 10: each scored dimension carries its standard label so the UI
    # can render "OWASP LLM01 — Pass" rather than "D1 — Pass". Optional for
    # backward compatibility with any caller that pre-dates the label join.
    standard: StandardLabel | None = None


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


# ── PromptLibrary schemas ────────────────────────────────────────────────────

LibraryDomain = Literal["finance", "general"]


class PromptLibraryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    full_text: str = Field(min_length=1)
    summary: str | None = None
    prompt_type: PromptType
    input_type: str | None = None
    output_type: str | None = None
    domain: LibraryDomain = "general"
    source_provenance: str | None = None
    topic_coverage: list[str] = Field(default_factory=list)
    classification_notes: str | None = None


class PromptLibraryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    full_text: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    prompt_type: PromptType | None = None
    input_type: str | None = None
    output_type: str | None = None
    domain: LibraryDomain | None = None
    source_provenance: str | None = None
    topic_coverage: list[str] | None = None
    classification_notes: str | None = None


SourceCategory = Literal["Internal", "Public", "Vendor"]

# Substrings that mark a provenance string as a public-vendor source.
# Lower-cased before comparison. Match anywhere in the string.
_PUBLIC_SOURCE_MARKERS = (
    "docs.claude.com",
    "docs.anthropic.com",
    "anthropic cookbook",
    "openai",
    "langchain",
    "promptbase",
    "huggingface",
    "github.com/anthropics",
)


def derive_source_category(source_provenance: str | None) -> SourceCategory:
    """Bucket a free-form source_provenance string into Internal/Public/Vendor.

    Rule (per Drop L1 follow-up spec):
      - "Authored for Prompt Registry" anywhere → Internal
      - contains a known public-source marker (docs.claude.com, named public
        prompt libraries) → Public
      - everything else → Vendor

    Empty / None defaults to Vendor — the registry never authored it and we
    can't prove it's public, so the conservative bucket is the third-party one.
    """
    s = (source_provenance or "").lower()
    if "authored for prompt registry" in s:
        return "Internal"
    if any(marker in s for marker in _PUBLIC_SOURCE_MARKERS):
        return "Public"
    return "Vendor"


class PromptLibraryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    library_id: str
    title: str
    full_text: str
    summary: str | None
    prompt_type: PromptType
    input_type: str | None
    output_type: str | None
    domain: LibraryDomain
    source_provenance: str | None
    topic_coverage: list[str] = Field(default_factory=list)
    classification_notes: str | None
    created_at: str
    updated_at: str

    @field_validator("topic_coverage", mode="before")
    @classmethod
    def _parse_topic_coverage(cls, v):
        if isinstance(v, str):
            return json.loads(v) if v else []
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def source_category(self) -> SourceCategory:
        return derive_source_category(self.source_provenance)


class PromptLibraryListOut(BaseModel):
    items: list[PromptLibraryOut]
    total: int
    page: int
    page_size: int
    has_next: bool
