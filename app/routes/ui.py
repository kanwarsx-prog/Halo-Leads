from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Organisation, ResearchRun, PromptConfig, ContactLead
from app.prompts import DEFAULT_PROMPTS, get_prompt
from app.openai_client import client
from app.config import get_settings
from app.openai_research import run_web_research

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

class EmailSendRequest(BaseModel):
    draft_text: str
    recipient_email: str
    include_attachment: bool = True

class ManualContactCreate(BaseModel):
    name: str
    job_title: str
    email: str | None = None
    linkedin_url: str | None = None

class DraftResult(BaseModel):
    email_draft: str
    linkedin_draft: str

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

@router.get("/contacts")
def ui_contacts(request: Request, db: Session = Depends(get_db)):
    """Render the master contacts dashboard."""
    contacts = db.query(ContactLead).join(Organisation).order_by(Organisation.name.asc(), ContactLead.name.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="contacts.html",
        context={"contacts": contacts}
    )

@router.get("/organisations/{org_id}/contacts/{contact_id}")
def ui_contact_detail(org_id: str, contact_id: str, request: Request, db: Session = Depends(get_db)):
    """Render the dedicated contact profile page."""
    contact = db.get(ContactLead, contact_id)
    org = db.get(Organisation, org_id)
    
    if not contact or not org or str(contact.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Contact not found")
        
    return templates.TemplateResponse(
        request=request,
        name="contact_detail.html",
        context={"org": org, "lead": contact}
    )

@router.post("/organisations/{org_id}/contacts/manual")
def ui_create_contact(org_id: str, data: ManualContactCreate, db: Session = Depends(get_db)):
    org = db.get(Organisation, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
        
    contact = ContactLead(
        organisation_id=org.id,
        name=data.name,
        job_title=data.job_title,
        email=data.email,
        linkedin_url=data.linkedin_url
    )
    db.add(contact)
    db.commit()
    return {"status": "success", "contact_id": str(contact.id)}

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
    if settings.calendar_link:
        prompt = prompt.replace("[Your Calendar Link]", settings.calendar_link)
        
    context = f"""Target Contact: {contact.name}, {contact.job_title}
Target Organisation: {org.name}, Sector: {org.sector}
Contact Notes: {contact.notes or 'None'}
"""
    if assessment:
        context += f"""
Research Assessment:
- ITSM Status: {assessment.itsm_status}
- Identified Tools: {assessment.identified_tools}
- Opportunity Hypothesis: {assessment.opportunity_hypothesis}
- Suggested Outreach: {assessment.suggested_outreach}
"""
    
    response = client.beta.chat.completions.parse(
        model=settings.openai_extraction_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": context}
        ],
        response_format=DraftResult
    )
    
    result = response.choices[0].message.parsed
    contact.latest_email_draft = result.email_draft
    contact.latest_linkedin_draft = result.linkedin_draft
    db.commit()
    
    return {"status": "success", "draft": result.email_draft, "linkedin_draft": result.linkedin_draft}

@router.post("/organisations/{org_id}/contacts/{contact_id}/deep-research")
def deep_research_contact(org_id: str, contact_id: str, db: Session = Depends(get_db)):
    contact = db.get(ContactLead, contact_id)
    org = db.get(Organisation, org_id)
    if not contact or not org or str(contact.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Contact not found")
        
    prompt = get_prompt(db, "CONTACT_RESEARCH_INSTRUCTIONS")
    input_text = f"Research {contact.name}, {contact.job_title} at {org.name}."
    
    discovery_text, _ = run_web_research(
        research_input=input_text,
        instructions=prompt
    )
    
    # Parse the deep dive findings to extract email and structured notes
    from app.schemas import ContactDeepDiveResult
    import json
    
    try:
        from config import settings
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.beta.chat.completions.parse(
            model=settings.openai_extraction_model,
            messages=[
                {"role": "system", "content": "Extract the deep dive notes and email address into the JSON schema."},
                {"role": "user", "content": discovery_text}
            ],
            response_format=ContactDeepDiveResult
        )
        result = response.choices[0].message.parsed
        contact.notes = result.notes
        if result.email:
            contact.email = result.email
            contact.email_is_guessed = result.email_is_guessed
    except Exception as e:
        # Fallback if structured parsing fails
        contact.notes = discovery_text

    db.commit()
    
    return {
        "status": "success", 
        "notes": contact.notes,
        "email": contact.email,
        "email_is_guessed": contact.email_is_guessed
    }


class SendEmailRequest(BaseModel):
    draft_text: str
    recipient_email: str
    include_attachment: bool = False

@router.post("/organisations/{org_id}/contacts/{contact_id}/send-email")
def send_contact_email(org_id: str, contact_id: str, payload: SendEmailRequest, db: Session = Depends(get_db)):
    contact = db.get(ContactLead, contact_id)
    org = db.get(Organisation, org_id)
    if not contact or not org or str(contact.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Contact not found")
        
    if not payload.recipient_email:
        raise HTTPException(status_code=400, detail="Recipient email address is required")
        
    if contact.email != payload.recipient_email:
        contact.email = payload.recipient_email
        db.commit()

    from app.email_service import send_email
    settings = get_settings()
    
    subject = f"HaloITSM and {org.name}"
    
    # Extract subject if the AI put "Subject: ..." in the draft
    lines = payload.draft_text.split("\n")
    body = payload.draft_text
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0][8:].strip()
        body = "\n".join(lines[1:]).strip()

    try:
        attachment_path = settings.default_attachment_path if payload.include_attachment else None
        
        send_email(
            to_email=payload.recipient_email,
            subject=subject,
            body=body,
            attachment_path=attachment_path
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
        
    return {"status": "success", "message": "Email sent"}
