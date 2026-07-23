"""
Research orchestration service.

Controlled pipeline (no free-running agent):
  1. Create ResearchRun record (status=researching)
  2. Call OpenAI web search -> save discovery text + raw response
  3. Parse and save source URLs
  4. Call OpenAI structured extraction -> EvidenceBundle
  5. Validate evidence bundle deterministically
  6. Save evidence items
  7. Calculate deterministic score + apply pursuit gate
  8. Save Assessment
  9. Mark run completed

On any exception, the run is marked failed and the error message saved.
The caller is responsible for re-raising if needed.

For the MVP this runs synchronously. Move to a background worker queue
(e.g. Redis + ARQ or Celery) before batch processing.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Assessment,
    ContactLead,
    EvidenceItem,
    EvidenceNature,
    EvidenceStrength,
    Organisation,
    ResearchRun,
    ResearchSource,
    ResearchStatus,
)
from app.openai_research import extract_evidence_bundle, run_web_research, generate_research_plan
from app.prompts import PROMPT_VERSION, build_research_input, get_prompt
from app.scoring import SCORING_VERSION, apply_pursuit_gate, calculate_lead_score
from app.source_parser import collect_sources
from app.validation import validate_evidence_bundle


settings = get_settings()


def update_run_message(db: Session, run_id: uuid.UUID, message: str):
    run = db.get(ResearchRun, run_id)
    if run:
        run.current_message = message
        db.commit()

def research_organisation(
    *,
    db: Session,
    organisation_id: uuid.UUID,
) -> ResearchRun:
    """
    Run the full research pipeline for an organisation.

    Raises ValueError if the organisation is not found or evidence validation
    fails. Raises RuntimeError if the OpenAI extraction returns no parsed output.
    All exceptions are caught internally to mark the run as failed before
    re-raising.
    """
    organisation = db.get(Organisation, organisation_id)
    if organisation is None:
        raise ValueError("Organisation not found")

    run = ResearchRun(
        organisation_id=organisation.id,
        status=ResearchStatus.researching,
        research_model=settings.openai_research_model,
        extraction_model=settings.openai_extraction_model,
        prompt_version=PROMPT_VERSION,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        # Stage 0: Plan
        research_input = build_research_input(
            organisation_name=organisation.name,
            website=organisation.website,
            country=organisation.country,
            sector=organisation.sector,
            notes=organisation.notes,
        )
        research_instructions = get_prompt(db, "RESEARCH_INSTRUCTIONS")

        update_run_message(db, run.id, "Planning research strategy...")
        questions = generate_research_plan(
            organisation_name=organisation.name,
            research_input=research_input,
            instructions=research_instructions,
        )

        # Stage 1: web discovery (Multi-step)
        aggregated_discovery_text = ""
        all_raw_responses = []
        all_sources = []

        for i, q in enumerate(questions, 1):
            update_run_message(db, run.id, f"Deep dive {i}/{len(questions)}: {q}")
            q_input = f"{research_input}\n\nFocus specifically on answering this question: {q}"
            discovery_text, raw_response = run_web_research(
                research_input=q_input,
                instructions=research_instructions
            )
            aggregated_discovery_text += f"\n\n--- Research on: {q} ---\n{discovery_text}"
            all_raw_responses.append(raw_response)
            
            source_dicts = collect_sources(raw_response)
            all_sources.extend(source_dicts)

        run.discovery_text = aggregated_discovery_text.strip()
        run.raw_discovery_response = {"responses": all_raw_responses}

        # Deduplicate sources
        seen_urls = set()
        unique_sources = []
        for src in all_sources:
            if src["url"] not in seen_urls:
                seen_urls.add(src["url"])
                unique_sources.append(src)

        for source in unique_sources[: settings.max_research_sources]:
            db.add(
                ResearchSource(
                    research_run_id=run.id,
                    url=source["url"],
                    title=source.get("title"),
                    domain=source.get("domain"),
                    raw_metadata=source.get("raw_metadata"),
                )
            )

        run.status = ResearchStatus.extracting
        db.commit()

        update_run_message(db, run.id, "Synthesizing evidence and generating assessment...")

        # Stage 2: structured extraction
        bundle = extract_evidence_bundle(
            organisation_name=organisation.name,
            discovery_text=run.discovery_text,
            sources=unique_sources,
            instructions=get_prompt(db, "EXTRACTION_INSTRUCTIONS")
        )

        # Deterministic validation
        known_urls = {source["url"] for source in unique_sources}
        validation_errors = validate_evidence_bundle(bundle, known_urls)

        if validation_errors:
            error_msg = f"Evidence validation failed: {validation_errors}"
            raise ValueError(error_msg)

        # Save evidence items
        for item in bundle.evidence:
            db.add(
                EvidenceItem(
                    research_run_id=run.id,
                    claim_type=item.claim_type,
                    claim=item.claim,
                    nature=EvidenceNature(item.nature),
                    strength=EvidenceStrength(item.strength),
                    confidence=item.confidence,
                    source_url=item.source_url,
                    source_title=item.source_title,
                    supporting_excerpt=item.supporting_excerpt,
                )
            )

        # Save contact leads
        for lead in bundle.contact_leads:
            db.add(
                ContactLead(
                    organisation_id=run.organisation_id,
                    research_run_id=run.id,
                    name=lead.name,
                    job_title=lead.job_title,
                    linkedin_url=lead.linkedin_url,
                    notes=lead.notes,
                    source_url=lead.source_url,
                )
            )

        run.status = ResearchStatus.scoring
        db.commit()

        # Deterministic scoring
        scores = bundle.component_scores

        score_result = calculate_lead_score(
            servicenow_confidence=scores.servicenow_confidence,
            basic_use_likelihood=scores.basic_use_likelihood,
            cost_pressure=scores.cost_pressure,
            renewal_proximity=scores.renewal_proximity,
            migration_fit=scores.migration_fit,
        )

        overall_score, priority, pursuit_gate = apply_pursuit_gate(
            overall_score=score_result.overall_score,
            priority=score_result.priority,
            servicenow_status=bundle.servicenow_status,
        )

        assessment = Assessment(
            research_run_id=run.id,
            servicenow_confidence=scores.servicenow_confidence,
            basic_use_likelihood=scores.basic_use_likelihood,
            cost_pressure=scores.cost_pressure,
            renewal_proximity=scores.renewal_proximity,
            migration_fit=scores.migration_fit,
            overall_score=overall_score,
            priority=priority,
            servicenow_status=bundle.servicenow_status,
            pursuit_gate=pursuit_gate,
            apparent_use_cases=bundle.apparent_use_cases,
            advanced_use_cases_found=bundle.advanced_use_cases_found,
            opportunity_hypothesis=bundle.opportunity_hypothesis,
            unknowns=bundle.unknowns_to_validate,
            recommended_stakeholders=bundle.recommended_stakeholders,
            discovery_questions=bundle.discovery_questions,
            suggested_outreach=bundle.suggested_outreach,
            scoring_version=SCORING_VERSION,
        )
        db.add(assessment)

        run.status = ResearchStatus.completed
        run.completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(run)

        return run

    except Exception as exc:
        db.rollback()

        failed_run = db.get(ResearchRun, run.id)
        if failed_run is not None:
            failed_run.status = ResearchStatus.failed
            failed_run.error_message = str(exc)
            failed_run.current_message = f"Error: {str(exc)}"
            failed_run.completed_at = datetime.now(timezone.utc)
            db.commit()

        raise
