import json
from sqlalchemy.orm import Session
from app.config import get_settings
from app.models import Organisation, ContactLead
from app.openai_client import client
from app.openai_research import run_web_research
from app.prompts import build_prospecting_input, get_prompt
from app.schemas import ProspectingBatch

settings = get_settings()

def run_prospecting(criteria: str, db: Session) -> ProspectingBatch:
    research_input = build_prospecting_input(criteria)
    discovery_text, raw_response = run_web_research(
        research_input=research_input, 
        instructions=get_prompt(db, "PROSPECTING_INSTRUCTIONS")
    )
    
    response = client.responses.parse(
        model=settings.openai_extraction_model,
        instructions=get_prompt(db, "PROSPECTING_EXTRACTION_INSTRUCTIONS"),
        input=discovery_text,
        text_format=ProspectingBatch,
    )
    
    if response.output_parsed is None:
        raise RuntimeError("The extraction response did not contain parsed output")
        
    batch = response.output_parsed
    
    for comp in batch.companies:
        org = Organisation(
            name=comp.name,
            website=str(comp.website) if comp.website else None,
            country=comp.country,
            sector=comp.sector,
            notes=comp.notes,
        )
        db.add(org)
        db.flush() # get ID
        
        for lead in comp.contact_leads:
            cl = ContactLead(
                organisation_id=org.id,
                name=lead.name,
                job_title=lead.job_title,
                linkedin_url=lead.linkedin_url,
                notes=lead.notes,
                source_url=lead.source_url,
            )
            db.add(cl)
    
    db.commit()
    return batch
