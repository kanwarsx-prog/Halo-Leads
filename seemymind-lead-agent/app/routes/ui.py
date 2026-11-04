from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import School, SchoolContact, SchoolAuditRun, PromptConfig, SchoolPipelineStage, ContactStatus
from app.prompts import DEFAULT_PROMPTS, get_prompt

router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    schools = db.query(School).order_by(School.created_at.desc()).all()
    contacts_count = db.query(SchoolContact).count()
    high_priority_count = sum(1 for s in schools if s.priority == "Immediate Focus")

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "schools": schools,
            "total_schools": len(schools),
            "contacts_count": contacts_count,
            "high_priority_count": high_priority_count,
        },
    )


@router.get("/schools/{school_id}")
def school_detail(school_id: str, request: Request, db: Session = Depends(get_db)):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    runs = (
        db.query(SchoolAuditRun)
        .filter(SchoolAuditRun.school_id == school.id)
        .order_by(SchoolAuditRun.started_at.desc())
        .all()
    )
    latest_run = runs[0] if runs else None

    contacts = (
        db.query(SchoolContact)
        .filter(SchoolContact.school_id == school.id)
        .order_by(SchoolContact.created_at.asc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="detail.html",
        context={
            "school": school,
            "runs": runs,
            "latest_run": latest_run,
            "contacts": contacts,
            "stages": [s.value for s in SchoolPipelineStage],
        },
    )


@router.get("/contacts")
def contacts_directory(request: Request, db: Session = Depends(get_db)):
    contacts = (
        db.query(SchoolContact)
        .join(School)
        .order_by(School.name.asc(), SchoolContact.role.asc())
        .all()
    )
    total_contacts = len(contacts)
    sencos = [c for c in contacts if "senco" in c.role.lower()]
    verified_emails = sum(1 for c in contacts if c.email_is_verified)

    return templates.TemplateResponse(
        request=request,
        name="contacts.html",
        context={
            "contacts": contacts,
            "total_contacts": total_contacts,
            "senco_count": len(sencos),
            "verified_count": verified_emails,
        },
    )


@router.get("/config")
def prompt_config(request: Request, db: Session = Depends(get_db)):
    for name in DEFAULT_PROMPTS:
        get_prompt(db, name)
    prompts = db.query(PromptConfig).all()

    return templates.TemplateResponse(
        request=request,
        name="config.html",
        context={"prompts": prompts},
    )
