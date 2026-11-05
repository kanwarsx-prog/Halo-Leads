from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from smm_app.database import get_db
from smm_app.models import School, SchoolContact, SchoolAuditRun, PromptConfig, SchoolPipelineStage, ContactStatus, SchoolActivity
from smm_app.prompts import DEFAULT_PROMPTS, get_prompt

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    schools = db.query(School).order_by(School.created_at.desc()).all()
    # Exclude role placeholders from named contacts metric
    contacts_count = (
        db.query(SchoolContact)
        .filter(~SchoolContact.name.startswith("The "))
        .count()
    )
    high_priority_count = sum(1 for s in schools if s.priority == "Immediate Focus")

    pending_tasks = (
        db.query(SchoolActivity)
        .join(School)
        .filter(
            SchoolActivity.next_follow_up_date.isnot(None),
            SchoolActivity.follow_up_completed.is_(False),
        )
        .order_by(SchoolActivity.next_follow_up_date.asc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "schools": schools,
            "total_schools": len(schools),
            "contacts_count": contacts_count,
            "high_priority_count": high_priority_count,
            "pending_tasks": pending_tasks,
            "now": datetime.now(),
        },
    )


@router.get("/schools/{school_id}")
def school_detail(school_id: str, request: Request, db: Session = Depends(get_db)):
    school = db.get(School, school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found")

    runs = (
        db.query(SchoolAuditRun)
        .filter(SchoolAuditRun.school_id == school.id)
        .order_by(SchoolAuditRun.started_at.desc())
        .all()
    )
    latest_run = runs[0] if runs else None

    contacts = (
        db.query(SchoolContact)
        .filter(SchoolContact.school_id == school.id)
        .order_by(SchoolContact.created_at.asc())
        .all()
    )
    named_contacts = [c for c in contacts if not c.name.startswith("The ")]
    has_named_senco = any("senco" in c.role.lower() or "inclusion" in c.role.lower() for c in named_contacts)
    has_named_head = any("head" in c.role.lower() or "principal" in c.role.lower() for c in named_contacts)

    activities = (
        db.query(SchoolActivity)
        .filter(SchoolActivity.school_id == school.id)
        .order_by(SchoolActivity.activity_date.desc(), SchoolActivity.created_at.desc())
        .all()
    )

    active_follow_up = (
        db.query(SchoolActivity)
        .filter(
            SchoolActivity.school_id == school.id,
            SchoolActivity.next_follow_up_date.isnot(None),
            SchoolActivity.follow_up_completed.is_(False),
        )
        .order_by(SchoolActivity.next_follow_up_date.asc())
        .first()
    )

    return templates.TemplateResponse(
        request=request,
        name="detail.html",
        context={
            "school": school,
            "runs": runs,
            "latest_run": latest_run,
            "contacts": contacts,
            "named_contacts": named_contacts,
            "has_named_senco": has_named_senco,
            "has_named_head": has_named_head,
            "stages": [s.value for s in SchoolPipelineStage],
            "activities": activities,
            "active_follow_up": active_follow_up,
        },
    )


@router.get("/contacts")
def contacts_directory(request: Request, db: Session = Depends(get_db)):
    # Only list actual named individuals, exclude role placeholders
    contacts = (
        db.query(SchoolContact)
        .join(School)
        .filter(~SchoolContact.name.startswith("The "))
        .order_by(School.name.asc(), SchoolContact.role.asc())
        .all()
    )
    schools = db.query(School).order_by(School.name.asc()).all()
    total_contacts = len(contacts)
    sencos = [c for c in contacts if "senco" in c.role.lower()]
    verified_emails = sum(1 for c in contacts if c.email_is_verified)

    return templates.TemplateResponse(
        request=request,
        name="contacts.html",
        context={
            "contacts": contacts,
            "schools": schools,
            "total_contacts": total_contacts,
            "senco_count": len(sencos),
            "verified_count": verified_emails,
        },
    )


@router.get("/config")
def prompt_config(request: Request, db: Session = Depends(get_db)):
    for name in DEFAULT_PROMPTS:
        get_prompt(db, name)
    prompts = db.query(PromptConfig).all()

    return templates.TemplateResponse(
        request=request,
        name="config.html",
        context={"prompts": prompts},
    )

def build_cluster_data(schools: list[School], group_by: str) -> list[dict]:
    """
    Groups schools by 'mat_name' or 'local_authority' and aggregates metrics.
    """
    clusters_map = {}
    for s in schools:
        raw_val = getattr(s, group_by, None)
        key = (raw_val or "").strip()
        if not key:
            continue
        if key not in clusters_map:
            clusters_map[key] = {
                "name": key,
                "group_type": "mat" if group_by == "mat_name" else "la",
                "schools": [],
                "total_schools": 0,
                "total_contacts": 0,
                "senco_count": 0,
                "head_count": 0,
                "stages_count": {},
                "sen_values": [],
                "avg_sen": 0.0,
                "max_score": 0,
                "top_school": None,
                "active_tasks": [],
                "has_demo": False,
                "has_won": False,
                "has_outreach_ready": False,
            }
        c = clusters_map[key]
        c["schools"].append(s)
        c["total_schools"] += 1

        named_c = [ct for ct in (s.contacts or []) if not ct.name.startswith("The ")]
        c["total_contacts"] += len(named_c)
        c["senco_count"] += sum(1 for ct in named_c if "senco" in ct.role.lower() or "inclusion" in ct.role.lower())
        c["head_count"] += sum(1 for ct in named_c if "head" in ct.role.lower() or "principal" in ct.role.lower())

        st_val = s.pipeline_stage.value if hasattr(s.pipeline_stage, "value") else str(s.pipeline_stage)
        c["stages_count"][st_val] = c["stages_count"].get(st_val, 0) + 1
        if st_val == "demo_booked":
            c["has_demo"] = True
        elif st_val == "partner_won":
            c["has_won"] = True
        elif st_val == "outreach_ready":
            c["has_outreach_ready"] = True

        if s.sen_percentage and s.sen_percentage > 0:
            c["sen_values"].append(s.sen_percentage)

        score = s.overall_score or 0
        if c["top_school"] is None or score > c["max_score"]:
            c["max_score"] = score
            c["top_school"] = s

        for act in (s.activities or []):
            if act.next_follow_up_date and not act.follow_up_completed:
                c["active_tasks"].append({"school": s, "task": act})

    res = list(clusters_map.values())
    for c in res:
        if c["sen_values"]:
            c["avg_sen"] = round(sum(c["sen_values"]) / len(c["sen_values"]), 1)
        c["schools"].sort(key=lambda sc: (-(sc.overall_score or 0), sc.name))

    res.sort(key=lambda cl: (-cl["total_schools"], -cl["avg_sen"], cl["name"]))
    return res


@router.get("/rollups")
def rollups_overview(request: Request, db: Session = Depends(get_db)):
    schools = db.query(School).order_by(School.name.asc()).all()

    mat_clusters = build_cluster_data(schools, "mat_name")
    la_clusters = build_cluster_data(schools, "local_authority")

    standalone_schools = [s for s in schools if not s.mat_name or not s.mat_name.strip()]
    standalone_contacts = sum(len(s.named_contacts) for s in standalone_schools)

    total_in_mats = sum(c["total_schools"] for c in mat_clusters)
    high_need_mats = sum(1 for c in mat_clusters if c["avg_sen"] >= 16.0)
    high_need_las = sum(1 for c in la_clusters if c["avg_sen"] >= 16.0)
    clusters_with_demos = sum(1 for c in mat_clusters if c["has_demo"])
    clusters_with_wins = sum(1 for c in mat_clusters if c["has_won"])

    return templates.TemplateResponse(
        request=request,
        name="rollups.html",
        context={
            "mats": mat_clusters,
            "las": la_clusters,
            "standalone_schools": standalone_schools,
            "standalone_count": len(standalone_schools),
            "standalone_contacts": standalone_contacts,
            "total_in_mats": total_in_mats,
            "high_need_mats": high_need_mats,
            "high_need_las": high_need_las,
            "clusters_with_demos": clusters_with_demos,
            "clusters_with_wins": clusters_with_wins,
            "total_schools": len(schools),
            "now": datetime.now(),
        },
    )

@router.get("/kanban")
def kanban_board(request: Request, db: Session = Depends(get_db)):
    schools = db.query(School).order_by(School.overall_score.desc()).all()
    contacts_count = (
        db.query(SchoolContact)
        .filter(~SchoolContact.name.startswith("The "))
        .count()
    )

    kanban_stages = [
        {"id": "discovered", "name": "Discovered", "icon": "🔍", "color": "#475569", "border": "#94a3b8"},
        {"id": "qualified", "name": "Qualified", "icon": "🎯", "color": "#0284c7", "border": "#38bdf8"},
        {"id": "outreach_ready", "name": "Outreach Ready", "icon": "✉️", "color": "var(--teal)", "border": "var(--teal)"},
        {"id": "contacted", "name": "Contacted", "icon": "📞", "color": "#d97706", "border": "#f59e0b"},
        {"id": "demo_booked", "name": "Demo Booked", "icon": "⭐", "color": "#8b5cf6", "border": "#a855f7"},
        {"id": "partner_won", "name": "Partner Won", "icon": "🏆", "color": "#16a34a", "border": "#22c55e"},
    ]

    stages_map = {st["id"]: [] for st in kanban_stages}
    disqualified_count = 0
    for s in schools:
        st_val = s.pipeline_stage.value if hasattr(s.pipeline_stage, "value") else str(s.pipeline_stage)
        if st_val in stages_map:
            stages_map[st_val].append(s)
        else:
            disqualified_count += 1

    return templates.TemplateResponse(
        request=request,
        name="kanban.html",
        context={
            "stages": kanban_stages,
            "stages_map": stages_map,
            "total_schools": len(schools),
            "contacts_count": contacts_count,
            "disqualified_count": disqualified_count,
            "now": datetime.now(),
        },
    )
