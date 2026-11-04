import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from smm_app.database import get_db
from smm_app.models import AuditStatus, School, SchoolAuditRun, SchoolContact
from smm_app.school_research import audit_school, draft_outreach_for_school

router = APIRouter(prefix="/research", tags=["research"])


def background_audit_runner(run_id: str):
    from smm_app.database import SessionLocal
    db = SessionLocal()
    try:
        audit_school(db, run_id)
    finally:
        db.close()


@router.post("/schools/{school_id}")
def trigger_school_audit(
    school_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    run = SchoolAuditRun(
        school_id=school.id,
        status=AuditStatus.queued,
        current_message="Queued for audit...",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(background_audit_runner, run.id)

    return {
        "run_id": run.id,
        "school_id": school.id,
        "status": run.status.value,
        "message": "Audit started",
    }


@router.get("/runs/{run_id}")
def get_audit_status(run_id: str, db: Session = Depends(get_db)):
    run = db.get(SchoolAuditRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Audit run not found")

    return {
        "id": run.id,
        "status": run.status.value,
        "current_message": run.current_message,
        "error_message": run.error_message,
        "detected_tools": run.detected_tools,
        "strengths_found": run.strengths_found,
        "challenges_found": run.challenges_found,
        "recommended_angle": run.recommended_angle,
        "send_report_url": run.send_report_url,
        "completed_at": run.completed_at,
    }


@router.post("/schools/{school_id}/redraft")
def trigger_redraft(school_id: str, db: Session = Depends(get_db)):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    draft_outreach_for_school(db, school.id)
    return {"message": "Outreach drafts re-generated"}
