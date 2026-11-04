import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SchoolPipelineStage(str, enum.Enum):
    discovered = "discovered"
    auditing = "auditing"
    qualified = "qualified"
    disqualified = "disqualified"
    outreach_ready = "outreach_ready"
    contacted = "contacted"
    demo_booked = "demo_booked"
    partner_won = "partner_won"
    not_a_fit = "not_a_fit"


class ContactStatus(str, enum.Enum):
    discovered = "discovered"
    researched = "researched"
    outreach_drafted = "outreach_drafted"
    contacted = "contacted"
    replied = "replied"


class AuditStatus(str, enum.Enum):
    queued = "queued"
    researching = "researching"
    completed = "completed"
    failed = "failed"


class School(Base):
    __tablename__ = "smm_schools"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    urn: Mapped[str | None] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    phase: Mapped[str | None] = mapped_column(String(100), default="Primary")
    school_type: Mapped[str | None] = mapped_column(String(150))
    mat_name: Mapped[str | None] = mapped_column(String(250), index=True)
    local_authority: Mapped[str | None] = mapped_column(String(150))
    website: Mapped[str | None] = mapped_column(String(1000))
    postcode: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(50))
    general_email: Mapped[str | None] = mapped_column(String(255))

    # SEND & Ofsted metrics
    sen_percentage: Mapped[float | None] = mapped_column(Float, default=0.0)
    ehcp_count: Mapped[int | None] = mapped_column(Integer, default=0)
    ofsted_rating: Mapped[str | None] = mapped_column(String(50))
    ofsted_inspection_date: Mapped[str | None] = mapped_column(String(50))
    ofsted_send_excerpt: Mapped[str | None] = mapped_column(Text)

    # Lead qualification
    pipeline_stage: Mapped[SchoolPipelineStage] = mapped_column(
        Enum(SchoolPipelineStage),
        nullable=False,
        default=SchoolPipelineStage.discovered,
    )
    overall_score: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[str] = mapped_column(String(50), default="Monitor")
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    contacts: Mapped[list["SchoolContact"]] = relationship(
        back_populates="school",
        cascade="all, delete-orphan",
        order_by="desc(SchoolContact.created_at)",
    )
    audit_runs: Mapped[list["SchoolAuditRun"]] = relationship(
        back_populates="school",
        cascade="all, delete-orphan",
        order_by="desc(SchoolAuditRun.started_at)",
    )


class SchoolContact(Base):
    __tablename__ = "smm_contacts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    school_id: Mapped[str] = mapped_column(
        ForeignKey("smm_schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(150), nullable=False)  # SENCO, Headteacher, etc.
    email: Mapped[str | None] = mapped_column(String(255))
    email_is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    phone_extension: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(300))  # e.g., "SEND Info Report 2025/26"

    status: Mapped[ContactStatus] = mapped_column(
        Enum(ContactStatus),
        nullable=False,
        default=ContactStatus.discovered,
    )

    personalized_hook: Mapped[str | None] = mapped_column(Text)
    email_subject: Mapped[str | None] = mapped_column(String(300))
    email_draft: Mapped[str | None] = mapped_column(Text)
    letter_draft: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    school: Mapped["School"] = relationship(back_populates="contacts")


class SchoolAuditRun(Base):
    __tablename__ = "smm_audit_runs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    school_id: Mapped[str] = mapped_column(
        ForeignKey("smm_schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[AuditStatus] = mapped_column(
        Enum(AuditStatus),
        nullable=False,
        default=AuditStatus.queued,
    )
    current_message: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(Text)

    send_report_url: Mapped[str | None] = mapped_column(String(1000))
    ofsted_report_url: Mapped[str | None] = mapped_column(String(1000))
    detected_tools: Mapped[str | None] = mapped_column(String(500))  # e.g. "Provision Map, CPOMS"
    strengths_found: Mapped[str | None] = mapped_column(Text)
    challenges_found: Mapped[str | None] = mapped_column(Text)
    recommended_angle: Mapped[str | None] = mapped_column(Text)
    raw_findings: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    school: Mapped["School"] = relationship(back_populates="audit_runs")


class PromptConfig(Base):
    __tablename__ = "smm_prompt_configs"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
