import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ResearchStatus(str, enum.Enum):
    queued = "queued"
    researching = "researching"
    extracting = "extracting"
    scoring = "scoring"
    completed = "completed"
    failed = "failed"

class ProspectingStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class ReviewStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    more_research = "more_research"


class PipelineStage(str, enum.Enum):
    discovered = "discovered"
    researching = "researching"
    qualified = "qualified"
    disqualified = "disqualified"
    outreach = "outreach"
    meeting_scheduled = "meeting_scheduled"
    closed_won = "closed_won"
    closed_lost = "closed_lost"


class EvidenceStrength(str, enum.Enum):
    strong = "strong"
    moderate = "moderate"
    weak = "weak"


class EvidenceNature(str, enum.Enum):
    fact = "fact"
    inference = "inference"
    unknown = "unknown"


class Organisation(Base):
    __tablename__ = "organisations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    website: Mapped[str | None] = mapped_column(String(1000))
    country: Mapped[str | None] = mapped_column(String(100))
    sector: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)

    pipeline_stage: Mapped[PipelineStage] = mapped_column(
        Enum(PipelineStage),
        nullable=False,
        default=PipelineStage.discovered,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    research_runs: Mapped[list["ResearchRun"]] = relationship(
        back_populates="organisation",
        cascade="all, delete-orphan",
        order_by="desc(ResearchRun.started_at)",
    )
    contact_leads: Mapped[list["ContactLead"]] = relationship(
        back_populates="organisation",
        cascade="all, delete-orphan",
    )


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[ResearchStatus] = mapped_column(
        Enum(ResearchStatus),
        nullable=False,
        default=ResearchStatus.queued,
    )
    research_model: Mapped[str] = mapped_column(String(100), nullable=False)
    extraction_model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)

    discovery_text: Mapped[str | None] = mapped_column(Text)
    raw_discovery_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    current_message: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    organisation: Mapped["Organisation"] = relationship(
        back_populates="research_runs"
    )
    sources: Mapped[list["ResearchSource"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )
    assessment: Mapped["Assessment | None"] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    contact_leads: Mapped[list["ContactLead"]] = relationship(
        back_populates="research_run",
        cascade="all, delete-orphan",
    )


class ProspectingRun(Base):
    __tablename__ = "prospecting_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    criteria: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProspectingStatus] = mapped_column(
        Enum(ProspectingStatus),
        nullable=False,
        default=ProspectingStatus.queued,
    )
    current_message: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    results_count: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

class ResearchSource(Base):
    __tablename__ = "research_sources"
    __table_args__ = (
        UniqueConstraint(
            "research_run_id",
            "url",
            name="uq_research_run_source_url",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(3000), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1000))
    domain: Mapped[str | None] = mapped_column(String(300))
    source_type: Mapped[str | None] = mapped_column(String(100))
    source_date: Mapped[date | None] = mapped_column(Date)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    research_run: Mapped["ResearchRun"] = relationship(
        back_populates="sources"
    )


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    claim_type: Mapped[str] = mapped_column(String(100), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    nature: Mapped[EvidenceNature] = mapped_column(
        Enum(EvidenceNature),
        nullable=False,
    )
    strength: Mapped[EvidenceStrength] = mapped_column(
        Enum(EvidenceStrength),
        nullable=False,
    )
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(3000))
    source_title: Mapped[str | None] = mapped_column(String(1000))
    supporting_excerpt: Mapped[str | None] = mapped_column(Text)

    research_run: Mapped["ResearchRun"] = relationship(
        back_populates="evidence_items"
    )


class ContactLead(Base):
    __tablename__ = "contact_leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    research_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    job_title: Mapped[str] = mapped_column(String(300), nullable=False)
    linkedin_url: Mapped[str | None] = mapped_column(String(1000))
    email: Mapped[str | None] = mapped_column(String(300))
    email_is_guessed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default='false')
    notes: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(3000))
    latest_email_draft: Mapped[str | None] = mapped_column(Text)
    latest_linkedin_draft: Mapped[str | None] = mapped_column(Text)

    organisation: Mapped["Organisation"] = relationship(
        back_populates="contact_leads"
    )
    research_run: Mapped["ResearchRun"] = relationship(
        back_populates="contact_leads"
    )


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    research_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    itsm_confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    basic_use_likelihood: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_pressure: Mapped[int] = mapped_column(Integer, nullable=False)
    renewal_proximity: Mapped[int] = mapped_column(Integer, nullable=False)
    migration_fit: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[str] = mapped_column(String(50), nullable=False)

    itsm_status: Mapped[str] = mapped_column(String(50), nullable=False)
    identified_tools: Mapped[str | None] = mapped_column(Text)
    pursuit_gate: Mapped[str] = mapped_column(String(50), nullable=False)
    apparent_use_cases: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
    )
    advanced_use_cases_found: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
    )
    opportunity_hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    unknowns: Mapped[list[str]] = mapped_column(JSONB, default=list)
    recommended_stakeholders: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
    )
    discovery_questions: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
    )
    suggested_outreach: Mapped[str | None] = mapped_column(Text)

    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus),
        default=ReviewStatus.pending,
    )
    review_notes: Mapped[str | None] = mapped_column(Text)

    scoring_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    research_run: Mapped["ResearchRun"] = relationship(
        back_populates="assessment"
    )

class PromptConfig(Base):
    __tablename__ = "prompt_configs"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
