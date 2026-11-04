from pathlib import Path
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from smm_app.database import get_db
from smm_app.models import School, SchoolContact, SchoolAuditRun, PromptConfig, SchoolPipelineStage, ContactStatus, SchoolActivity
from smm_app.prompts import DEFAULT_PROMPTS, get_prompt

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    schools = db.query(School).order_by(School.created_at.desc()).all()
    # Exclude role placeholders from named contacts metric
    contacts_count = (
        db.query(SchoolContact)
        .filter(~SchoolContact.name.startswith("The "))
        .count()
    )
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
    named_contacts = [c for c in contacts if not c.name.startswith("The ")]
    has_named_senco = any("senco" in c.role.lower() or "inclusion" in c.role.lower() for c in named_contacts)
    has_named_head = any("head" in c.role.lower() or "principal" in c.role.lower() for c in named_contacts)

    activities = (
        db.query(SchoolActivity)
        .filter(SchoolActivity.school_id == school.id)
        .order_by(SchoolActivity.activity_date.desc(), SchoolActivity.created_at.desc())
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
            "named_contacts": named_contacts,
            "has_named_senco": has_named_senco,
            "has_named_head": has_named_head,
            "stages": [s.value for s in SchoolPipelineStage],
            "activities": activities,
        },
    )


@router.get("/contacts")
def contacts_directory(request: Request, db: Session = Depends(get_db)):
    # Only list actual named individuals, exclude role placeholders
    contacts = (
        db.query(SchoolContact)
        .join(School)
        .filter(~SchoolContact.name.startswith("The "))
        .order_by(School.name.asc(), SchoolContact.role.asc())
        .all()
    )
    schools = db.query(School).order_by(School.name.asc()).all()
    total_contacts = len(contacts)
    sencos = [c for c in contacts if "senco" in c.role.lower()]
    verified_emails = sum(1 for c in contacts if c.email_is_verified)

    return templates.TemplateResponse(
        request=request,
        name="contacts.html",
        context={
            "contacts": contacts,
            "schools": schools,
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
