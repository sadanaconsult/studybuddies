from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app
from app.models.tables import LearningEvidence, SkillState


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _turn(c, sid, h, ch, text):
    r = c.post(f"/sessions/{sid}/turn", json={"household_id": str(h.id), "child_id": str(ch.id), "input": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_full_flow_assisted_then_independent(db, family):
    (h, ch), _ = family
    c = _client(db)
    sid = c.post("/sessions", json={"household_id": str(h.id), "child_id": str(ch.id)}).json()["session_id"]
    _turn(c, sid, h, ch, "hello")
    r = _turn(c, sid, h, ch, "4/8")          # correct value, not simplified -> help
    assert r["state"] == "learner_try"
    r = _turn(c, sid, h, ch, "1/2")          # assisted success
    assert r["state"] == "independent_transfer"
    r = _turn(c, sid, h, ch, "2/3")          # independent success
    assert r["state"] == "summarise"
    kinds = {(e.assistance_level, e.observation_kind) for e in db.query(LearningEvidence).all()}
    assert kinds == {("assisted", "supported_correct"), ("independent", "independent_correct")}
    st = db.query(SkillState).one()
    assert st.status == "emerging" and st.independent_successes == 1  # one success is not "demonstrated"


def test_assisted_evidence_never_counts_as_independent(db, family):
    (h, ch), _ = family
    c = _client(db)
    sid = c.post("/sessions", json={"household_id": str(h.id), "child_id": str(ch.id)}).json()["session_id"]
    for t in ("hello", "wrong", "1/2", "x"):
        _turn(c, sid, h, ch, t)
    st = db.query(SkillState).one()
    assert st.independent_successes == 0
    assert st.status in ("attempted", "emerging") and st.status != "demonstrated"
    data = c.get(f"/parent/{h.id}/{ch.id}").json()
    assert all(e["kind"].startswith("supported") for e in data["assisted_evidence"])
    assert all(e["kind"].startswith("independent") for e in data["independent_evidence"])


def test_household_isolation(db, family):
    (ha, ca), (hb, cb) = family
    c = _client(db)
    sid = c.post("/sessions", json={"household_id": str(ha.id), "child_id": str(ca.id)}).json()["session_id"]
    r = c.post(f"/sessions/{sid}/turn", json={"household_id": str(hb.id), "child_id": str(cb.id), "input": "hi"})
    assert r.status_code == 404
    assert c.get(f"/parent/{hb.id}/{ca.id}").status_code == 404
    assert c.post("/sessions", json={"household_id": str(hb.id), "child_id": str(ca.id)}).status_code == 404


def test_concern_gets_static_response(db, family):
    (h, ch), _ = family
    c = _client(db)
    sid = c.post("/sessions", json={"household_id": str(h.id), "child_id": str(ch.id)}).json()["session_id"]
    r = _turn(c, sid, h, ch, "I want to hurt myself")
    assert r["gate_outcome"] == "blocked_concern" and r["state"] == "orient"


def test_hint_ladder_escalates_and_caps(db, family):
    from app.models.tables import TutoringSession
    (h, ch), _ = family
    c = _client(db)
    sid = c.post("/sessions", json={"household_id": str(h.id), "child_id": str(ch.id)}).json()["session_id"]
    levels = []
    for t in ["hello", "wrong"] + ["nope"] * 5:
        _turn(c, sid, h, ch, t)
        levels.append(db.query(TutoringSession).one().hint_level)
        db.expire_all()
    assert levels[-1] == 3 and max(levels) == 3
    assert levels == sorted(levels)


def test_correction_invalidates_and_suppresses_memory(db, family):
    from app.models.tables import MemoryFact
    (h, ch), _ = family
    c = _client(db)
    # two sessions, each ending with an independent success -> demonstrated
    for _ in range(2):
        sid = c.post("/sessions", json={"household_id": str(h.id), "child_id": str(ch.id)}).json()["session_id"]
        _turn(c, sid, h, ch, "hello")
        _turn(c, sid, h, ch, "1/2")      # correct first try -> straight to transfer
        _turn(c, sid, h, ch, "2/3")
    assert db.query(SkillState).one().status == "demonstrated"
    cap = db.query(MemoryFact).filter_by(recall_allowed=True).all()
    assert cap
    ev = db.query(LearningEvidence).filter_by(observation_kind="independent_correct").first()
    r = c.post("/evidence/correct", json={"household_id": str(h.id), "child_id": str(ch.id), "evidence_id": str(ev.id)})
    assert r.status_code == 200
    db.expire_all()
    assert db.query(SkillState).one().status == "emerging"
    for m in db.query(MemoryFact).filter_by(recall_allowed=True):
        assert str(ev.id) not in (m.evidence_refs or [])
    assert any(str(ev.id) in (m.evidence_refs or []) and not m.recall_allowed for m in db.query(MemoryFact))
    # wrong household cannot correct it
    (hb, cb) = family[1]
    assert c.post("/evidence/correct", json={"household_id": str(hb.id), "child_id": str(cb.id), "evidence_id": str(ev.id)}).status_code == 404
