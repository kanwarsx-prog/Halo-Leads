from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import (
    HALO_AUTH_PASS,
    HALO_AUTH_USER,
    SESSION_MAX_AGE_SECONDS,
    SMM_AUTH_PASS,
    SMM_AUTH_USER,
    create_token,
    is_halo_authenticated,
    is_smm_authenticated,
)
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
        from sqlalchemy import text
        with smm_engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE smm_activities 
                ADD COLUMN IF NOT EXISTS next_follow_up_date TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS follow_up_task VARCHAR(300),
                ADD COLUMN IF NOT EXISTS follow_up_completed BOOLEAN DEFAULT FALSE;
            """))
            conn.commit()
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
    description="Dual-engine lead intelligence platform with portal authentication.",
    lifespan=lifespan,
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

SMM_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "smm_app" / "templates"
smm_templates = Jinja2Templates(directory=str(SMM_TEMPLATES_DIR))


# Authentication Middleware
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Public static assets and health check
    if (
        path == "/health"
        or path.startswith("/static")
        or path.startswith("/seemymind/static")
        or path == "/favicon.ico"
    ):
        return await call_next(request)

    # Public login & logout endpoints
    if path in ["/login", "/logout", "/halo-leads/login", "/halo-leads/logout"]:
        return await call_next(request)

    # Halo Leads gate (explicit URL and sub-routes)
    if (
        path.startswith("/halo-leads")
        or path.startswith("/helo-leads")
        or path == "/halo"
        or path.startswith("/ui")
        or path.startswith("/organisations")
        or path.startswith("/research")
        or path.startswith("/prompts")
        or path.startswith("/reviews")
    ):
        if not is_halo_authenticated(request):
            return RedirectResponse(url="/halo-leads/login", status_code=303)
        return await call_next(request)

    # See My Mind gate (Default portal at "/" and "/seemymind/*")
    if not is_smm_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    return await call_next(request)


# Mount static assets

@app.get("/favicon.ico", include_in_schema=False)
def root_favicon():
    fav = SMM_TEMPLATES_DIR.parent / "static" / "favicon.ico"
    if fav.exists():
        return FileResponse(fav)
    return RedirectResponse(url="/seemymind/static/favicon.ico")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/seemymind", smm_subapp)


# ==============================================================================
# See My Mind Authentication Routes
# ==============================================================================

@app.get("/login", include_in_schema=False)
def smm_login_page(request: Request):
    """Render See My Mind branded login page."""
    if is_smm_authenticated(request):
        return RedirectResponse(url="/seemymind/ui")
    return smm_templates.TemplateResponse(request=request, name="login.html")


@app.post("/login", include_in_schema=False)
async def smm_login_submit(request: Request):
    """Verify credentials for See My Mind."""
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

    if username == SMM_AUTH_USER and password == SMM_AUTH_PASS:
        token = create_token("smm")
        response = RedirectResponse(url="/seemymind/ui", status_code=303)
        response.set_cookie(
            key="smm_session",
            value=token,
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
        )
        return response

    return smm_templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Invalid username or password. Please try again."},
        status_code=401,
    )


@app.get("/logout", include_in_schema=False)
def smm_logout():
    """Sign out of See My Mind."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("smm_session")
    return response


# ==============================================================================
# Halo Leads Authentication & Entry Routes
# ==============================================================================

@app.get("/halo-leads/login", include_in_schema=False)
def halo_login_page(request: Request):
    """Render HaloITSM branded login page."""
    if is_halo_authenticated(request):
        return RedirectResponse(url="/ui")
    return templates.TemplateResponse(request=request, name="halo_login.html")


@app.post("/halo-leads/login", include_in_schema=False)
async def halo_login_submit(request: Request):
    """Verify credentials for Halo Leads."""
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

    if username == HALO_AUTH_USER and password == HALO_AUTH_PASS:
        token = create_token("halo")
        response = RedirectResponse(url="/ui", status_code=303)
        response.set_cookie(
            key="halo_session",
            value=token,
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
        )
        return response

    return templates.TemplateResponse(
        request=request,
        name="halo_login.html",
        context={"error": "Invalid username or password. Please try again."},
        status_code=401,
    )


@app.get("/halo-leads/logout", include_in_schema=False)
def halo_logout():
    """Sign out of Halo Leads."""
    response = RedirectResponse(url="/halo-leads/login", status_code=303)
    response.delete_cookie("halo_session")
    return response


# Default root redirects to See My Mind dashboard (if authenticated)
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
