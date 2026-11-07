from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from smm_app.config import get_settings
from smm_app.database import Base, SessionLocal, engine
from smm_app.models import AuditStatus, SchoolAuditRun
from smm_app.routes import prompts, research, schools, ui, mcp_route, agent

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all tables exist (SQLite or Supabase PostgreSQL)
    Base.metadata.create_all(bind=engine)
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE smm_activities 
                ADD COLUMN IF NOT EXISTS next_follow_up_date TIMESTAMP WITH TIME ZONE,
                ADD COLUMN IF NOT EXISTS follow_up_task VARCHAR(300),
                ADD COLUMN IF NOT EXISTS follow_up_completed BOOLEAN DEFAULT FALSE;
            """))
            conn.commit()
    except Exception as e:
        print(f"Notice on activity migration: {e}")

    # Clean up any stuck research runs from prior server restart
    db = SessionLocal()
    try:
        stuck_runs = (
            db.query(SchoolAuditRun)
            .filter(SchoolAuditRun.status.in_([AuditStatus.queued, AuditStatus.researching]))
            .all()
        )
        for r in stuck_runs:
            r.status = AuditStatus.failed
            r.current_message = "Server restarted during audit"
        db.commit()
    finally:
        db.close()

    yield


app = FastAPI(
    title="See My Mind · Education Lead Agent",
    version="0.1.0",
    description="Education intelligence agent for UK Schools and Multi-Academy Trusts.",
    lifespan=lifespan,
)

# Mount static files with robust directory path

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    fav = STATIC_DIR / "favicon.ico"
    if fav.exists():
        return FileResponse(fav)
    return RedirectResponse(url="/seemymind/static/favicon.ico")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/seemymind/ui")


# Register routers
app.include_router(ui.router)
app.include_router(schools.router)
app.include_router(research.router)
app.include_router(prompts.router)
app.include_router(mcp_route.router)
app.include_router(agent.router)
