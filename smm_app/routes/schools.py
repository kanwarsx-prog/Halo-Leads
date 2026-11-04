import csv
import io
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.orm import Session

from smm_app.database import get_db
from smm_app.models import School, SchoolPipelineStage, SchoolContact, ContactStatus, SchoolActivity, SchoolAuditRun, AuditStatus
from smm_app.schemas import SchoolCreate, SchoolRead, SchoolStageUpdate, SchoolContactCreate, SchoolActivityCreate, SchoolActivityRead, OfstedUpdate, SendProvisionUpdate

router = APIRouter(prefix="/schools", tags=["schools"])


@router.get("", response_model=list[SchoolRead])
def list_schools(
    stage: SchoolPipelineStage | None = None,
    mat_name: str | None = None,
    phase: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(School).order_by(School.created_at.desc())
    if stage:
        query = query.filter(School.pipeline_stage == stage)
    if mat_name:
        query = query.filter(School.mat_name.ilike(f"%{mat_name}%"))
    if phase:
        query = query.filter(School.phase.ilike(f"%{phase}%"))
    return list(db.scalars(query).all())


@router.post("", response_model=SchoolRead)
def create_school(payload: SchoolCreate, db: Session = Depends(get_db)):
    school = School(
        name=payload.name,
        urn=payload.urn,
        phase=payload.phase,
        school_type=payload.school_type,
        mat_name=payload.mat_name,
        local_authority=payload.local_authority,
        website=str(payload.website) if payload.website else None,
        postcode=payload.postcode,
        address=payload.address,
        phone=payload.phone,
        general_email=payload.general_email,
        sen_percentage=payload.sen_percentage,
        ehcp_count=payload.ehcp_count,
        ofsted_rating=payload.ofsted_rating,
        notes=payload.notes,
    )
    db.add(school)
    db.commit()
    db.refresh(school)
    return school


@router.get("/{school_id}", response_model=SchoolRead)
def get_school(school_id: str, db: Session = Depends(get_db)):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    return school


@router.patch("/{school_id}/stage", response_model=SchoolRead)
def update_stage(school_id: str, payload: SchoolStageUpdate, db: Session = Depends(get_db)):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    
    old_stage = school.pipeline_stage
    school.pipeline_stage = payload.pipeline_stage
    
    if old_stage != payload.pipeline_stage:
        old_name = old_stage.value.replace("_", " ").title()
        new_name = payload.pipeline_stage.value.replace("_", " ").title()
        stage_activity = SchoolActivity(
            id=str(uuid.uuid4()),
            school_id=school.id,
            activity_type="stage_change",
            title=f"Pipeline Stage Changed to {new_name}",
            notes=f"Progressed from '{old_name}' to '{new_name}'.",
            author="Admin",
            activity_date=datetime.now(),
        )
        db.add(stage_activity)
        
    db.commit()
    db.refresh(school)
    return school


@router.delete("/{school_id}")
def delete_school(school_id: str, db: Session = Depends(get_db)):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    db.delete(school)
    db.commit()
    return {"message": "School deleted"}


@router.get("/export/contacts-csv")
def export_contacts_csv(db: Session = Depends(get_db)):
    """Export all discovered SENCOs and leadership contacts as a mail-merge CSV."""
    from fastapi.responses import Response
    contacts = db.query(SchoolContact).join(School).order_by(School.name.asc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "School Name",
        "Phase",
        "Multi-Academy Trust",
        "Postcode",
        "Contact Name",
        "Role",
        "Email",
        "Email Verified",
        "Phone Extension",
        "Email Subject",
        "Email Draft Preview",
    ])
    
    for c in contacts:
        writer.writerow([
            c.school.name,
            c.school.phase or "",
            c.school.mat_name or "",
            c.school.postcode or "",
            c.name,
            c.role,
            c.email or "",
            "Yes" if c.email_is_verified else "No",
            c.phone_extension or "",
            c.email_subject or "",
            (c.email_draft or "").replace("\n", " ")[:200],
        ])
    
    csv_bytes = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=seemymind_contacts.csv"},
    )


@router.post("/import-csv")
async def import_schools_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Import schools from a CSV file.
    Supports standard CSVs or DfE GIAS (Get Information About Schools) export files.
    """
    contents = await file.read()
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = contents.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    imported_count = 0

    for row in reader:
        # Normalize column keys
        clean_row = {k.strip().lower(): v.strip() for k, v in row.items() if k and v}

        name = (
            clean_row.get("establishmentname")
            or clean_row.get("school name")
            or clean_row.get("name")
        )
        if not name:
            continue

        urn = clean_row.get("urn")
        if urn:
            existing = db.query(School).filter(School.urn == urn).first()
            if existing:
                continue
        elif name:
            existing = db.query(School).filter(School.name.ilike(name.strip())).first()
            if existing:
                continue
        phase = clean_row.get("phaseofeducation (name)") or clean_row.get("phase") or "Primary"
        school_type = clean_row.get("typeofestablishment (name)") or clean_row.get("type")
        mat_name = clean_row.get("trusts (name)") or clean_row.get("trust") or clean_row.get("mat_name")
        postcode = clean_row.get("postcode")
        website = clean_row.get("schoolwebsite") or clean_row.get("website")
        address = (
            clean_row.get("street") or clean_row.get("address")
        )

        sen_str = clean_row.get("sen_percentage") or clean_row.get("sen%")
        sen_val = float(sen_str) if sen_str and sen_str.replace(".", "", 1).isdigit() else 0.0

        school = School(
            name=name,
            urn=urn,
            phase=phase,
            school_type=school_type,
            mat_name=mat_name,
            website=website,
            postcode=postcode,
            address=address,
            sen_percentage=sen_val,
        )
        db.add(school)
        imported_count += 1

    db.commit()
    return {"imported": imported_count}


@router.post("/{school_id}/contacts")
def add_school_contact(
    school_id: str,
    payload: SchoolContactCreate,
    db: Session = Depends(get_db),
):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    # If adding a SENCO or Headteacher and a placeholder exists with drafts, transfer drafts
    placeholder = None
    role_lower = payload.role.lower()
    if "senco" in role_lower or "inclusion" in role_lower:
        placeholder = (
            db.query(SchoolContact)
            .filter(
                SchoolContact.school_id == school.id,
                SchoolContact.name.startswith("The "),
                SchoolContact.role.ilike("%senco%"),
            )
            .first()
        )
    elif "head" in role_lower or "principal" in role_lower:
        placeholder = (
            db.query(SchoolContact)
            .filter(
                SchoolContact.school_id == school.id,
                SchoolContact.name.startswith("The "),
                SchoolContact.role.ilike("%head%"),
            )
            .first()
        )

    contact = SchoolContact(
        id=str(uuid.uuid4()),
        school_id=school.id,
        name=payload.name.strip(),
        role=payload.role.strip(),
        email=payload.email.strip() if payload.email else None,
        email_is_verified=payload.email_is_verified or bool(payload.email),
        phone_extension=payload.phone_extension.strip() if payload.phone_extension else None,
        source=payload.source or "Manual Entry",
        status=ContactStatus.discovered,
        email_subject=placeholder.email_subject if placeholder else None,
        email_draft=placeholder.email_draft if placeholder else None,
        letter_draft=placeholder.letter_draft if placeholder else None,
        personalized_hook=placeholder.personalized_hook if placeholder else None,
    )

    if placeholder:
        db.delete(placeholder)

    db.add(contact)
    db.commit()
    db.refresh(contact)
    return {
        "message": "Contact created successfully",
        "contact_id": contact.id,
        "name": contact.name,
        "role": contact.role,
        "school_id": school.id,
    }


@router.delete("/contacts/{contact_id}")
def delete_school_contact(contact_id: str, db: Session = Depends(get_db)):
    contact = db.get(SchoolContact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()
    return {"message": "Contact deleted successfully"}


@router.post("/{school_id}/activities", status_code=201)
def add_school_activity(
    school_id: str,
    payload: SchoolActivityCreate,
    db: Session = Depends(get_db),
):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    activity = SchoolActivity(
        id=str(uuid.uuid4()),
        school_id=school.id,
        activity_type=payload.activity_type or "note",
        title=payload.title.strip(),
        notes=payload.notes.strip() if payload.notes else None,
        contact_name=payload.contact_name.strip() if payload.contact_name else None,
        author=payload.author or "Admin",
        activity_date=payload.activity_date or datetime.now(),
        next_follow_up_date=payload.next_follow_up_date,
        follow_up_task=payload.follow_up_task.strip() if payload.follow_up_task else None,
        follow_up_completed=False,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return {
        "message": "Activity logged successfully",
        "activity_id": activity.id,
        "title": activity.title,
        "activity_type": activity.activity_type,
    }


@router.delete("/activities/{activity_id}")
def delete_school_activity(activity_id: str, db: Session = Depends(get_db)):
    act = db.get(SchoolActivity, activity_id)
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    db.delete(act)
    db.commit()
    return {"message": "Activity deleted successfully"}

@router.post("/activities/{activity_id}/complete")
def complete_activity_task(activity_id: str, db: Session = Depends(get_db)):
    act = db.get(SchoolActivity, activity_id)
    if not act:
        raise HTTPException(status_code=404, detail="Activity not found")
    act.follow_up_completed = True
    db.commit()
    return {"message": "Task marked as complete", "activity_id": act.id}


@router.patch("/{school_id}/ofsted")
def update_school_ofsted(
    school_id: str,
    payload: OfstedUpdate,
    db: Session = Depends(get_db),
):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    if payload.ofsted_rating is not None:
        school.ofsted_rating = payload.ofsted_rating
    if payload.ofsted_inspection_date is not None:
        school.ofsted_inspection_date = payload.ofsted_inspection_date
    if payload.ofsted_send_excerpt is not None:
        school.ofsted_send_excerpt = payload.ofsted_send_excerpt

    # If school was in discovered stage, advance to qualified
    if school.pipeline_stage == SchoolPipelineStage.discovered:
        school.pipeline_stage = SchoolPipelineStage.qualified

    db.add(
        SchoolActivity(
            school_id=school.id,
            activity_type="note",
            title="Updated Ofsted Inspection Intelligence",
            notes=f"Rating: {school.ofsted_rating or 'Unspecified'} | Date: {school.ofsted_inspection_date or 'Unspecified'}\nFindings: {school.ofsted_send_excerpt or 'None'}",
            author="User",
        )
    )
    db.commit()
    db.refresh(school)
    return {"message": "Ofsted intelligence updated successfully", "school_id": school.id}


@router.post("/{school_id}/send-provision")
def update_send_provision(
    school_id: str,
    payload: SendProvisionUpdate,
    db: Session = Depends(get_db),
):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

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

    if payload.send_report_url is not None:
        run.send_report_url = payload.send_report_url
    if payload.detected_tools is not None:
        run.detected_tools = payload.detected_tools
    if payload.strengths_found is not None:
        run.strengths_found = payload.strengths_found
    if payload.challenges_found is not None:
        run.challenges_found = payload.challenges_found
    if payload.recommended_angle is not None:
        run.recommended_angle = payload.recommended_angle

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
            author="User",
        )
    )
    db.commit()
    return {"message": "SEND provision details updated successfully", "school_id": school.id}
