import uuid

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
import json
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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
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
                "status": "success",
                "message": "Found existing recent assessment.",
                "research_run_id": str(latest.id),
                "note": "Use research_again=true to force a new run."
            }

    # Start research in background
    run = ResearchRun(
        organisation_id=organisation_id,
        status=ResearchStatus.queued,
        research_model="gpt-4o-mini", # Will be updated by service
        extraction_model="gpt-4o", # Will be updated by service
        prompt_version="v1" # Will be updated by service
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(research_organisation, db=db, run_id=run.id)
    return {"status": "started", "run_id": str(run.id)}


@router.post(
    "/organisations/{organisation_id}/research_again",
    status_code=202,
)
def force_research(
    organisation_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Force a new research run even if a recent result exists."""
    run = ResearchRun(
        organisation_id=organisation_id,
        status=ResearchStatus.queued,
        research_model="gpt-4o-mini",
        extraction_model="gpt-4o",
        prompt_version="v1"
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(research_organisation, db=db, run_id=run.id)
    return {"status": "started", "run_id": str(run.id)}


@router.get("/organisations/{organisation_id}/runs/{run_id}/progress")
def get_research_progress(
    organisation_id: uuid.UUID,
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Get the live progress of a running research job."""
    run = db.get(ResearchRun, run_id)
    if not run or run.organisation_id != organisation_id:
        raise HTTPException(status_code=404, detail="Run not found")
        
    return {
        "status": run.status.value,
        "message": run.current_message or "Initializing..."
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
