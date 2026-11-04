import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from smm_app.config import get_settings
from smm_app.models import (
    AuditStatus,
    ContactStatus,
    School,
    SchoolAuditRun,
    SchoolContact,
    SchoolPipelineStage,
    SchoolActivity,
)
from smm_app.openai_client import client
from smm_app.prompts import get_prompt
from smm_app.schemas import OutreachDraftResult, SchoolAuditExtraction
from smm_app.scoring import calculate_school_score

settings = get_settings()


def update_audit_message(db: Session, run_id: str, message: str):
    run = db.get(SchoolAuditRun, run_id)
    if run:
        run.current_message = message
        db.commit()


def run_web_search(query_input: str, instructions: str) -> tuple[str, dict[str, Any]]:
    """Execute live web search using OpenAI's hosted tool."""
    response = client.responses.create(
        model=settings.openai_model,
        instructions=instructions,
        tools=[{"type": "web_search_preview"}],
        input=query_input,
    )
    raw_response = response.model_dump(mode="json")
    return response.output_text, raw_response


def audit_school(db: Session, run_id: str) -> SchoolAuditExtraction:
    """Run the complete education intelligence discovery for a school."""
    run = db.get(SchoolAuditRun, run_id)
    if not run:
        raise ValueError(f"Discovery run {run_id} not found")

    school = db.get(School, run.school_id)
    if not school:
        raise ValueError(f"School {run.school_id} not found")

    try:
        run.status = AuditStatus.researching
        db.commit()

        # Step 1: Formulate search query
        update_audit_message(db, run.id, f"Discovering {school.name}'s SEND Information Report & Ofsted history...")
        search_prompt = f"""
School Name: {school.name}
Phase: {school.phase or 'Primary'}
Postcode / Location: {school.postcode or 'UK'}
Official Website: {school.website or 'Find via search'}
Multi-Academy Trust: {school.mat_name or 'Single Academy / Maintained'}
Known SEN %: {school.sen_percentage or 'Unknown'}%

Please investigate:
1. Their statutory SEND Information Report / SEN Policy: Find the named SENCO, their direct contact email/phone, and how they review support.
2. Their latest Ofsted inspection report: Find the specific findings and verbatim quotes about SEND and inclusion.
3. Mentions of tools they currently use (e.g. Edukey / Provision Map, CPOMS, SIMS, Arbor, Bromcom).
"""
        discovery_instructions = get_prompt(db, "SCHOOL_AUDIT_INSTRUCTIONS")
        discovery_text, _ = run_web_search(search_prompt, discovery_instructions)
        run.raw_findings = discovery_text
        db.commit()

        # Step 2: Structured extraction
        update_audit_message(db, run.id, "Extracting structured SEND intelligence & staff contacts...")
        extract_instructions = get_prompt(db, "SCHOOL_EXTRACTION_INSTRUCTIONS")

        response = client.responses.parse(
            model=settings.openai_extraction_model,
            instructions=extract_instructions,
            input=f"School: {school.name}\n\nResearch Findings:\n{discovery_text}",
            text_format=SchoolAuditExtraction,
        )

        if response.output_parsed is None:
            raise RuntimeError("Extraction did not return parsed data")

        extraction: SchoolAuditExtraction = response.output_parsed

        # Step 3: Update School Record
        if extraction.ofsted_rating:
            school.ofsted_rating = extraction.ofsted_rating
        if extraction.ofsted_inspection_date:
            school.ofsted_inspection_date = extraction.ofsted_inspection_date
        if extraction.ofsted_send_quote:
            school.ofsted_send_excerpt = extraction.ofsted_send_quote
        if extraction.send_report_url:
            run.send_report_url = extraction.send_report_url

        run.detected_tools = ", ".join(extraction.detected_tools) if extraction.detected_tools else None
        run.strengths_found = "\n".join(f"• {s}" for s in extraction.strengths_found)
        run.challenges_found = "\n".join(f"• {c}" for c in extraction.challenges_found)
        run.recommended_angle = extraction.recommended_angle

        # Calculate deterministic score
        score_result = calculate_school_score(
            need_score=extraction.need_score,
            fit_score=extraction.fit_score,
            named_senco_found=bool(extraction.named_senco),
            is_part_of_mat=bool(school.mat_name),
            has_ofsted_quote=bool(extraction.ofsted_send_quote),
            sen_percentage=school.sen_percentage,
        )
        school.overall_score = score_result.overall_score
        school.priority = score_result.priority
        if school.pipeline_stage == SchoolPipelineStage.discovered:
            school.pipeline_stage = SchoolPipelineStage.qualified

        # Step 4: Add or update Key Contacts
        # Primary Contact: SENCO
        if extraction.named_senco:
            senco_contact = db.query(SchoolContact).filter(
                SchoolContact.school_id == school.id,
                SchoolContact.role.ilike("%SENCO%"),
            ).first()

            if not senco_contact:
                senco_contact = SchoolContact(
                    school_id=school.id,
                    name=extraction.named_senco,
                    role="SENCO",
                    email=extraction.senco_email,
                    email_is_verified=bool(extraction.senco_email),
                    phone_extension=extraction.senco_phone,
                    source="Statutory SEND Information Report",
                    personalized_hook=extraction.recommended_angle,
                )
                db.add(senco_contact)
            else:
                senco_contact.name = extraction.named_senco
                if extraction.senco_email:
                    senco_contact.email = extraction.senco_email
                    senco_contact.email_is_verified = True
                senco_contact.personalized_hook = extraction.recommended_angle

        # Secondary Contact: Headteacher
        if extraction.headteacher_name:
            head_contact = db.query(SchoolContact).filter(
                SchoolContact.school_id == school.id,
                SchoolContact.role.ilike("%Head%"),
            ).first()

            if not head_contact:
                head_contact = SchoolContact(
                    school_id=school.id,
                    name=extraction.headteacher_name,
                    role="Headteacher",
                    email=extraction.headteacher_email,
                    email_is_verified=bool(extraction.headteacher_email),
                    source="School Leadership Directory",
                    personalized_hook=extraction.recommended_angle,
                )
                db.add(head_contact)

        # Additional contacts from extraction
        for staff in extraction.additional_contacts:
            existing = db.query(SchoolContact).filter(
                SchoolContact.school_id == school.id,
                SchoolContact.name == staff.name,
            ).first()
            if not existing:
                db.add(
                    SchoolContact(
                        school_id=school.id,
                        name=staff.name,
                        role=staff.role,
                        email=staff.email,
                        email_is_verified=staff.email_is_verified,
                        phone_extension=staff.phone_extension,
                        source=staff.source or "Website Staff Directory",
                        personalized_hook=extraction.recommended_angle,
                    )
                )

        db.flush()

        # Step 5: Complete Discovery (Drafts generated on-demand)
        update_audit_message(db, run.id, "Discovery complete! Key contacts & SEND intelligence ready.")
        run.status = AuditStatus.completed
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

        return extraction

    except Exception as exc:
        db.rollback()
        failed_run = db.get(SchoolAuditRun, run_id)
        if failed_run:
            failed_run.status = AuditStatus.failed
            failed_run.error_message = str(exc)
            db.commit()
        raise


def draft_outreach_for_school(
    db: Session,
    school_id: str,
    extraction: SchoolAuditExtraction | None = None,
    custom_instructions: str | None = None,
) -> dict[str, Any]:
    """Generate on-demand empathetic email drafts and 1-page physical letters, factoring in CRM activities & notes."""
    school = db.get(School, school_id)
    if not school:
        raise ValueError(f"School {school_id} not found")

    contacts = db.query(SchoolContact).filter(SchoolContact.school_id == school.id).all()
    outreach_prompt_instructions = get_prompt(db, "OUTREACH_DRAFTING_PROMPT")

    # Ensure both SENCO and Headteacher contacts exist
    senco = next((c for c in contacts if "senco" in c.role.lower() or "inclusion" in c.role.lower()), None)
    if not senco:
        senco = next((c for c in contacts if "head" not in c.role.lower() and "principal" not in c.role.lower()), None)
    if not senco:
        is_named = bool(extraction and extraction.named_senco)
        senco_name = extraction.named_senco if is_named else "The SENCO / Inclusion Lead"
        senco = SchoolContact(
            school_id=school.id,
            name=senco_name,
            role="SENCO",
            email=extraction.senco_email if is_named else None,
            email_is_verified=bool(is_named and extraction.senco_email),
            phone_extension=extraction.senco_phone if is_named else None,
            source="Statutory SEND Information Report" if is_named else "Unassigned Role",
            personalized_hook=extraction.recommended_angle if extraction else None,
        )
        db.add(senco)
        db.flush()

    head = next((c for c in contacts if "head" in c.role.lower() or "principal" in c.role.lower()), None)
    if not head:
        is_named_head = bool(extraction and extraction.headteacher_name)
        head_name = extraction.headteacher_name if is_named_head else "The Headteacher / Principal"
        head = SchoolContact(
            school_id=school.id,
            name=head_name,
            role="Headteacher",
            email=extraction.headteacher_email if is_named_head else None,
            email_is_verified=bool(is_named_head and extraction.headteacher_email),
            source="School Leadership" if is_named_head else "Unassigned Role",
            personalized_hook=extraction.recommended_angle if extraction else None,
        )
        db.add(head)
        db.flush()

    # Retrieve all recorded pipeline activities and discussion notes
    activities = (
        db.query(SchoolActivity)
        .filter(SchoolActivity.school_id == school.id)
        .order_by(SchoolActivity.activity_date.desc(), SchoolActivity.created_at.desc())
        .all()
    )

    if activities:
        act_items = []
        for a in activities:
            dt_str = a.activity_date.strftime("%d %b %Y") if a.activity_date else "Recently"
            who = f" (Staff: {a.contact_name})" if a.contact_name else ""
            act_items.append(f"• [{dt_str}] Type: {a.activity_type.upper()}{who} | Title: {a.title}")
            if a.notes:
                act_items.append(f"  Discussion Notes: {a.notes.strip()}")
            if a.follow_up_task and not a.follow_up_completed:
                act_items.append(f"  Open Follow-up Task: {a.follow_up_task}")
        activities_summary = "\n".join(act_items)
    else:
        activities_summary = "No prior conversations, phone calls, or CRM notes recorded yet (Initial outreach)."

    # Retrieve audit intelligence
    latest_run = (
        db.query(SchoolAuditRun)
        .filter(SchoolAuditRun.school_id == school.id, SchoolAuditRun.status == AuditStatus.completed)
        .order_by(SchoolAuditRun.started_at.desc())
        .first()
    )

    tools_info = (
        ", ".join(extraction.detected_tools)
        if extraction and extraction.detected_tools
        else (latest_run.detected_tools if latest_run and latest_run.detected_tools else "Not explicitly stated")
    )
    strengths_info = (
        ", ".join(extraction.strengths_found)
        if extraction and extraction.strengths_found
        else (latest_run.strengths_found if latest_run and latest_run.strengths_found else "Inclusive ethos")
    )
    challenges_info = (
        ", ".join(extraction.challenges_found)
        if extraction and extraction.challenges_found
        else (latest_run.challenges_found if latest_run and latest_run.challenges_found else "High caseload / transition support")
    )
    angle_info = (
        extraction.recommended_angle
        if extraction and extraction.recommended_angle
        else (latest_run.recommended_angle if latest_run and latest_run.recommended_angle else "Workload reduction and daily home-school loop")
    )

    today_str = datetime.now().strftime("%d %B %Y")

    prompt_input = f"""
School Name: {school.name}
School Address: {school.address or school.postcode or 'England, UK'}
Current Date: {today_str}
Phase: {school.phase or 'Primary'}
Multi-Academy Trust: {school.mat_name or 'Maintained / Single Academy'}
SENCO Name: {senco.name} ({senco.role})
Headteacher Name: {head.name if head else 'The Headteacher'}

Ofsted Inspection Quote regarding SEND:
{school.ofsted_send_excerpt or 'Not available'}

Identified SEND Context / Tools:
- Tools: {tools_info}
- Strengths: {strengths_info}
- Challenges: {challenges_info}
- Recommended Angle: {angle_info}

CRITICAL - Recorded Pipeline Activities & CRM Notes ({len(activities)} logged):
{activities_summary}

Specific Drafting Instructions / Additional Guidance:
{custom_instructions if custom_instructions else "None provided - dynamically synthesize school context and CRM notes history."}

Demo Booking Link: {settings.demo_link}
Video Overview Link: {settings.video_link}
"""

    response = client.responses.parse(
        model=settings.openai_extraction_model,
        instructions=outreach_prompt_instructions,
        input=prompt_input,
        text_format=OutreachDraftResult,
    )

    if response.output_parsed:
        drafts: OutreachDraftResult = response.output_parsed

        # Apply to SENCO
        senco.email_subject = drafts.senco_email_subject
        senco.email_draft = drafts.senco_email_body
        senco.letter_draft = drafts.physical_letter_body
        senco.status = ContactStatus.outreach_drafted

        # Apply to Headteacher if present
        if head:
            head.email_subject = drafts.headteacher_email_subject
            head.email_draft = drafts.headteacher_email_body
            head.letter_draft = drafts.physical_letter_body
            head.status = ContactStatus.outreach_drafted

        if school.pipeline_stage in (SchoolPipelineStage.discovered, SchoolPipelineStage.qualified):
            school.pipeline_stage = SchoolPipelineStage.outreach_ready

        # Log an activity for draft generation
        notes_detail = f"Generated SENCO email, Headteacher email, and physical letter taking into account {len(activities)} recorded CRM notes and SEND intelligence."
        if custom_instructions:
            notes_detail += f" Focus angle: '{custom_instructions}'."
        db.add(
            SchoolActivity(
                school_id=school.id,
                activity_type="note",
                title="✨ Tailored outreach drafts generated",
                notes=notes_detail,
                author="See My Mind Agent",
            )
        )

        db.commit()

        return {
            "status": "success",
            "senco_subject": senco.email_subject,
            "senco_email": senco.email_draft,
            "head_subject": head.email_subject if head else None,
            "head_email": head.email_draft if head else None,
            "letter": senco.letter_draft,
            "activities_count": len(activities),
        }

    return {"status": "error", "message": "Failed to parse outreach drafts"}


# Alias for terminology
discovery_school = audit_school
