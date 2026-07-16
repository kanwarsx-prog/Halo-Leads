from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Organisation, ResearchRun, PromptConfig
from app.prompts import DEFAULT_PROMPTS, get_prompt

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
