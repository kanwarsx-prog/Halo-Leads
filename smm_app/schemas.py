from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from smm_app.models import SchoolPipelineStage, ContactStatus, AuditStatus


class SchoolContactBase(BaseModel):
    name: str
    role: str
    email: str | None = None
    email_is_verified: bool = False
    phone_extension: str | None = None
    source: str | None = None
    notes: str | None = None


class SchoolContactCreate(SchoolContactBase):
    pass


class SchoolContactRead(SchoolContactBase):
    id: str
    school_id: str
    status: ContactStatus
    personalized_hook: str | None = None
    email_subject: str | None = None
    email_draft: str | None = None
    letter_draft: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SchoolBase(BaseModel):
    name: str
    urn: str | None = None
    phase: str | None = "Primary"
    school_type: str | None = None
    mat_name: str | None = None
    local_authority: str | None = None
    website: str | None = None
    postcode: str | None = None
    address: str | None = None
    phone: str | None = None
    general_email: str | None = None
    sen_percentage: float | None = 0.0
    ehcp_count: int | None = 0
    ofsted_rating: str | None = None
    ofsted_inspection_date: str | None = None
    notes: str | None = None


class SchoolCreate(SchoolBase):
    pass


class SchoolRead(SchoolBase):
    id: str
    pipeline_stage: SchoolPipelineStage
    overall_score: int
    priority: str
    ofsted_send_excerpt: str | None = None
    created_at: datetime
    contacts: list[SchoolContactRead] = []

    model_config = ConfigDict(from_attributes=True)


class SchoolStageUpdate(BaseModel):
    pipeline_stage: SchoolPipelineStage


# Structured LLM Output for School Web Audits
class DiscoveredStaffContact(BaseModel):
    name: str = Field(description="Full name of the staff member")
    role: str = Field(description="Role: e.g., SENCO, Inclusion Lead, Headteacher, MAT Director of SEND")
    email: str | None = Field(description="Direct email address if found in SEND report or staff page", default=None)
    email_is_verified: bool = Field(description="True if explicitly found on school website/report", default=False)
    phone_extension: str | None = Field(description="Direct extension or contact number", default=None)
    source: str | None = Field(description="Exact page or report name where found", default=None)


class SchoolAuditExtraction(BaseModel):
    named_senco: str | None = Field(description="Name of the SENCO or Inclusion Lead")
    senco_email: str | None = Field(description="Direct email for SENCO")
    senco_phone: str | None = Field(description="Contact phone / extension for SENCO")
    headteacher_name: str | None = Field(description="Name of Headteacher / Principal")
    headteacher_email: str | None = Field(description="Direct or PA email for Headteacher")
    
    send_report_summary: str = Field(description="Brief summary of their statutory SEND Information Report")
    send_report_url: str | None = Field(description="URL to the school's SEND policy or Information report")
    detected_tools: list[str] = Field(description="Existing tools/platforms mentioned (e.g., Provision Map, CPOMS, SIMS, Arbor, ClassDojo)")
    
    ofsted_rating: str | None = Field(description="Latest Ofsted rating if discovered")
    ofsted_inspection_date: str | None = Field(description="Date of latest Ofsted inspection, e.g., November 2023", default=None)
    ofsted_send_quote: str | None = Field(description="Exact quote from latest Ofsted report regarding SEND / Inclusion")
    
    strengths_found: list[str] = Field(description="Specific SEND strengths or initiatives they highlight")
    challenges_found: list[str] = Field(description="Specific pressures, high need cohorts, or areas for development")
    
    additional_contacts: list[DiscoveredStaffContact] = Field(default_factory=list, description="Other relevant inclusion/pastoral staff")
    
    # Qualification Scores (0 to 100)
    need_score: int = Field(ge=0, le=100, description="Score based on SEND cohort size, complexity, and need")
    fit_score: int = Field(ge=0, le=100, description="Score based on alignment with See My Mind's classroom & parent features")
    recommended_angle: str = Field(description="Recommended hook or conversation angle for outreach")


class OutreachDraftResult(BaseModel):
    senco_email_subject: str = Field(description="Subject line for SENCO email")
    senco_email_body: str = Field(description="Empathetic, jargon-free email body for SENCO")
    headteacher_email_subject: str = Field(description="Subject line for Headteacher email")
    headteacher_email_body: str = Field(description="Strategic, workload-focused email body for Headteacher")
    physical_letter_body: str = Field(description="Formatted 1-page executive letter ready to print and post")


class PromptConfigRead(BaseModel):
    name: str
    content: str
    description: str | None


class PromptConfigUpdate(BaseModel):
    content: str


class SchoolActivityCreate(BaseModel):
    activity_type: str = "note"
    title: str
    notes: str | None = None
    contact_name: str | None = None
    author: str | None = "Admin"
    activity_date: datetime | None = None
    next_follow_up_date: datetime | None = None
    follow_up_task: str | None = None
    follow_up_completed: bool = False


class SchoolActivityRead(BaseModel):
    id: str
    school_id: str
    activity_type: str
    title: str
    notes: str | None = None
    contact_name: str | None = None
    author: str
    activity_date: datetime
    created_at: datetime
    next_follow_up_date: datetime | None = None
    follow_up_task: str | None = None
    follow_up_completed: bool = False

    model_config = ConfigDict(from_attributes=True)
