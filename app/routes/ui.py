from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Organisation, ResearchRun, PromptConfig, ContactLead
from app.prompts import DEFAULT_PROMPTS, get_prompt
from app.openai_client import client
from app.config import get_settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def ui_dashboard(request: Request, db: Session = Depends(get_db)):
    """Render the main dashboard."""
    organisations = db.query(Organisation).order_by(Organisation.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"organisations": organisations}
    )

@router.get("/organisations/{org_id}")
def ui_organisation_detail(request: Request, org_id: str, db: Session = Depends(get_db)):
    """Render the organisation detail page."""
    org = db.get(Organisation, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    
    # Get research runs ordered by newest first
    runs = db.query(ResearchRun).filter(ResearchRun.organisation_id == org.id).order_by(ResearchRun.started_at.desc()).all()
    
    return templates.TemplateResponse(
        request=request,
        name="detail.html",
        context={
            "org": org,
            "runs": runs,
        },
    )

@router.get("/config", response_class=HTMLResponse)
def config_page(request: Request, db: Session = Depends(get_db)):
    for name in DEFAULT_PROMPTS:
        get_prompt(db, name)
    prompts = list(db.scalars(select(PromptConfig).order_by(PromptConfig.name)).all())
    return templates.TemplateResponse(
        request=request,
        name="config.html", 
        context={"prompts": prompts}
    )

@router.post("/organisations/{org_id}/contacts/{contact_id}/draft-email")
def draft_contact_email(org_id: str, contact_id: str, db: Session = Depends(get_db)):
    contact = db.get(ContactLead, contact_id)
    org = db.get(Organisation, org_id)
    if not contact or not org or str(contact.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Contact not found")
        
    latest_run = db.query(ResearchRun).filter(ResearchRun.organisation_id == org.id).order_by(ResearchRun.started_at.desc()).first()
    assessment = latest_run.assessment if latest_run else None
    
    settings = get_settings()
    prompt = get_prompt(db, "EMAIL_DRAFTING_PROMPT")
    
    context = f"""Target Contact: {contact.name}, {contact.job_title}
Target Organisation: {org.name}, Sector: {org.sector}
"""
    if assessment:
        context += f"""
Research Assessment:
- ServiceNow Status: {assessment.servicenow_status}
- Opportunity Hypothesis: {assessment.opportunity_hypothesis}
- Suggested Outreach: {assessment.suggested_outreach}
"""
    
    response = client.chat.completions.create(
        model=settings.openai_extraction_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": context}
        ]
    )
    
    draft = response.choices[0].message.content
    contact.latest_email_draft = draft
    db.commit()
    
    return {"status": "success", "draft": draft}
