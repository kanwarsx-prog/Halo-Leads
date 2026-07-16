import uuid
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Organisation
from app.schemas import OrganisationCreate, OrganisationRead


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
    db: Session = Depends(get_db),
):
    from app.prospecting_service import run_prospecting
    batch = run_prospecting(request.criteria, db)
    return {"message": f"Successfully processed {len(batch.companies)} companies", "batch": batch.model_dump()}
