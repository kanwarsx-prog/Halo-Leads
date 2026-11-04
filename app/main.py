from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import SessionLocal
from app.models import ProspectingRun, ProspectingStatus, ResearchRun, ResearchStatus
from app.routes import organisations, prompts, research, reviews, ui

from smm_app.database import Base as SMMBase, SessionLocal as SMMSessionLocal, engine as smm_engine
from smm_app.main import app as smm_subapp
from smm_app.models import AuditStatus as SMMAuditStatus, SchoolAuditRun


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure See My Mind tables exist
    try:
        SMMBase.metadata.create_all(bind=smm_engine)
    except Exception as e:
        print(f"Warning: SMM tables initialization: {e}")

    # Startup: clean up stuck Halo runs
    db = SessionLocal()
    try:
        stuck_research = db.query(ResearchRun).filter(
            ResearchRun.status.in_([
                ResearchStatus.queued,
                ResearchStatus.researching,
                ResearchStatus.extracting,
                ResearchStatus.scoring,
            ])
        ).all()
        for r in stuck_research:
            r.status = ResearchStatus.failed
            r.current_message = "Failed due to server restart"

        stuck_prospecting = db.query(ProspectingRun).filter(
            ProspectingRun.status.in_([ProspectingStatus.queued, ProspectingStatus.running])
        ).all()
        for p in stuck_prospecting:
            p.status = ProspectingStatus.failed
            p.current_message = "Failed due to server restart"

        db.commit()
    finally:
        db.close()

    # Startup: clean up stuck See My Mind runs
    smm_db = SMMSessionLocal()
    try:
        stuck_smm = smm_db.query(SchoolAuditRun).filter(
            SchoolAuditRun.status.in_([SMMAuditStatus.queued, SMMAuditStatus.researching])
        ).all()
        for r in stuck_smm:
            r.status = SMMAuditStatus.failed
            r.current_message = "Server restarted during audit"
        smm_db.commit()
    finally:
        smm_db.close()

    yield


app = FastAPI(
    title="LeadGen Multi-Agent Suite (HaloITSM & See My Mind)",
    version="0.2.0",
    description=(
        "Dual-engine lead intelligence platform featuring: "
        "1. HaloITSM Value-Gap Prospecting Engine (/ui) "
        "2. See My Mind UK Schools & MATs Outreach Engine (/seemymind/ui)"
    ),
    lifespan=lifespan,
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Mount Halo static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Mount See My Mind sub-application at /seemymind
app.mount("/seemymind", smm_subapp)


# Default root is See My Mind Education Agent
@app.get("/", include_in_schema=False)
def root():
    """Main page of the app is See My Mind Education Lead Agent."""
    return RedirectResponse(url="/seemymind/ui")


# Explicit entrance for Halo Leads (only accessible via explicit URL)
@app.get("/halo-leads", include_in_schema=False)
@app.get("/helo-leads", include_in_schema=False)
@app.get("/halo", include_in_schema=False)
def halo_shortcut():
    """Explicit entry point for HaloITSM Prospecting Pipeline."""
    return RedirectResponse(url="/ui")


# Halo Lead Agent routers
app.include_router(
    ui.router,
    prefix="/ui",
    tags=["Halo UI"],
    include_in_schema=False,
)
app.include_router(
    organisations.router,
    prefix="/organisations",
    tags=["Halo Organisations"],
)
app.include_router(
    research.router,
    prefix="/research",
    tags=["Halo Research"],
)
app.include_router(
    prompts.router,
    prefix="/prompts",
    tags=["Halo Prompts"],
)
app.include_router(
    reviews.router,
    prefix="/reviews",
    tags=["Halo Reviews"],
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """API health check."""
    return {
        "status": "ok",
        "engines": "HaloITSM, SeeMyMind",
    }
