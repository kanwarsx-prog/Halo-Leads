"""
See My Mind In-App Agentic Assistant Router
Provides an OpenAI tool-calling agent capable of checking school status,
drafting tailored emails, taking notes, logging meeting schedules,
updating pipeline stages, and managing contacts & follow-up tasks.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from smm_app.config import get_settings
from smm_app.database import get_db
from smm_app.models import (
    AuditStatus,
    ContactStatus,
    School,
    SchoolActivity,
    SchoolAuditRun,
    SchoolContact,
    SchoolPipelineStage,
    AgentInteractionLog,
)
from smm_app.openai_client import client

router = APIRouter(prefix="/agent", tags=["agent"])
settings = get_settings()


class AgentMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(BaseModel):
    message: str
    history: list[AgentMessage] = []
    current_school_id: str | None = None



def _log_llm_interaction(
    db: Session,
    user_prompt: str,
    llm_output: str,
    system_prompt: str | None = None,
    tool_calls_trace: list[dict[str, Any]] | None = None,
    school_id: str | None = None,
    status: str = "completed",
) -> None:
    """Persist every AI Agent input prompt, tool trace, and LLM output to smm_agent_logs."""
    try:
        AgentInteractionLog.__table__.create(bind=db.get_bind(), checkfirst=True)
        entry = AgentInteractionLog(
            school_id=school_id,
            model=settings.openai_model,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            tool_calls_json=json.dumps(tool_calls_trace) if tool_calls_trace else None,
            llm_output=llm_output,
            status=status,
        )
        db.add(entry)
        db.commit()
    except Exception as log_exc:
        db.rollback()
        print(f"Warning: failed to write AgentInteractionLog: {log_exc}")


def _resolve_school(db: Session, query_or_id: str | None, fallback_id: str | None = None) -> School | None:
    """Find a school by exact ID, case-insensitive name match, or fuzzy substring."""
    target = (query_or_id or "").strip()
    if not target and fallback_id:
        return db.get(School, fallback_id)
    if not target:
        return None

    # 1. Exact ID match
    by_id = db.get(School, target)
    if by_id:
        return by_id

    # 2. Exact case-insensitive name match
    exact_name = db.query(School).filter(School.name.ilike(target)).first()
    if exact_name:
        return exact_name

    # 3. Substring match on name
    sub = db.query(School).filter(School.name.ilike(f"%{target}%")).order_by(School.overall_score.desc()).first()
    if sub:
        return sub

    # 4. Token match (e.g. "Poverest Primary" -> search "Poverest")
    cleaned = (
        target.lower()
        .replace("primary school", "")
        .replace("secondary school", "")
        .replace("school", "")
        .replace("academy", "")
        .strip()
    )
    if cleaned and len(cleaned) >= 3:
        token_match = (
            db.query(School)
            .filter(
                or_(
                    School.name.ilike(f"%{cleaned}%"),
                    School.mat_name.ilike(f"%{cleaned}%"),
                    School.postcode.ilike(f"%{cleaned}%"),
                )
            )
            .order_by(School.overall_score.desc())
            .first()
        )
        if token_match:
            return token_match

    if fallback_id:
        return db.get(School, fallback_id)
    return None


# ==============================================================================
# Agent Tool Definitions (OpenAI Function Calling Schema)
# ==============================================================================

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_school_status",
            "description": (
                "Look up the full status, SEND metrics, Ofsted findings, pipeline stage, "
                "key contacts (Headteacher, SENCO), recent notes, and scheduled meetings for a school."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "school_query": {
                        "type": "string",
                        "description": "School name, postcode, trust name, or ID (e.g. 'Poverest Primary', 'Gallions'). Leave empty if asking about the currently viewed school.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_schools_pipeline",
            "description": "Search or filter schools across the pipeline by keyword, pipeline stage, or priority tier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional search keyword (name, borough, MAT, postcode).",
                    },
                    "pipeline_stage": {
                        "type": "string",
                        "description": "Optional stage filter: discovered, qualified, outreach_ready, contacted, demo_booked, partner_won, not_a_fit.",
                    },
                    "priority": {
                        "type": "string",
                        "description": "Optional priority filter: 'Immediate Focus', 'Target School', 'Monitor'.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of schools to return (default 10).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_or_update_school",
            "description": (
                "Add a new target school to the if it does not exist yet, or update an existing school's "
                "pipeline stage, phase, trust, local authority, SEN %, or general notes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Full name of the school (e.g. 'Poverest Primary School').",
                    },
                    "phase": {
                        "type": "string",
                        "description": "School phase: 'Primary', 'Secondary', 'Special', or 'All-through'.",
                    },
                    "local_authority": {
                        "type": "string",
                        "description": "Local authority or borough (e.g. 'Bromley', 'Newham', 'Bexley').",
                    },
                    "mat_name": {
                        "type": "string",
                        "description": "Multi-Academy Trust name if applicable.",
                    },
                    "postcode": {
                        "type": "string",
                        "description": "Postcode if known.",
                    },
                    "pipeline_stage": {
                        "type": "string",
                        "description": "Stage: discovered, qualified, outreach_ready, contacted, demo_booked, partner_won, not_a_fit.",
                    },
                    "sen_percentage": {
                        "type": "number",
                        "description": "SEN support / EHCP roll percentage if known.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "General summary notes for the school.",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_school_stage",
            "description": "Move a school to a new pipeline stage (e.g. contacted, demo_booked, partner_won, qualified, outreach_ready, not_a_fit).",
            "parameters": {
                "type": "object",
                "properties": {
                    "school_query": {
                        "type": "string",
                        "description": "School name or ID.",
                    },
                    "new_stage": {
                        "type": "string",
                        "enum": [
                            "discovered",
                            "auditing",
                            "qualified",
                            "outreach_ready",
                            "contacted",
                            "demo_booked",
                            "partner_won",
                            "not_a_fit",
                        ],
                        "description": "Target pipeline stage.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional note explaining the stage transition.",
                    },
                },
                "required": ["new_stage"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_note_or_meeting",
            "description": (
                "Take a note, log a phone call/email, or schedule a meeting/demo/follow-up task for a school. "
                "Automatically creates the school if it is not yet in the database."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "school_query": {
                        "type": "string",
                        "description": "Name or ID of the school (e.g. 'Poverest Primary').",
                    },
                    "activity_type": {
                        "type": "string",
                        "enum": ["note", "call", "meeting", "demo", "email"],
                        "description": "Type of activity: 'note', 'call', 'meeting', 'demo', or 'email'.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Concise title (e.g. 'Meeting scheduled with Headteacher Paul', 'Call with SENCO').",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Detailed notes, agenda, or context.",
                    },
                    "contact_name": {
                        "type": "string",
                        "description": "Name of the person at the school (e.g. 'Paul', 'Mrs Clarke').",
                    },
                    "next_follow_up_date": {
                        "type": "string",
                        "description": "Scheduled date for the meeting or follow-up in YYYY-MM-DD format (e.g. '2026-11-18').",
                    },
                    "follow_up_task": {
                        "type": "string",
                        "description": "Action item or meeting reminder to show in the Dashboard Action Queue.",
                    },
                },
                "required": ["activity_type", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_or_update_contact",
            "description": "Save a named contact (Headteacher, SENCO, Inclusion Lead, CEO) on a school.",
            "parameters": {
                "type": "object",
                "properties": {
                    "school_query": {
                        "type": "string",
                        "description": "School name or ID.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Full name of the contact (e.g. 'Paul').",
                    },
                    "role": {
                        "type": "string",
                        "description": "Role (e.g. 'Headteacher', 'SENCO', 'Assistant Head').",
                    },
                    "email": {
                        "type": "string",
                        "description": "Email address if known.",
                    },
                    "phone_extension": {
                        "type": "string",
                        "description": "Phone number or extension if known.",
                    },
                },
                "required": ["name", "role"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_email_for_school",
            "description": (
                "Draft a personalised outreach or follow-up email for a school contact (Headteacher, SENCO, or custom recipient), "
                "incorporating school SEND intelligence, past notes, and the user's specific instructions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "school_query": {
                        "type": "string",
                        "description": "School name or ID.",
                    },
                    "recipient_name": {
                        "type": "string",
                        "description": "Recipient name if known (e.g. 'Paul', 'Sarah').",
                    },
                    "recipient_role": {
                        "type": "string",
                        "description": "Recipient role (e.g. 'Headteacher', 'SENCO').",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "Specific angle, tone, or context for the email (e.g. 'warm intro via Priyanka for Nov 18 meeting', 'follow up on sandbox demo').",
                    },
                    "save_to_contact": {
                        "type": "boolean",
                        "description": "Whether to save the generated subject & body onto the school contact record (default true).",
                    },
                },
                "required": ["instructions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_schedule",
            "description": "Retrieve all upcoming scheduled meetings, demos, and open follow-up tasks across all schools.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_completed": {
                        "type": "boolean",
                        "description": "Whether to include completed tasks (default false).",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark an open follow-up task or meeting reminder for a school as completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "school_query": {
                        "type": "string",
                        "description": "School name or activity ID whose open task should be marked done.",
                    }
                },
                "required": ["school_query"],
            },
        },
    },
]


# ==============================================================================
# Tool Execution Implementations
# ==============================================================================

def _execute_tool(
    db: Session,
    tool_name: str,
    args: dict[str, Any],
    current_school_id: str | None,
    actions_taken: list[dict[str, Any]],
) -> dict[str, Any]:
    """Execute a single agent tool call against the database and record UI action badges."""

    if tool_name == "get_school_status":
        q = args.get("school_query")
        school = _resolve_school(db, q, current_school_id)
        if not school:
            return {
                "found": False,
                "message": f"No school matching '{q}' was found in the database. You can ask me to add it with create_or_update_school.",
            }

        latest_run = (
            db.query(SchoolAuditRun)
            .filter(SchoolAuditRun.school_id == school.id, SchoolAuditRun.status == AuditStatus.completed)
            .order_by(SchoolAuditRun.started_at.desc())
            .first()
        )
        activities = (
            db.query(SchoolActivity)
            .filter(SchoolActivity.school_id == school.id)
            .order_by(SchoolActivity.activity_date.desc())
            .limit(8)
            .all()
        )
        contacts = (
            db.query(SchoolContact)
            .filter(SchoolContact.school_id == school.id)
            .all()
        )

        actions_taken.append({
            "label": f"Checked status: {school.name}",
            "school_id": school.id,
            "school_name": school.name,
            "mutated": False,
        })

        return {
            "found": True,
            "id": school.id,
            "name": school.name,
            "url": f"/seemymind/ui/schools/{school.id}",
            "phase": school.phase,
            "mat_name": school.mat_name,
            "local_authority": school.local_authority,
            "postcode": school.postcode,
            "pipeline_stage": school.pipeline_stage.value,
            "priority": school.priority,
            "overall_score": school.overall_score,
            "sen_percentage": school.sen_percentage,
            "ofsted_rating": school.ofsted_rating,
            "ofsted_send_excerpt": school.ofsted_send_excerpt,
            "recommended_angle": latest_run.recommended_angle if latest_run else None,
            "challenges_found": latest_run.challenges_found if latest_run else None,
            "detected_tools": latest_run.detected_tools if latest_run else None,
            "contacts": [
                {
                    "name": c.name,
                    "role": c.role,
                    "email": c.email,
                    "phone": c.phone_extension,
                }
                for c in contacts
            ],
            "recent_activities": [
                {
                    "type": a.activity_type,
                    "title": a.title,
                    "notes": a.notes,
                    "contact": a.contact_name,
                    "date": a.activity_date.strftime("%Y-%m-%d") if a.activity_date else None,
                    "follow_up_task": a.follow_up_task,
                    "next_follow_up_date": a.next_follow_up_date.strftime("%Y-%m-%d") if a.next_follow_up_date else None,
                    "follow_up_completed": a.follow_up_completed,
                }
                for a in activities
            ],
        }

    elif tool_name == "search_schools_pipeline":
        q = (args.get("query") or "").strip()
        stage = args.get("pipeline_stage")
        priority = args.get("priority")
        limit = min(int(args.get("limit") or 10), 30)

        query = db.query(School)
        if q:
            like_q = f"%{q}%"
            query = query.filter(
                or_(
                    School.name.ilike(like_q),
                    School.mat_name.ilike(like_q),
                    School.local_authority.ilike(like_q),
                    School.postcode.ilike(like_q),
                )
            )
        if stage:
            try:
                query = query.filter(School.pipeline_stage == SchoolPipelineStage(stage))
            except Exception:
                pass
        if priority:
            query = query.filter(School.priority.ilike(f"%{priority}%"))

        results = query.order_by(School.overall_score.desc()).limit(limit).all()
        return {
            "count": len(results),
            "schools": [
                {
                    "id": s.id,
                    "name": s.name,
                    "phase": s.phase,
                    "mat_name": s.mat_name,
                    "local_authority": s.local_authority,
                    "sen_percentage": s.sen_percentage,
                    "overall_score": s.overall_score,
                    "priority": s.priority,
                    "pipeline_stage": s.pipeline_stage.value,
                    "url": f"/seemymind/ui/schools/{s.id}",
                }
                for s in results
            ],
        }

    elif tool_name == "create_or_update_school":
        name = (args.get("name") or "").strip()
        if not name:
            return {"error": "School name is required."}

        school = _resolve_school(db, name, None)
        created = False
        if not school:
            school = School(
                name=name,
                phase=args.get("phase") or "Primary",
                local_authority=args.get("local_authority"),
                mat_name=args.get("mat_name"),
                postcode=args.get("postcode"),
                sen_percentage=args.get("sen_percentage") or 0.0,
                notes=args.get("notes"),
                pipeline_stage=SchoolPipelineStage.discovered,
                priority="Target School",
            )
            db.add(school)
            created = True
        else:
            if args.get("phase"):
                school.phase = args["phase"]
            if args.get("local_authority"):
                school.local_authority = args["local_authority"]
            if args.get("mat_name"):
                school.mat_name = args["mat_name"]
            if args.get("postcode"):
                school.postcode = args["postcode"]
            if args.get("sen_percentage") is not None:
                school.sen_percentage = float(args["sen_percentage"])
            if args.get("notes"):
                school.notes = args["notes"]

        if args.get("pipeline_stage"):
            try:
                school.pipeline_stage = SchoolPipelineStage(args["pipeline_stage"])
            except Exception:
                pass

        db.commit()
        db.refresh(school)

        actions_taken.append({
            "label": f"{'Added' if created else 'Updated'} school: {school.name}",
            "school_id": school.id,
            "school_name": school.name,
            "mutated": True,
        })
        return {
            "status": "created" if created else "updated",
            "school_id": school.id,
            "name": school.name,
            "pipeline_stage": school.pipeline_stage.value,
            "url": f"/seemymind/ui/schools/{school.id}",
        }

    elif tool_name == "update_school_stage":
        school = _resolve_school(db, args.get("school_query"), current_school_id)
        if not school:
            return {"error": f"Could not find school '{args.get('school_query')}'."}

        new_stage_str = args.get("new_stage", "contacted")
        try:
            new_stage = SchoolPipelineStage(new_stage_str)
        except Exception:
            return {"error": f"Invalid stage '{new_stage_str}'."}

        old_stage = school.pipeline_stage.value
        school.pipeline_stage = new_stage

        reason = args.get("reason") or f"Stage updated via Agent from {old_stage} to {new_stage.value}"
        db.add(
            SchoolActivity(
                school_id=school.id,
                activity_type="stage_change",
                title=f"Moved to {new_stage.value.replace('_', ' ').title()}",
                notes=reason,
                author="SMM Agent",
                follow_up_completed=True,
            )
        )
        db.commit()

        actions_taken.append({
            "label": f"Stage → {new_stage.value.replace('_', ' ').title()} ({school.name})",
            "school_id": school.id,
            "school_name": school.name,
            "mutated": True,
        })
        return {
            "status": "success",
            "school_id": school.id,
            "school_name": school.name,
            "old_stage": old_stage,
            "new_stage": new_stage.value,
            "url": f"/seemymind/ui/schools/{school.id}",
        }

    elif tool_name == "log_note_or_meeting":
        q = args.get("school_query")
        school = _resolve_school(db, q, current_school_id)
        # If the user logs a meeting/note for a school not yet in the DB, create it automatically!
        if not school and q:
            school = School(
                name=q.strip(),
                phase="Primary" if "primary" in q.lower() else ("Secondary" if "secondary" in q.lower() else "Primary"),
                pipeline_stage=SchoolPipelineStage.contacted,
                priority="Target School",
            )
            db.add(school)
            db.commit()
            db.refresh(school)
            actions_taken.append({
                "label": f"Added school: {school.name}",
                "school_id": school.id,
                "school_name": school.name,
                "mutated": True,
            })

        if not school:
            return {"error": "Please specify which school this note or meeting is for."}

        act_type = args.get("activity_type") or "note"
        title = args.get("title") or "Note logged via Agent"
        notes = args.get("notes")
        contact_name = args.get("contact_name")
        follow_up_task = args.get("follow_up_task")
        next_date_str = args.get("next_follow_up_date")

        parsed_date = None
        if next_date_str:
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    parsed_date = datetime.strptime(next_date_str[:10], fmt).replace(tzinfo=timezone.utc)
                    break
                except Exception:
                    continue

        # If it's a scheduled meeting or demo with a future date and no explicit follow_up_task, set one so it shows in Action Queue
        if not follow_up_task and parsed_date and act_type in ("meeting", "demo", "call"):
            follow_up_task = title

        activity = SchoolActivity(
            school_id=school.id,
            activity_type=act_type,
            title=title,
            notes=notes,
            contact_name=contact_name,
            author="SMM Agent",
            next_follow_up_date=parsed_date,
            follow_up_task=follow_up_task,
            follow_up_completed=False if (follow_up_task or parsed_date) else True,
        )
        db.add(activity)

        # Auto-advance stage if booking a demo/meeting on a discovered/qualified school
        if act_type in ("demo", "meeting") and school.pipeline_stage in (
            SchoolPipelineStage.discovered,
            SchoolPipelineStage.qualified,
            SchoolPipelineStage.outreach_ready,
            SchoolPipelineStage.contacted,
        ):
            school.pipeline_stage = SchoolPipelineStage.demo_booked

        db.commit()
        db.refresh(activity)

        actions_taken.append({
            "label": f"Logged {act_type}: {title} ({school.name})",
            "school_id": school.id,
            "school_name": school.name,
            "mutated": True,
        })
        return {
            "status": "success",
            "activity_id": activity.id,
            "school_id": school.id,
            "school_name": school.name,
            "activity_type": act_type,
            "title": title,
            "scheduled_date": parsed_date.strftime("%Y-%m-%d") if parsed_date else None,
            "follow_up_task": follow_up_task,
            "pipeline_stage": school.pipeline_stage.value,
            "url": f"/seemymind/ui/schools/{school.id}",
        }

    elif tool_name == "add_or_update_contact":
        q = args.get("school_query")
        school = _resolve_school(db, q, current_school_id)
        if not school and q:
            school = School(
                name=q.strip(),
                phase="Primary",
                pipeline_stage=SchoolPipelineStage.discovered,
                priority="Target School",
            )
            db.add(school)
            db.commit()
            db.refresh(school)

        if not school:
            return {"error": "Please specify the school for this contact."}

        c_name = (args.get("name") or "").strip()
        c_role = (args.get("role") or "Contact").strip()
        c_email = (args.get("email") or "").strip() or None
        c_phone = (args.get("phone_extension") or "").strip() or None

        existing = (
            db.query(SchoolContact)
            .filter(SchoolContact.school_id == school.id, SchoolContact.name.ilike(c_name))
            .first()
        )
        if existing:
            existing.role = c_role
            if c_email:
                existing.email = c_email
                existing.email_is_verified = True
            if c_phone:
                existing.phone_extension = c_phone
            contact = existing
        else:
            contact = SchoolContact(
                school_id=school.id,
                name=c_name,
                role=c_role,
                email=c_email,
                email_is_verified=bool(c_email),
                phone_extension=c_phone,
                source="Added via SMM Agent",
                status=ContactStatus.researched,
            )
            db.add(contact)

        db.commit()
        db.refresh(contact)

        actions_taken.append({
            "label": f"Saved contact: {contact.name} ({contact.role}) at {school.name}",
            "school_id": school.id,
            "school_name": school.name,
            "mutated": True,
        })
        return {
            "status": "success",
            "contact_id": contact.id,
            "name": contact.name,
            "role": contact.role,
            "email": contact.email,
            "school_name": school.name,
            "school_id": school.id,
        }

    elif tool_name == "draft_email_for_school":
        q = args.get("school_query")
        school = _resolve_school(db, q, current_school_id)
        instructions = args.get("instructions") or "Write a warm, concise outreach email introducing See My Mind."
        recipient_name = args.get("recipient_name") or ""
        recipient_role = args.get("recipient_role") or "Headteacher / SENCO"

        school_context_str = f"School: {q or 'Target UK School'}"
        if school:
            latest_run = (
                db.query(SchoolAuditRun)
                .filter(SchoolAuditRun.school_id == school.id, SchoolAuditRun.status == AuditStatus.completed)
                .order_by(SchoolAuditRun.started_at.desc())
                .first()
            )
            activities = (
                db.query(SchoolActivity)
                .filter(SchoolActivity.school_id == school.id)
                .order_by(SchoolActivity.activity_date.desc())
                .limit(5)
                .all()
            )
            contacts = db.query(SchoolContact).filter(SchoolContact.school_id == school.id).all()
            if not recipient_name and contacts:
                recipient_name = contacts[0].name
                recipient_role = contacts[0].role

            act_summary = "; ".join([f"{a.activity_type}: {a.title} ({a.notes or ''})" for a in activities])
            school_context_str = (
                f"School Name: {school.name}\n"
                f"Phase: {school.phase or 'Primary'} | Trust: {school.mat_name or 'Single/Maintained'} | LA: {school.local_authority or 'UK'}\n"
                f"SEN Percentage: {school.sen_percentage or 'Not recorded'}% | Ofsted: {school.ofsted_rating or 'Not recorded'}\n"
                f"Ofsted SEND Excerpt: {school.ofsted_send_excerpt or 'None'}\n"
                f"Provision Strengths: {latest_run.strengths_found if latest_run else 'None'}\n"
                f"Inclusion Challenges: {latest_run.challenges_found if latest_run else 'None'}\n"
                f"Recent Notes/Meetings: {act_summary or 'None'}"
            )

        prompt = (
            "You are drafting an email for Sushil Kanwar at See My Mind (an early-stage UK EdTech platform supporting "
            "SEN pupils, SENCOs, and teachers with early identification and pupil wellbeing/support profiles).\n\n"
            f"Recipient Name: {recipient_name or 'Headteacher / SENCO'}\n"
            f"Recipient Role: {recipient_role}\n"
            f"{school_context_str}\n\n"
            f"User's Specific Instructions: {instructions}\n\n"
            "Write a warm, natural, human UK-English email (not robotic or overly salesy). "
            "Return JSON with keys: 'subject' and 'body'."
        )

        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.5,
        )
        raw_draft_output = resp.choices[0].message.content or "{}"
        _log_llm_interaction(
            db=db,
            user_prompt=prompt,
            llm_output=raw_draft_output,
            system_prompt="Email Drafting Sub-Agent (JSON mode)",
            school_id=school.id if school else current_school_id,
            status="completed",
        )
        parsed = json.loads(raw_draft_output)
        subject = parsed.get("subject", f"Supporting SEN pupils at {school.name if school else 'your school'}")
        body = parsed.get("body", "")

        if school and args.get("save_to_contact", True):
            contacts = db.query(SchoolContact).filter(SchoolContact.school_id == school.id).all()
            if contacts:
                target_c = contacts[0]
                for c in contacts:
                    if recipient_name and recipient_name.lower() in c.name.lower():
                        target_c = c
                        break
                    if recipient_role and recipient_role.lower() in c.role.lower():
                        target_c = c
                        break
                target_c.email_subject = subject
                target_c.email_draft = body
                target_c.status = ContactStatus.outreach_drafted
                db.commit()

        actions_taken.append({
            "label": f"Drafted email for {recipient_name or (school.name if school else 'School')}",
            "school_id": school.id if school else None,
            "school_name": school.name if school else None,
            "mutated": bool(school),
            "email_draft": {"subject": subject, "body": body},
        })

        return {
            "status": "success",
            "school_name": school.name if school else q,
            "recipient": recipient_name,
            "subject": subject,
            "body": body,
        }

    elif tool_name == "get_upcoming_schedule":
        include_completed = bool(args.get("include_completed", False))
        q = db.query(SchoolActivity).filter(
            or_(
                SchoolActivity.next_follow_up_date.isnot(None),
                SchoolActivity.follow_up_task.isnot(None),
                SchoolActivity.activity_type.in_(["meeting", "demo"]),
            )
        )
        if not include_completed:
            q = q.filter(SchoolActivity.follow_up_completed == False)  # noqa: E712

        items = q.order_by(SchoolActivity.next_follow_up_date.asc().nullslast(), SchoolActivity.activity_date.desc()).limit(20).all()
        schedule = []
        for item in items:
            sc = db.get(School, item.school_id)
            schedule.append({
                "activity_id": item.id,
                "school_id": item.school_id,
                "school_name": sc.name if sc else "Unknown School",
                "type": item.activity_type,
                "title": item.title,
                "task": item.follow_up_task or item.title,
                "contact_name": item.contact_name,
                "due_date": item.next_follow_up_date.strftime("%Y-%m-%d") if item.next_follow_up_date else None,
                "notes": item.notes,
                "completed": item.follow_up_completed,
            })
        return {"count": len(schedule), "schedule": schedule}

    elif tool_name == "complete_task":
        q = (args.get("school_query") or "").strip()
        act = db.get(SchoolActivity, q)
        if not act:
            school = _resolve_school(db, q, current_school_id)
            if school:
                act = (
                    db.query(SchoolActivity)
                    .filter(SchoolActivity.school_id == school.id, SchoolActivity.follow_up_completed == False)  # noqa: E712
                    .order_by(SchoolActivity.next_follow_up_date.asc().nullslast())
                    .first()
                )
        if not act:
            return {"error": f"No open follow-up task found for '{q}'."}

        act.follow_up_completed = True
        db.commit()
        sc = db.get(School, act.school_id)
        actions_taken.append({
            "label": f"Completed task: {act.follow_up_task or act.title}",
            "school_id": act.school_id,
            "school_name": sc.name if sc else None,
            "mutated": True,
        })
        return {"status": "completed", "task": act.follow_up_task or act.title, "school_name": sc.name if sc else None}

    return {"error": f"Unknown tool '{tool_name}'"}


# ==============================================================================
# Main Agent Chat Endpoint
# ==============================================================================

@router.post("/chat")
def agent_chat(payload: AgentChatRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Execute a multi-step agent turn with tool calling against the See My Mind CRM."""
    now_str = datetime.now(timezone.utc).strftime("%A, %d %B %Y")

    current_school_info = ""
    if payload.current_school_id:
        curr = db.get(School, payload.current_school_id)
        if curr:
            current_school_info = (
                f"\nCURRENT PAGE CONTEXT: The user is currently viewing the school detail page for "
                f"'{curr.name}' (ID: {curr.id}, Stage: {curr.pipeline_stage.value}, SEN: {curr.sen_percentage}%). "
                f"If the user says 'this school' or omits the school name, use '{curr.name}' (ID: {curr.id})."
            )

    system_prompt = (
        f"You are the SMM Agent, an executive operational assistant for Sushil Kanwar and his partners "
        f"at See My Mind (UK EdTech platform supporting SEN pupils, SENCOs, and school leaders).\n"
        f"Today's date is {now_str}.{current_school_info}\n\n"
        "You have direct tool access to the live See My Mind database:\n"
        "- Check school status, SEND metrics, Ofsted quotes, contacts, and activity history (`get_school_status`, `search_schools_pipeline`)\n"
        "- Add new schools or update pipeline stages (`create_or_update_school`, `update_school_stage`)\n"
        "- Take notes, log calls/emails, and schedule meetings/demos with follow-up dates (`log_note_or_meeting`)\n"
        "- Save named contacts like Headteachers or SENCOs (`add_or_update_contact`)\n"
        "- Draft tailored, warm UK-English emails (`draft_email_for_school`)\n"
        "- Check upcoming scheduled meetings, demos, and follow-up tasks (`get_upcoming_schedule`, `complete_task`)\n\n"
        "GUIDELINES:\n"
        "1. Always execute the appropriate tool(s) immediately when the user asks to log a note, schedule a meeting, check a school, change a stage, or draft an email. You can chain multiple tool calls in a single turn (for example: add contact + schedule meeting + update stage).\n"
        "2. Keep your responses concise, clear, and action-oriented in British English.\n"
        "3. When you draft an email, display the Subject and Body clearly in your response so the user can review or copy it right away."
    )

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for h in payload.history[-10:]:
        if h.role in ("user", "assistant") and h.content:
            messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": payload.message})

    actions_taken: list[dict[str, Any]] = []
    tool_calls_trace: list[dict[str, Any]] = []

    try:
        # Up to 4 sequential tool-calling rounds
        for _ in range(4):
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                tools=AGENT_TOOLS,
                tool_choice="auto",
                temperature=0.3,
            )
            msg = response.choices[0].message

            if not msg.tool_calls:
                final_text = msg.content or "Done."
                resolved_school_id = next((a.get("school_id") for a in actions_taken if a.get("school_id")), payload.current_school_id)
                _log_llm_interaction(
                    db=db,
                    user_prompt=payload.message,
                    llm_output=final_text,
                    system_prompt=system_prompt,
                    tool_calls_trace=tool_calls_trace,
                    school_id=resolved_school_id,
                    status="completed",
                )
                return {
                    "reply": final_text,
                    "actions_taken": actions_taken,
                    "mutated": any(a.get("mutated") for a in actions_taken),
                }

            messages.append(msg.model_dump(exclude_none=True))

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    fn_args = {}

                tool_result = _execute_tool(
                    db=db,
                    tool_name=fn_name,
                    args=fn_args,
                    current_school_id=payload.current_school_id,
                    actions_taken=actions_taken,
                )
                tool_calls_trace.append({
                    "tool": fn_name,
                    "arguments": fn_args,
                    "output": tool_result,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn_name,
                    "content": json.dumps(tool_result),
                })

        # Final synthesis after tool calls
        final_resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0.3,
        )
        final_text = final_resp.choices[0].message.content or "Completed your request."
        resolved_school_id = next((a.get("school_id") for a in actions_taken if a.get("school_id")), payload.current_school_id)
        _log_llm_interaction(
            db=db,
            user_prompt=payload.message,
            llm_output=final_text,
            system_prompt=system_prompt,
            tool_calls_trace=tool_calls_trace,
            school_id=resolved_school_id,
            status="completed",
        )
        return {
            "reply": final_text,
            "actions_taken": actions_taken,
            "mutated": any(a.get("mutated") for a in actions_taken),
        }
    except Exception as exc:
        err_msg = f"⚠️ Agent encountered an error while processing your request: {exc}"
        _log_llm_interaction(
            db=db,
            user_prompt=payload.message,
            llm_output=err_msg,
            system_prompt=system_prompt,
            tool_calls_trace=tool_calls_trace,
            school_id=payload.current_school_id,
            status="error",
        )
        return {
            "reply": err_msg,
            "actions_taken": actions_taken,
            "mutated": False,
        }


@router.get("/logs")
def get_agent_logs(limit: int = 50, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Retrieve logged AI Agent interactions (input prompt, system prompt, tool calls, and LLM output)."""
    AgentInteractionLog.__table__.create(bind=db.get_bind(), checkfirst=True)
    logs = (
        db.query(AgentInteractionLog)
        .order_by(AgentInteractionLog.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "id": l.id,
            "school_id": l.school_id,
            "model": l.model,
            "user_prompt": l.user_prompt,
            "system_prompt": l.system_prompt,
            "tool_calls": json.loads(l.tool_calls_json) if l.tool_calls_json else [],
            "llm_output": l.llm_output,
            "status": l.status,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]
