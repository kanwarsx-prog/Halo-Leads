from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import AuditStatus, SchoolAuditRun
from app.routes import prompts, research, schools, ui

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all tables exist (SQLite or Supabase PostgreSQL)
    Base.metadata.create_all(bind=engine)

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

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui")


# Register routers
app.include_router(ui.router)
app.include_router(schools.router)
app.include_router(research.router)
app.include_router(prompts.router)
