from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routes import organisations, prompts, research, reviews, ui

app = FastAPI(
    title="HaloITSM Value-Gap Lead Agent",
    version="0.1.0",
    description=(
        "Evidence-backed lead intelligence tool that identifies organisations "
        "which appear to use ServiceNow for basic ITSM and may be suitable for "
        "a HaloITSM value assessment."
    ),
)

# Mount static files for UI
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", include_in_schema=False)
def root():
    """Redirect root to UI dashboard."""
    return RedirectResponse(url="/ui")

app.include_router(
    ui.router,
    prefix="/ui",
    tags=["ui"],
    include_in_schema=False
)

app.include_router(
    organisations.router,
    prefix="/organisations",
    tags=["organisations"],
)
app.include_router(
    research.router,
    prefix="/research",
    tags=["research"],
)
app.include_router(
    prompts.router,
    prefix="/prompts",
    tags=["prompts"],
)
app.include_router(
    reviews.router,
    prefix="/reviews",
    tags=["reviews"],
)

@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """API health check."""
    return {"status": "ok"}
