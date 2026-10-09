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
