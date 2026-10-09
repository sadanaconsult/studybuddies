from __future__ import annotations

import base64
import secrets
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .core.config import settings
from .core.db import Base, engine, get_db
from .core.evidence import invalidate_evidence
from .core.session_service import ScopeError, get_scoped_session, process_turn, start_session
from .models.tables import ChildProfile, LearningEvidence, MemoryFact, SkillState

BASE = Path(__file__).parent
app = FastAPI(title="Tutor Buddy prototype (fraction addition)")


@app.on_event("startup")
def _create_tables() -> None:
    from .models import tables  # noqa: F401  (register models)
    Base.metadata.create_all(engine)


@app.middleware("http")
async def demo_password_gate(request: Request, call_next):
    """Shared-password basic auth for demo deployments. Not real auth
    (AGENTS.md: real guardian/child auth is out of scope)."""
    if not settings.demo_password or request.url.path == "/healthz":
        return await call_next(request)
    header = request.headers.get("authorization", "")
    ok = False
    if header.lower().startswith("basic "):
        try:
            _, _, pw = base64.b64decode(header[6:]).decode().partition(":")
            ok = secrets.compare_digest(pw, settings.demo_password)
        except Exception:
            ok = False
    if ok:
        return await call_next(request)
    return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Tutor Buddy demo"'})


@app.get("/healthz")
def healthz():
    return {"ok": True}


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))


class StartSessionBody(BaseModel):
    household_id: uuid.UUID
    child_id: uuid.UUID
    canonical: bool = True


class TurnBody(BaseModel):
    household_id: uuid.UUID
    child_id: uuid.UUID
    input: str


def _require_child(db: Session, household_id: uuid.UUID, child_id: uuid.UUID) -> ChildProfile:
    child = (
        db.query(ChildProfile)
        .filter(ChildProfile.id == child_id, ChildProfile.household_id == household_id)
        .one_or_none()
    )
    if child is None:
        raise HTTPException(404, "child not found in household")
    return child


@app.post("/sessions")
def create_session(body: StartSessionBody, db: Session = Depends(get_db)):
    _require_child(db, body.household_id, body.child_id)
    s = start_session(db, household_id=body.household_id, child_id=body.child_id, canonical=body.canonical)
    db.commit()
    return {"session_id": str(s.id), "state": s.state}


@app.post("/sessions/{session_id}/turn")
def post_turn(session_id: uuid.UUID, body: TurnBody, db: Session = Depends(get_db)):
    try:
        s = get_scoped_session(db, session_id, body.household_id, body.child_id)
    except ScopeError:
        raise HTTPException(404, "session not found")
    r = process_turn(db, s, body.input)
    db.commit()
    return {
        "tutor_text": r.tutor_text,
        "state": r.state,
        "gate_outcome": r.gate_outcome,
        "verification": r.verification,
        "visual": r.visual,
    }


@app.get("/session/{session_id}", response_class=HTMLResponse)
def session_page(request: Request, session_id: uuid.UUID, household_id: uuid.UUID, child_id: uuid.UUID):
    return templates.TemplateResponse(
        request, "session.html",
        {"session_id": session_id, "household_id": household_id, "child_id": child_id},
    )


@app.get("/parent/{household_id}/{child_id}")
def parent_data(household_id: uuid.UUID, child_id: uuid.UUID, db: Session = Depends(get_db)):
    child = _require_child(db, household_id, child_id)
    ev = (
        db.query(LearningEvidence)
        .filter(LearningEvidence.household_id == household_id, LearningEvidence.child_id == child_id,
                LearningEvidence.invalidated_at.is_(None))
        .order_by(LearningEvidence.valid_at.asc()).all()
    )
    state = (
        db.query(SkillState)
        .filter(SkillState.household_id == household_id, SkillState.child_id == child_id).all()
    )
    caps = (
        db.query(MemoryFact)
        .filter(MemoryFact.household_id == household_id, MemoryFact.child_id == child_id,
                MemoryFact.recall_allowed.is_(True)).all()
    )
    return {
        "child": child.display_name,
        "assisted_evidence": [
            {"when": e.valid_at.isoformat(), "kind": e.observation_kind}
            for e in ev if e.assistance_level == "assisted"
        ],
        "independent_evidence": [
            {"when": e.valid_at.isoformat(), "kind": e.observation_kind}
            for e in ev if e.assistance_level == "independent"
        ],
        "skills": [
            {"skill": s.skill_id, "status": s.status, "independent_successes": s.independent_successes}
            for s in state
        ],
        "dated_records": [c.structured_payload for c in caps],
        "note": "Assisted work is shown separately and never counts as independent evidence.",
    }


@app.get("/parent", response_class=HTMLResponse)
def parent_page(request: Request):
    return templates.TemplateResponse(request, "parent.html", {})


class CorrectBody(BaseModel):
    household_id: uuid.UUID
    child_id: uuid.UUID
    evidence_id: uuid.UUID


@app.post("/evidence/correct")
def correct_evidence(body: CorrectBody, db: Session = Depends(get_db)):
    """Invalidate one evidence row (e.g. mis-transcribed answer). Scoped."""
    row = (
        db.query(LearningEvidence)
        .filter(LearningEvidence.id == body.evidence_id,
                LearningEvidence.household_id == body.household_id,
                LearningEvidence.child_id == body.child_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "evidence not found")
    invalidate_evidence(db, row.id)
    db.commit()
    return {"invalidated": str(row.id)}
