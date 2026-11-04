"""
See My Mind MCP Server
Provides standard MCP tools for interacting with See My Mind Education CRM,
viewing school intelligence, reading/writing activity timelines, and generating
contextual outreach drafts that incorporate CRM discussion history.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from mcp.server.mcpserver import MCPServer
from sqlalchemy import or_
from smm_app.database import SessionLocal
from smm_app.models import (
    School,
    SchoolContact,
    SchoolActivity,
    SchoolAuditRun,
    SchoolPipelineStage,
    AuditStatus,
)
from smm_app.school_research import draft_outreach_for_school

mcp = MCPServer(
    name="seemymind-crm",
    instructions=(
        "See My Mind CRM MCP Server. Provides tools to search target UK schools, "
        "inspect SEND intelligence, read and log CRM activities/notes, and generate "
        "tailored outreach drafts synthesizing discovery data with past engagement notes."
    ),
)


@mcp.tool()
def search_schools(query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Search target schools by name, postcode, or multi-academy trust.

    Args:
        query: Search string (e.g., 'primary', 'bexley', 'harris academy').
        limit: Maximum number of schools to return (default 20).
    """
    db = SessionLocal()
    try:
        q = f"%{query.lower()}%"
        schools = (
            db.query(School)
            .filter(
                or_(
                    School.name.ilike(q),
                    School.postcode.ilike(q),
                    School.mat_name.ilike(q),
                    School.local_authority.ilike(q),
                )
            )
            .limit(limit)
            .all()
        )
        return [
            {
                "id": s.id,
                "name": s.name,
                "phase": s.phase,
                "postcode": s.postcode,
                "mat_name": s.mat_name,
                "sen_percentage": s.sen_percentage,
                "ofsted_rating": s.ofsted_rating,
                "priority": s.priority,
                "pipeline_stage": s.pipeline_stage.value,
            }
            for s in schools
        ]
    finally:
        db.close()


@mcp.tool()
def get_school_context(school_id: str) -> dict[str, Any]:
    """Retrieve full SEND intelligence, Ofsted quotes, contacts, and metadata for a school.

    Args:
        school_id: The unique identifier of the school.
    """
    db = SessionLocal()
    try:
        school = db.get(School, school_id)
        if not school:
            return {"error": f"School with ID '{school_id}' not found"}

        contacts = (
            db.query(SchoolContact)
            .filter(SchoolContact.school_id == school.id)
            .all()
        )

        latest_run = (
            db.query(SchoolAuditRun)
            .filter(
                SchoolAuditRun.school_id == school.id,
                SchoolAuditRun.status == AuditStatus.completed,
            )
            .order_by(SchoolAuditRun.started_at.desc())
            .first()
        )

        return {
            "id": school.id,
            "name": school.name,
            "address": school.address,
            "postcode": school.postcode,
            "phase": school.phase,
            "mat_name": school.mat_name,
            "local_authority": school.local_authority,
            "sen_percentage": school.sen_percentage,
            "ofsted_rating": school.ofsted_rating,
            "ofsted_send_excerpt": school.ofsted_send_excerpt,
            "overall_score": school.overall_score,
            "priority": school.priority,
            "pipeline_stage": school.pipeline_stage.value,
            "detected_tools": latest_run.detected_tools if latest_run else None,
            "strengths_found": latest_run.strengths_found if latest_run else None,
            "challenges_found": latest_run.challenges_found if latest_run else None,
            "recommended_angle": latest_run.recommended_angle if latest_run else None,
            "contacts": [
                {
                    "id": c.id,
                    "name": c.name,
                    "role": c.role,
                    "email": c.email,
                    "email_is_verified": c.email_is_verified,
                    "phone_extension": c.phone_extension,
                    "has_draft": bool(c.email_draft),
                }
                for c in contacts
            ],
        }
    finally:
        db.close()


@mcp.tool()
def get_school_activities(school_id: str) -> list[dict[str, Any]]:
    """Retrieve all logged CRM activities, phone call notes, meetings, and follow-ups for a school.

    Args:
        school_id: The unique identifier of the school.
    """
    db = SessionLocal()
    try:
        activities = (
            db.query(SchoolActivity)
            .filter(SchoolActivity.school_id == school_id)
            .order_by(SchoolActivity.activity_date.desc(), SchoolActivity.created_at.desc())
            .all()
        )
        return [
            {
                "id": a.id,
                "activity_type": a.activity_type,
                "title": a.title,
                "notes": a.notes,
                "contact_name": a.contact_name,
                "author": a.author,
                "activity_date": a.activity_date.isoformat() if a.activity_date else None,
                "follow_up_task": a.follow_up_task,
                "next_follow_up_date": a.next_follow_up_date.isoformat() if a.next_follow_up_date else None,
                "follow_up_completed": a.follow_up_completed,
            }
            for a in activities
        ]
    finally:
        db.close()


@mcp.tool()
def log_school_activity(
    school_id: str,
    activity_type: str,
    title: str,
    notes: str | None = None,
    contact_name: str | None = None,
    author: str = "AI Assistant",
    follow_up_task: str | None = None,
    next_follow_up_date: str | None = None,
) -> dict[str, Any]:
    """Log a new call, meeting, email, demo, or discussion note to the school CRM timeline.

    Args:
        school_id: The target school ID.
        activity_type: One of 'call', 'meeting', 'email', 'note', 'demo', 'stage_change'.
        title: Summary title of the activity.
        notes: Detailed discussion notes, objections, or topics discussed.
        contact_name: Name of the school contact person engaged with.
        author: Who logged the activity (default 'AI Assistant').
        follow_up_task: Description of next action item or task.
        next_follow_up_date: ISO date string (YYYY-MM-DD) for next follow-up due date.
    """
    db = SessionLocal()
    try:
        school = db.get(School, school_id)
        if not school:
            return {"error": f"School with ID '{school_id}' not found"}

        parsed_follow_up = None
        if next_follow_up_date:
            try:
                parsed_follow_up = datetime.fromisoformat(next_follow_up_date.replace("Z", "+00:00"))
            except Exception:
                try:
                    parsed_follow_up = datetime.strptime(next_follow_up_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except Exception:
                    pass

        activity = SchoolActivity(
            school_id=school.id,
            activity_type=activity_type,
            title=title,
            notes=notes,
            contact_name=contact_name,
            author=author,
            follow_up_task=follow_up_task,
            next_follow_up_date=parsed_follow_up,
            follow_up_completed=False if follow_up_task else True,
        )
        db.add(activity)
        db.commit()
        db.refresh(activity)

        return {
            "status": "success",
            "message": "Activity logged successfully",
            "activity_id": activity.id,
            "school_name": school.name,
        }
    finally:
        db.close()


@mcp.tool()
def draft_school_outreach(
    school_id: str,
    custom_instructions: str | None = None,
) -> dict[str, Any]:
    """Generate on-demand tailored outreach (SENCO email, Headteacher email, physical letter)
    dynamically synthesizing school SEND intelligence AND all recorded CRM activity notes.

    Args:
        school_id: The target school ID.
        custom_instructions: Optional specific focus or angle (e.g. 'Emphasize TA transition notes', 'Follow up on our phone call regarding EHCP reviews').
    """
    db = SessionLocal()
    try:
        school = db.get(School, school_id)
        if not school:
            return {"error": f"School with ID '{school_id}' not found"}

        result = draft_outreach_for_school(
            db=db,
            school_id=school.id,
            custom_instructions=custom_instructions,
        )
        return {
            "status": "success",
            "school_id": school.id,
            "school_name": school.name,
            "senco_subject": result.get("senco_subject"),
            "senco_email": result.get("senco_email"),
            "head_subject": result.get("head_subject"),
            "head_email": result.get("head_email"),
            "letter": result.get("letter"),
            "activities_considered": result.get("activities_count", 0),
        }
    finally:
        db.close()


@mcp.tool()
def list_schools(
    pipeline_stage: str | None = None,
    priority: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List target schools filtered by pipeline stage or priority tier.

    Args:
        pipeline_stage: Filter by stage (e.g., 'discovered', 'qualified', 'outreach_ready', 'contacted', 'demo_booked', 'partner_won').
        priority: Filter by priority (e.g., 'Immediate Focus', 'Target School', 'Monitor').
        limit: Maximum results (default 50).
    """
    db = SessionLocal()
    try:
        query = db.query(School)
        if pipeline_stage:
            query = query.filter(School.pipeline_stage == SchoolPipelineStage(pipeline_stage))
        if priority:
            query = query.filter(School.priority == priority)

        schools = query.order_by(School.overall_score.desc()).limit(limit).all()
        return [
            {
                "id": s.id,
                "name": s.name,
                "phase": s.phase,
                "postcode": s.postcode,
                "mat_name": s.mat_name,
                "overall_score": s.overall_score,
                "priority": s.priority,
                "pipeline_stage": s.pipeline_stage.value,
            }
            for s in schools
        ]
    finally:
        db.close()


@mcp.tool()
def update_school_ofsted(
    school_id: str,
    ofsted_rating: str | None = None,
    ofsted_inspection_date: str | None = None,
    ofsted_send_excerpt: str | None = None,
) -> dict[str, Any]:
    """Manually record or update Ofsted rating, inspection date, and SEND inspection excerpt for a school.

    Args:
        school_id: Target school ID.
        ofsted_rating: Rating (e.g. 'Outstanding', 'Good', 'Requires Improvement', 'Inadequate').
        ofsted_inspection_date: Date or period of inspection (e.g. 'March 2024').
        ofsted_send_excerpt: Verbatim excerpt or notes regarding SEND provision from inspection report.
    """
    db = SessionLocal()
    try:
        school = db.get(School, school_id)
        if not school:
            return {"error": f"School with ID '{school_id}' not found"}

        if ofsted_rating is not None:
            school.ofsted_rating = ofsted_rating
        if ofsted_inspection_date is not None:
            school.ofsted_inspection_date = ofsted_inspection_date
        if ofsted_send_excerpt is not None:
            school.ofsted_send_excerpt = ofsted_send_excerpt

        if school.pipeline_stage == SchoolPipelineStage.discovered:
            school.pipeline_stage = SchoolPipelineStage.qualified

        db.add(
            SchoolActivity(
                school_id=school.id,
                activity_type="note",
                title="Updated Ofsted Inspection Intelligence",
                notes=f"Rating: {school.ofsted_rating or 'Unspecified'} | Date: {school.ofsted_inspection_date or 'Unspecified'}\nFindings: {school.ofsted_send_excerpt or 'None'}",
                author="MCP Assistant",
            )
        )
        db.commit()
        return {"status": "success", "message": "Ofsted intelligence updated successfully", "school_name": school.name}
    finally:
        db.close()


@mcp.tool()
def update_school_send_provision(
    school_id: str,
    send_report_url: str | None = None,
    detected_tools: str | None = None,
    strengths_found: str | None = None,
    challenges_found: str | None = None,
    recommended_angle: str | None = None,
) -> dict[str, Any]:
    """Manually record or update statutory SEND information report link, tools used, strengths, challenges, and angle.

    Args:
        school_id: Target school ID.
        send_report_url: URL to statutory SEND information report.
        detected_tools: Platforms and tools used (e.g. 'Provision Map, CPOMS, Arbor').
        strengths_found: Documented strengths in SEND provision.
        challenges_found: Identified challenges, EHCP caseload, or inclusion pressures.
        recommended_angle: Strategic outreach hook or internal positioning note.
    """
    db = SessionLocal()
    try:
        school = db.get(School, school_id)
        if not school:
            return {"error": f"School with ID '{school_id}' not found"}

        run = (
            db.query(SchoolAuditRun)
            .filter(SchoolAuditRun.school_id == school.id)
            .order_by(SchoolAuditRun.started_at.desc())
            .first()
        )
        if not run:
            run = SchoolAuditRun(
                school_id=school.id,
                status=AuditStatus.completed,
                current_message="Manual provision entry",
                completed_at=datetime.now(timezone.utc),
            )
            db.add(run)

        if send_report_url is not None:
            run.send_report_url = send_report_url
        if detected_tools is not None:
            run.detected_tools = detected_tools
        if strengths_found is not None:
            run.strengths_found = strengths_found
        if challenges_found is not None:
            run.challenges_found = challenges_found
        if recommended_angle is not None:
            run.recommended_angle = recommended_angle

        run.status = AuditStatus.completed
        run.completed_at = datetime.now(timezone.utc)

        if school.pipeline_stage == SchoolPipelineStage.discovered:
            school.pipeline_stage = SchoolPipelineStage.qualified

        db.add(
            SchoolActivity(
                school_id=school.id,
                activity_type="note",
                title="Updated Statutory SEND Provision Notes",
                notes=f"Tools: {run.detected_tools or 'None'}\nStrengths: {run.strengths_found or 'None'}\nChallenges: {run.challenges_found or 'None'}\nAngle: {run.recommended_angle or 'None'}",
                author="MCP Assistant",
            )
        )
        db.commit()
        return {"status": "success", "message": "Statutory SEND provision updated successfully", "school_name": school.name}
    finally:
        db.close()


if __name__ == "__main__":
    # Runs standard stdio MCP transport for AI assistants
    mcp.run()
