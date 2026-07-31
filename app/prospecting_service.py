import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.config import get_settings
from app.models import Organisation, ContactLead, ProspectingRun, ProspectingStatus
from app.openai_client import client
from app.openai_research import run_web_research, generate_prospecting_plan
from app.prompts import build_prospecting_input, get_prompt
from app.schemas import ProspectingBatch

settings = get_settings()

def update_run_message(db: Session, run_id: uuid.UUID, message: str):
    run = db.get(ProspectingRun, run_id)
    if run:
        run.current_message = message
        db.commit()

def run_prospecting(run_id: uuid.UUID, criteria: str, db: Session) -> ProspectingBatch:
    run = db.get(ProspectingRun, run_id)
    if not run:
        raise ValueError("Prospecting run not found")

    try:
        run.status = ProspectingStatus.running
        db.commit()

        update_run_message(db, run.id, "Planning prospecting strategy...")
        
        research_input = build_prospecting_input(criteria)
        plan_instructions = get_prompt(db, "PROSPECTING_PLAN_INSTRUCTIONS")
        
        missions = generate_prospecting_plan(
            criteria=research_input,
            instructions=plan_instructions
        )

        aggregated_discovery_text = ""
        web_instructions = get_prompt(db, "PROSPECTING_INSTRUCTIONS")

        for i, mission in enumerate(missions, 1):
            update_run_message(db, run.id, f"Deep dive {i}/{len(missions)}: {mission}")
            q_input = f"{research_input}\n\nFocus specifically on answering this mission: {mission}"
            discovery_text, raw_response = run_web_research(
                research_input=q_input, 
                instructions=web_instructions
            )
            aggregated_discovery_text += f"\n\n--- Mission: {mission} ---\n{discovery_text}"

        update_run_message(db, run.id, "Extracting discovered companies and contacts...")
        
        response = client.responses.parse(
            model=settings.openai_extraction_model,
            instructions=get_prompt(db, "PROSPECTING_EXTRACTION_INSTRUCTIONS"),
            input=aggregated_discovery_text,
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
                    email=lead.email,
                    email_is_guessed=lead.email_is_guessed,
                    notes=lead.notes,
                    source_url=lead.source_url,
                )
                db.add(cl)
        
        run.status = ProspectingStatus.completed
        run.completed_at = datetime.now(timezone.utc)
        run.results_count = len(batch.companies)
        db.commit()
        
        return batch

    except Exception as exc:
        db.rollback()
        failed_run = db.get(ProspectingRun, run_id)
        if failed_run:
            failed_run.status = ProspectingStatus.failed
            failed_run.error_message = str(exc)
            failed_run.current_message = f"Error: {str(exc)}"
            failed_run.completed_at = datetime.now(timezone.utc)
            db.commit()
        raise
