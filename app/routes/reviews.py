import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Assessment, ReviewStatus
from app.schemas import AssessmentRead, ReviewUpdate


router = APIRouter()


@router.patch("/assessments/{assessment_id}")
def review_assessment(
    assessment_id: uuid.UUID,
    payload: ReviewUpdate,
    db: Session = Depends(get_db),
) -> dict:
    """
    Record a human review decision on an assessment.

    Status must be one of: accepted, rejected, more_research.
    Notes are optional free text for the reviewer's reasoning.
    """
    assessment = db.get(Assessment, assessment_id)

    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    assessment.review_status = ReviewStatus(payload.status)
    assessment.review_notes = payload.notes

    db.commit()

    return {
        "assessment_id": str(assessment.id),
        "review_status": assessment.review_status.value,
        "review_notes": assessment.review_notes,
    }


@router.get("/assessments/{assessment_id}", response_model=AssessmentRead)
def get_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Assessment:
    """Get full assessment detail including scores, evidence summary and review status."""
    assessment = db.get(Assessment, assessment_id)

    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return assessment
