"""
Research service unit tests.

LLM calls (run_web_research, extract_evidence_bundle) are mocked so these
tests run without an API key or network access.

Integration tests that make real API calls are marked @pytest.mark.integration
and are skipped unless explicitly requested.
"""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import JSON, String, Text, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Organisation, ResearchStatus
from app.schemas import ComponentScores, EvidenceBundle, EvidenceExtraction
from app.research_service import research_organisation


# ---------------------------------------------------------------------------
# In-memory SQLite database for tests.
# SQLite does not support JSONB or PostgreSQL UUID column types, so we remap
# them before CREATE TABLE runs and configure the engine to handle uuid objects.
# ---------------------------------------------------------------------------


def _sqlite_type_listener(target, connection, **kw):
    """Remap PostgreSQL-specific column types to SQLite-compatible equivalents."""
    for table in target.sorted_tables:
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, PG_UUID):
                column.type = String(36)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite session for a single test.

    Uses detect_types + a custom converter so that uuid.UUID objects
    returned from SQLAlchemy are stored/retrieved as strings in SQLite.
    """
    import sqlite3

    # Register a sqlite3 adapter so uuid.UUID → text automatically
    sqlite3.register_adapter(uuid.UUID, str)

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    event.listen(Base.metadata, "before_create", _sqlite_type_listener)
    Base.metadata.create_all(engine, checkfirst=True)
    event.remove(Base.metadata, "before_create", _sqlite_type_listener)

    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _make_bundle(org_name: str = "Test Org") -> EvidenceBundle:
    """Build a minimal valid EvidenceBundle for testing."""
    return EvidenceBundle(
        organisation=org_name,
        servicenow_status="confirmed",
        apparent_use_cases=["incident management", "service catalogue"],
        advanced_use_cases_found=[],
        evidence=[
            EvidenceExtraction(
                claim_type="servicenow_usage",
                claim="The organisation uses ServiceNow for incident management.",
                nature="fact",
                strength="strong",
                confidence=90,
                source_url="https://example.com/source",
                source_title="Example Source",
                supporting_excerpt="ServiceNow is used for incident management.",
            )
        ],
        component_scores=ComponentScores(
            servicenow_confidence=85,
            basic_use_likelihood=75,
            cost_pressure=60,
            renewal_proximity=50,
            migration_fit=70,
        ),
        opportunity_hypothesis="This organisation appears to use ServiceNow for basic ITSM only.",
        unknowns_to_validate=["Contract renewal date unknown"],
        recommended_stakeholders=["IT Director"],
        discovery_questions=["What is the current contract value?"],
        suggested_outreach=None,
    )


def _make_raw_response() -> dict:
    """Minimal raw response with one URL matching the bundle's source URL."""
    return {
        "output": [
            {
                "type": "message",
                "content": "Research brief text.",
                "annotations": [
                    {
                        "url": "https://example.com/source",
                        "title": "Example Source",
                    }
                ],
            }
        ]
    }


@pytest.fixture
def org(db_session):
    """Insert a test organisation and return it."""
    organisation = Organisation(
        id=uuid.uuid4(),
        name="Test Organisation",
        website="https://www.testorg.example.com",
        country="United Kingdom",
        sector="Local government",
    )
    db_session.add(organisation)
    db_session.commit()
    db_session.refresh(organisation)
    return organisation


class TestResearchOrganisation:
    def test_successful_run_creates_assessment(self, db_session, org):
        """A successful research run should create a completed run with an assessment."""
        bundle = _make_bundle(org.name)
        raw = _make_raw_response()

        with (
            patch(
                "app.research_service.run_web_research",
                return_value=("Research brief text.", raw),
            ),
            patch(
                "app.research_service.extract_evidence_bundle",
                return_value=bundle,
            ),
        ):
            run = research_organisation(db=db_session, organisation_id=org.id)

        assert run.status == ResearchStatus.completed
        assert run.assessment is not None
        assert run.assessment.overall_score > 0
        assert run.assessment.priority in {
            "immediate_pursuit",
            "research_and_nurture",
            "monitor",
            "do_not_pursue",
        }
        assert run.assessment.servicenow_status == "confirmed"

    def test_failed_run_is_marked_failed(self, db_session, org):
        """If the web research call raises, the run should be marked failed."""
        with (
            patch(
                "app.research_service.run_web_research",
                side_effect=RuntimeError("API error"),
            ),
            pytest.raises(RuntimeError, match="API error"),
        ):
            research_organisation(db=db_session, organisation_id=org.id)

        from sqlalchemy import select
        from app.models import ResearchRun

        failed_run = db_session.scalars(
            select(ResearchRun).where(
                ResearchRun.organisation_id == org.id,
                ResearchRun.status == ResearchStatus.failed,
            )
        ).first()

        assert failed_run is not None
        assert "API error" in failed_run.error_message

    def test_unknown_organisation_raises(self, db_session):
        """Researching a non-existent organisation should raise ValueError."""
        with pytest.raises(ValueError, match="Organisation not found"):
            research_organisation(
                db=db_session,
                organisation_id=uuid.uuid4(),
            )

    def test_sources_are_saved(self, db_session, org):
        """Source URLs parsed from the raw response should be persisted."""
        bundle = _make_bundle(org.name)
        raw = _make_raw_response()

        with (
            patch(
                "app.research_service.run_web_research",
                return_value=("Research brief.", raw),
            ),
            patch(
                "app.research_service.extract_evidence_bundle",
                return_value=bundle,
            ),
        ):
            run = research_organisation(db=db_session, organisation_id=org.id)

        assert len(run.sources) >= 1
        assert run.sources[0].url == "https://example.com/source"

    def test_evidence_items_are_saved(self, db_session, org):
        """Evidence items from the bundle should be persisted."""
        bundle = _make_bundle(org.name)
        raw = _make_raw_response()

        with (
            patch(
                "app.research_service.run_web_research",
                return_value=("Research brief.", raw),
            ),
            patch(
                "app.research_service.extract_evidence_bundle",
                return_value=bundle,
            ),
        ):
            run = research_organisation(db=db_session, organisation_id=org.id)

        assert len(run.evidence_items) == 1
        assert run.evidence_items[0].claim_type == "servicenow_usage"

    def test_unverified_status_gates_score(self, db_session, org):
        """Unverified ServiceNow status must produce do_not_pursue regardless of component scores."""
        bundle = _make_bundle(org.name)
        # Override to unverified with high component scores
        bundle = bundle.model_copy(
            update={
                "servicenow_status": "unverified",
                "evidence": [],  # no facts = no source URL validation needed
            }
        )
        raw = {"output": []}

        with (
            patch(
                "app.research_service.run_web_research",
                return_value=("Research brief.", raw),
            ),
            patch(
                "app.research_service.extract_evidence_bundle",
                return_value=bundle,
            ),
        ):
            run = research_organisation(db=db_session, organisation_id=org.id)

        assert run.assessment.overall_score <= 44
        assert run.assessment.priority == "do_not_pursue"
