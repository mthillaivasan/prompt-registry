import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(String(500), default="")  # comma-separated
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    versions: Mapped[list["PromptVersion"]] = relationship(
        back_populates="prompt", cascade="all, delete-orphan", order_by="PromptVersion.version"
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_note: Mapped[str] = mapped_column(Text, default="")
    upgrade_proposal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    prompt: Mapped["Prompt"] = relationship(back_populates="versions")


class ScoringDimension(Base):
    __tablename__ = "scoring_dimensions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    framework: Mapped[str] = mapped_column(String(10), nullable=False)  # REG, OWASP, NIST, ISO
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_type: Mapped[str] = mapped_column(String(20), nullable=False)  # Blocking/Advisory/Maturity/Alignment
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    blocking_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_5_criteria: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ComplianceResult(Base):
    __tablename__ = "compliance_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("prompt_versions.id"), nullable=False)
    scores_json: Mapped[str] = mapped_column(Text, nullable=False)  # full scoring response
    gold_score: Mapped[float] = mapped_column(Float, nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_result: Mapped[str] = mapped_column(String(20), nullable=False)  # clean/suspicious/compromised
    anomaly_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    anomaly_reason: Mapped[str] = mapped_column(Text, default="")
    cache_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    dimensions_hash: Mapped[str] = mapped_column(String(64), default="")

    version: Mapped["PromptVersion"] = relationship()


def _generate_job_id() -> str:
    return str(uuid.uuid4())


class ComplianceCheckJob(Base):
    __tablename__ = "compliance_check_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, default=_generate_job_id)
    version_id: Mapped[int] = mapped_column(ForeignKey("prompt_versions.id"), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(255), default="system")
    requested_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(20), default="Queued")  # Queued/Running/Complete/Failed
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    result_id: Mapped[int | None] = mapped_column(ForeignKey("compliance_results.id"), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    force_refresh: Mapped[bool] = mapped_column(Boolean, default=False)

    result: Mapped["ComplianceResult | None"] = relationship()
    version: Mapped["PromptVersion"] = relationship()


def _generate_proposal_id() -> str:
    return str(uuid.uuid4())


class UpgradeProposal(Base):
    __tablename__ = "upgrade_proposals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(36), unique=True, default=_generate_proposal_id)
    prompt_id: Mapped[int | None] = mapped_column(ForeignKey("prompts.id"), nullable=True)
    source_version_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_versions.id"), nullable=True)
    proposed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    proposed_by: Mapped[str] = mapped_column(String(255), default="SYSTEM")
    status: Mapped[str] = mapped_column(String(30), default="Pending")
    # Pending / Partially Accepted / Accepted / Rejected / Applied / Abandoned
    inferred_purpose: Mapped[str] = mapped_column(Text, default="")
    inferred_prompt_type: Mapped[str] = mapped_column(String(255), default="")
    inferred_risk_tier: Mapped[str] = mapped_column(String(20), default="")
    # Minimal / Limited / High / Prohibited
    classification_confidence: Mapped[str] = mapped_column(String(10), default="")
    # Low / Medium / High
    findings_json: Mapped[str] = mapped_column(Text, default="[]")
    suggestions_json: Mapped[str] = mapped_column(Text, default="[]")
    user_responses_json: Mapped[str] = mapped_column(Text, default="[]")
    responses_recorded_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    resulting_version_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_versions.id"), nullable=True)
    applied_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    applied_by: Mapped[str] = mapped_column(String(255), default="")
    abandoned_reason: Mapped[str] = mapped_column(Text, default="")
    # Original prompt text for fresh imports
    original_prompt_text: Mapped[str] = mapped_column(Text, default="")

    prompt: Mapped["Prompt | None"] = relationship(foreign_keys=[prompt_id])
    source_version: Mapped["PromptVersion | None"] = relationship(foreign_keys=[source_version_id])
    resulting_version: Mapped["PromptVersion | None"] = relationship(foreign_keys=[resulting_version_id])


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    # PromptImported / UpgradeProposed / UpgradeResponseRecorded /
    # ClassificationOverridden / UpgradeApplied / UpgradeAbandoned /
    # InjectionDetected
    entity_type: Mapped[str] = mapped_column(String(50), default="")
    entity_id: Mapped[str] = mapped_column(String(36), default="")
    actor: Mapped[str] = mapped_column(String(255), default="SYSTEM")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
