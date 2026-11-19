from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from smm_app.database import get_db
from smm_app.models import ProductRequest, ProductRequestSource, ProductRequestStatus, School

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
router = APIRouter(prefix="/product-requests", tags=["product-requests"])


@router.get("")
@router.get("/")
def product_requests(request: Request, db: Session = Depends(get_db)):
    requests = db.query(ProductRequest).order_by(ProductRequest.created_at.desc()).all()
    stats = {
        "total": len(requests),
        "new": sum(r.status == ProductRequestStatus.new for r in requests),
        "planned": sum(r.status in (ProductRequestStatus.planned, ProductRequestStatus.in_progress) for r in requests),
        "school_voice": sum(r.source == ProductRequestSource.school for r in requests),
    }
    return templates.TemplateResponse(request=request, name="product_requests.html", context={
        "requests": requests,
        "schools": db.query(School).order_by(School.name.asc()).all(),
        "statuses": [s.value for s in ProductRequestStatus],
        "sources": [s.value for s in ProductRequestSource],
        "stats": stats,
        "now": datetime.now(),
    })


@router.post("")
def create_product_request(
    title: str = Form(...), description: str = Form(...), source: str = Form("internal"),
    requester_name: str | None = Form(None), product_area: str | None = Form(None),
    priority: str = Form("Medium"), school_id: str | None = Form(None),
    db: Session = Depends(get_db),
):
    item = ProductRequest(
        title=title.strip(), description=description.strip(), source=ProductRequestSource(source),
        requester_name=(requester_name or "").strip() or None, product_area=(product_area or "").strip() or None,
        priority=priority, school_id=school_id or None,
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url="/seemymind/product-requests", status_code=303)


@router.post("/{request_id}/status")
def update_product_request_status(request_id: str, status: str = Form(...), db: Session = Depends(get_db)):
    item = db.get(ProductRequest, request_id)
    if item:
        item.status = ProductRequestStatus(status)
        db.commit()
    return RedirectResponse(url="/seemymind/product-requests", status_code=303)


@router.get("/search")
def search_product_requests(q: str = "", status: str | None = None, limit: int = 10, db: Session = Depends(get_db)):
    query = db.query(ProductRequest)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(or_(ProductRequest.title.ilike(term), ProductRequest.description.ilike(term), ProductRequest.product_area.ilike(term)))
    if status:
        query = query.filter(ProductRequest.status == ProductRequestStatus(status))
    rows = query.order_by(ProductRequest.created_at.desc()).limit(min(limit, 50)).all()
    return [{"id": r.id, "title": r.title, "description": r.description, "source": r.source.value, "status": r.status.value, "priority": r.priority, "school": r.school.name if r.school else None} for r in rows]


@router.get("/{request_id}")
def product_request_detail(request_id: str, request: Request, db: Session = Depends(get_db)):
    item = db.get(ProductRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Product request not found")
    return templates.TemplateResponse(request=request, name="product_request_detail.html", context={
        "item": item,
        "schools": db.query(School).order_by(School.name.asc()).all(),
        "statuses": [s.value for s in ProductRequestStatus],
        "sources": [s.value for s in ProductRequestSource],
    })


@router.post("/{request_id}")
def update_product_request(
    request_id: str,
    title: str = Form(...), description: str = Form(...), source: str = Form(...),
    requester_name: str | None = Form(None), product_area: str | None = Form(None),
    priority: str = Form("Medium"), status: str = Form("new"), school_id: str | None = Form(None),
    owner: str | None = Form(None), target_release: str | None = Form(None), internal_notes: str | None = Form(None),
    impact_score: int = Form(3), effort_score: int = Form(3), evidence_score: int = Form(1),
    db: Session = Depends(get_db),
):
    item = db.get(ProductRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Product request not found")
    item.title = title.strip()
    item.description = description.strip()
    item.source = ProductRequestSource(source)
    item.requester_name = (requester_name or "").strip() or None
    item.product_area = (product_area or "").strip() or None
    item.priority = priority
    item.status = ProductRequestStatus(status)
    item.school_id = school_id or None
    item.owner = (owner or "").strip() or None
    item.target_release = (target_release or "").strip() or None
    item.internal_notes = (internal_notes or "").strip() or None
    item.impact_score = max(1, min(5, impact_score))
    item.effort_score = max(1, min(5, effort_score))
    item.evidence_score = max(1, min(5, evidence_score))
    db.commit()
    return RedirectResponse(url=f"/seemymind/product-requests/{item.id}", status_code=303)
