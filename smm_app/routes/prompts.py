from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from smm_app.database import get_db
from smm_app.models import PromptConfig
from smm_app.prompts import DEFAULT_PROMPTS, get_prompt
from smm_app.schemas import PromptConfigRead, PromptConfigUpdate

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptConfigRead])
def list_prompts(db: Session = Depends(get_db)):
    # Ensure defaults are populated
    for name in DEFAULT_PROMPTS:
        get_prompt(db, name)
    return list(db.scalars(select(PromptConfig)).all())


@router.put("/{name}", response_model=PromptConfigRead)
def update_prompt(name: str, payload: PromptConfigUpdate, db: Session = Depends(get_db)):
    prompt = db.get(PromptConfig, name)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    prompt.content = payload.content
    db.commit()
    db.refresh(prompt)
    return prompt
