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
