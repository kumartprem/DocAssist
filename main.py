import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Case, ChecklistItem
from schemas import CaseCreate, CaseOut, CaseSummary, ChecklistItemCreate, ChecklistItemOut

Base.metadata.create_all(bind=engine)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="DocAssist — Document Collection Assistant")

templates = Jinja2Templates(directory="templates")


# ─── API: Cases ───────────────────────────────────────────────

@app.post("/api/cases", response_model=CaseOut)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)):
    case = Case(
        title=payload.title,
        client_name=payload.client_name,
        client_email=payload.client_email,
    )
    db.add(case)
    db.flush()

    for item_name in payload.checklist_items:
        db.add(ChecklistItem(case_id=case.id, name=item_name))

    db.commit()
    db.refresh(case)
    return case


@app.get("/api/cases", response_model=list[CaseSummary])
def list_cases(db: Session = Depends(get_db)):
    cases = db.query(Case).order_by(Case.created_at.desc()).all()
    result = []
    for c in cases:
        result.append(CaseSummary(
            id=c.id,
            title=c.title,
            client_name=c.client_name,
            client_email=c.client_email,
            created_at=c.created_at,
            total_items=len(c.checklist_items),
            received_items=sum(1 for i in c.checklist_items if i.is_received),
        ))
    return result


@app.get("/api/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: int, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(404, "Case not found")
    return case


@app.delete("/api/cases/{case_id}")
def delete_case(case_id: int, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(404, "Case not found")
    db.delete(case)
    db.commit()
    return {"ok": True}


# ─── API: Checklist Items ────────────────────────────────────

@app.post("/api/cases/{case_id}/checklist", response_model=ChecklistItemOut)
def add_checklist_item(
    case_id: int, payload: ChecklistItemCreate, db: Session = Depends(get_db)
):
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(404, "Case not found")
    item = ChecklistItem(case_id=case_id, name=payload.name, description=payload.description)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.delete("/api/checklist/{item_id}")
def delete_checklist_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()
    if not item:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


# ─── API: Client Upload ──────────────────────────────────────

@app.get("/api/client/{token}", response_model=CaseOut)
def get_case_by_token(token: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.access_token == token).first()
    if not case:
        raise HTTPException(404, "Invalid link")
    return case


@app.post("/api/client/{token}/upload/{item_id}", response_model=ChecklistItemOut)
async def upload_document(
    token: str, item_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    case = db.query(Case).filter(Case.access_token == token).first()
    if not case:
        raise HTTPException(404, "Invalid link")

    item = db.query(ChecklistItem).filter(
        ChecklistItem.id == item_id, ChecklistItem.case_id == case.id
    ).first()
    if not item:
        raise HTTPException(404, "Checklist item not found")

    case_dir = UPLOAD_DIR / str(case.id)
    case_dir.mkdir(exist_ok=True)

    safe_name = f"{item_id}_{file.filename}"
    file_path = case_dir / safe_name
    content = await file.read()
    file_path.write_bytes(content)

    item.is_received = True
    item.uploaded_file_path = str(file_path)
    item.uploaded_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return item


# ─── Pages ────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/portal/{token}", response_class=HTMLResponse)
def client_portal_page(request: Request, token: str, db: Session = Depends(get_db)):
    case = db.query(Case).filter(Case.access_token == token).first()
    if not case:
        raise HTTPException(404, "Invalid link")
    return templates.TemplateResponse(request, "portal.html", {"token": token})
