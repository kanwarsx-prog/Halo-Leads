import uuid
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Organisation, ProspectingRun, ProspectingStatus
from app.schemas import OrganisationCreate, OrganisationRead, OrganisationStageUpdate


router = APIRouter()


@router.post("", response_model=OrganisationRead, status_code=201)
def create_organisation(
    payload: OrganisationCreate,
    db: Session = Depends(get_db),
) -> Organisation:
    """Create a new target organisation."""
    organisation = Organisation(
        name=payload.name.strip(),
        website=str(payload.website) if payload.website else None,
        country=payload.country,
        sector=payload.sector,
        notes=payload.notes,
    )
    db.add(organisation)
    db.commit()
    db.refresh(organisation)
    return organisation


@router.get("", response_model=list[OrganisationRead])
def list_organisations(
    db: Session = Depends(get_db),
) -> list[Organisation]:
    """List all target organisations, newest first."""
    return list(
        db.scalars(
            select(Organisation).order_by(Organisation.created_at.desc())
        )
    )


@router.get("/{organisation_id}", response_model=OrganisationRead)
def get_organisation(
    organisation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Organisation:
    """Get a single organisation by ID."""
    organisation = db.get(Organisation, organisation_id)

    if organisation is None:
        raise HTTPException(status_code=404, detail="Organisation not found")

    return organisation


@router.patch("/{organisation_id}/stage", response_model=OrganisationRead)
def update_organisation_stage(
    organisation_id: uuid.UUID,
    payload: OrganisationStageUpdate,
    db: Session = Depends(get_db),
) -> Organisation:
    """Update the pipeline stage of an organisation."""
    organisation = db.get(Organisation, organisation_id)
    if organisation is None:
        raise HTTPException(status_code=404, detail="Organisation not found")

    organisation.pipeline_stage = payload.pipeline_stage
    db.commit()
    db.refresh(organisation)
    return organisation


@router.delete("/{organisation_id}", status_code=204)
def delete_organisation(
    organisation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    """
    Delete an organisation and all associated research runs, sources,
    evidence items and assessments (cascade).
    """
    organisation = db.get(Organisation, organisation_id)

    if organisation is None:
        raise HTTPException(status_code=404, detail="Organisation not found")

    db.delete(organisation)
    db.commit()


class ProspectingRequest(BaseModel):
    criteria: str

@router.post("/prospecting/run")
def api_run_prospecting(
    request: ProspectingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    from app.prospecting_service import run_prospecting
    
    run = ProspectingRun(
        criteria=request.criteria,
        status=ProspectingStatus.queued,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    
    background_tasks.add_task(run_prospecting, run_id=run.id, criteria=request.criteria, db=db)
    
    return {"status": "started", "run_id": str(run.id)}

@router.get("/prospecting/runs/{run_id}/progress")
def get_prospecting_progress(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Get the live progress of a running prospecting job."""
    run = db.get(ProspectingRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    return {
        "status": run.status.value,
        "message": run.current_message or "Initializing..."
    }
