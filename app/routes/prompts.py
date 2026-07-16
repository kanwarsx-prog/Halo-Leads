from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import PromptConfig
from app.schemas import PromptConfigRead, PromptConfigUpdate
from app.prompts import DEFAULT_PROMPTS, get_prompt

router = APIRouter()

@router.get("", response_model=list[PromptConfigRead])
def list_prompts(db: Session = Depends(get_db)):
    # Ensure defaults are seeded
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
