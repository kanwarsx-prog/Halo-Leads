import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ResearchRun, ResearchStatus
from app.research_service import research_organisation
from app.schemas import AssessmentRead


router = APIRouter()


@router.post(
    "/organisations/{organisation_id}",
    status_code=202,
)
def start_research(
    organisation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    """
    Start a research run for the given organisation.

    Checks for an existing recent completed run (< 30 days) and returns it
    rather than running again. Blocks while research runs synchronously.

    HTTP 202 is returned because this endpoint will become asynchronous
    (background worker) before production use.
    """
    from datetime import datetime, timedelta, timezone

    # Cost control: if a completed assessment exists that is < 30 days old,
    # return the existing result. Require explicit "research_again" to rerun.
    existing_runs = list(
        db.scalars(
            select(ResearchRun)
            .where(
                ResearchRun.organisation_id == organisation_id,
                ResearchRun.status == ResearchStatus.completed,
            )
            .order_by(ResearchRun.completed_at.desc())
            .limit(1)
        )
    )

    if existing_runs:
        latest = existing_runs[0]
        if latest.completed_at and latest.completed_at > datetime.now(
            timezone.utc
        ) - timedelta(days=30):
            return {
                "research_run_id": str(latest.id),
                "status": latest.status.value,
                "note": (
                    "A completed assessment less than 30 days old already exists. "
                    "Use research_again=true to force a new run."
                ),
            }

    try:
        run = research_organisation(
            db=db,
            organisation_id=organisation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "research_run_id": str(run.id),
        "status": run.status.value,
    }


@router.post(
    "/organisations/{organisation_id}/research_again",
    status_code=202,
)
def force_research(
    organisation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    """Force a new research run even if a recent result exists."""
    try:
        run = research_organisation(
            db=db,
            organisation_id=organisation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "research_run_id": str(run.id),
        "status": run.status.value,
    }


@router.get("/runs/{run_id}")
def get_research_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    """Get the status and summary of a research run, including its assessment."""
    run = db.get(ResearchRun, run_id)

    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")

    return {
        "id": str(run.id),
        "organisation_id": str(run.organisation_id),
        "status": run.status.value,
        "research_model": run.research_model,
        "extraction_model": run.extraction_model,
        "prompt_version": run.prompt_version,
        "error_message": run.error_message,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "source_count": len(run.sources),
        "evidence_count": len(run.evidence_items),
        "assessment": (
            {
                "id": str(run.assessment.id),
                "overall_score": run.assessment.overall_score,
                "priority": run.assessment.priority,
                "servicenow_status": run.assessment.servicenow_status,
                "servicenow_confidence": run.assessment.servicenow_confidence,
                "basic_use_likelihood": run.assessment.basic_use_likelihood,
                "cost_pressure": run.assessment.cost_pressure,
                "renewal_proximity": run.assessment.renewal_proximity,
                "migration_fit": run.assessment.migration_fit,
                "apparent_use_cases": run.assessment.apparent_use_cases,
                "advanced_use_cases_found": run.assessment.advanced_use_cases_found,
                "opportunity_hypothesis": run.assessment.opportunity_hypothesis,
                "unknowns": run.assessment.unknowns,
                "recommended_stakeholders": run.assessment.recommended_stakeholders,
                "discovery_questions": run.assessment.discovery_questions,
                "suggested_outreach": run.assessment.suggested_outreach,
                "review_status": run.assessment.review_status.value,
                "scoring_version": run.assessment.scoring_version,
            }
            if run.assessment
            else None
        ),
    }


@router.get("/runs/{run_id}/sources")
def get_run_sources(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Get all source URLs discovered during a research run."""
    run = db.get(ResearchRun, run_id)

    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")

    return [
        {
            "id": str(source.id),
            "url": source.url,
            "title": source.title,
            "domain": source.domain,
            "is_official": source.is_official,
        }
        for source in run.sources
    ]


@router.get("/runs/{run_id}/evidence")
def get_run_evidence(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Get all evidence items extracted during a research run."""
    run = db.get(ResearchRun, run_id)

    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")

    return [
        {
            "id": str(item.id),
            "claim_type": item.claim_type,
            "claim": item.claim,
            "nature": item.nature.value,
            "strength": item.strength.value,
            "confidence": item.confidence,
            "source_url": item.source_url,
            "source_title": item.source_title,
            "supporting_excerpt": item.supporting_excerpt,
        }
        for item in run.evidence_items
    ]
