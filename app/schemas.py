import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ResearchPlan(BaseModel):
    questions: list[str] = Field(description="A list of specific research questions to investigate for this organisation.")


class OrganisationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    website: HttpUrl | None = None
    country: str | None = None
    sector: str | None = None
    notes: str | None = None


class OrganisationRead(BaseModel):
    id: uuid.UUID
    name: str
    website: str | None
    country: str | None
    sector: str | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvidenceExtraction(BaseModel):
    claim_type: Literal[
        "servicenow_usage",
        "basic_itsm_usage",
        "advanced_platform_usage",
        "contract",
        "renewal",
        "cost_pressure",
        "vendor_consolidation",
        "migration_complexity",
        "organisation_profile",
        "other",
    ]
    claim: str
    nature: Literal["fact", "inference", "unknown"]
    strength: Literal["strong", "moderate", "weak"]
    confidence: int = Field(ge=0, le=100)
    source_url: str | None = None
    source_title: str | None = None
    supporting_excerpt: str | None = None


class ComponentScores(BaseModel):
    servicenow_confidence: int = Field(ge=0, le=100)
    basic_use_likelihood: int = Field(ge=0, le=100)
    cost_pressure: int = Field(ge=0, le=100)
    renewal_proximity: int = Field(ge=0, le=100)
    migration_fit: int = Field(ge=0, le=100)


class ContactLeadSchema(BaseModel):
    name: str = Field(description="Full name of the contact")
    job_title: str = Field(description="Job title of the contact")
    linkedin_url: str | None = Field(description="LinkedIn URL of the contact, if found", default=None)
    notes: str | None = Field(description="Any notes regarding their role or relevance", default=None)
    source_url: str | None = Field(description="URL of the source where they were found", default=None)


class ProspectingResult(BaseModel):
    name: str = Field(description="Name of the organisation")
    website: str | None = Field(description="Website URL if found", default=None)
    country: str | None = Field(description="Country where headquartered", default=None)
    sector: str | None = Field(description="Industry sector", default=None)
    notes: str | None = Field(description="Brief notes on why this company is a good fit and their ServiceNow usage", default=None)
    contact_leads: list[ContactLeadSchema] = Field(default_factory=list, description="Key IT contacts found for this organisation")


class ProspectingBatch(BaseModel):
    companies: list[ProspectingResult] = Field(description="List of companies discovered")


class PromptConfigRead(BaseModel):
    name: str
    content: str
    description: str | None

class PromptConfigUpdate(BaseModel):
    content: str


class EvidenceBundle(BaseModel):
    organisation: str

    servicenow_status: Literal[
        "confirmed",
        "highly_likely",
        "possible",
        "unverified",
    ]

    apparent_use_cases: list[str]
    advanced_use_cases_found: list[str]
    evidence: list[EvidenceExtraction]

    component_scores: ComponentScores

    opportunity_hypothesis: str
    unknowns_to_validate: list[str]
    recommended_stakeholders: list[str]
    contact_leads: list[ContactLeadSchema] = Field(default_factory=list)
    discovery_questions: list[str]
    suggested_outreach: str | None = None


class AssessmentRead(BaseModel):
    id: uuid.UUID
    research_run_id: uuid.UUID
    servicenow_confidence: int
    basic_use_likelihood: int
    cost_pressure: int
    renewal_proximity: int
    migration_fit: int
    overall_score: int
    priority: str
    servicenow_status: str
    apparent_use_cases: list[str]
    advanced_use_cases_found: list[str]
    opportunity_hypothesis: str
    unknowns: list[str]
    recommended_stakeholders: list[str]
    discovery_questions: list[str]
    suggested_outreach: str | None
    review_status: str
    review_notes: str | None

    model_config = {"from_attributes": True}


class ReviewUpdate(BaseModel):
    status: Literal[
        "accepted",
        "rejected",
        "more_research",
    ]
    notes: str | None = None
