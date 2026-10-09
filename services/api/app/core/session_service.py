"""Orchestrates one tutoring turn: intent -> state machine -> verifier ->
tutor text (gated) -> evidence writer. All child-scoped queries filter by
both household_id and child_id (AGENTS.md rule 10)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.tables import AssessmentAttempt, TutoringSession, TutoringTurn
from .evidence import record_attempt_evidence, write_resolution_capsule
from .fractions import FractionItem, verify_answer
from .items import GeneratedItem, canonical_worked_example, generate_baseline_item, generate_transfer_item
from .state_machine import SessionState, classify_intent_heuristic
from .tutor import generate_tutor_turn

SKILL_ID = "fraction_addition_same_denominator"


class ScopeError(LookupError):
    """Session not found within the given household/child scope."""


def _item_to_json(g: GeneratedItem) -> dict:
    return {
        "a": g.item.numerator_a,
        "b": g.item.numerator_b,
        "d": g.item.denominator,
        "family": g.family,
        "requires_simplification": g.requires_simplification,
        "prompt": g.prompt,
    }


def _item_from_json(j: dict) -> GeneratedItem:
    return GeneratedItem(
        item=FractionItem(j["a"], j["b"], j["d"]),
        family=j["family"],
        requires_simplification=j["requires_simplification"],
        prompt=j["prompt"],
    )


def start_session(db: Session, *, household_id: uuid.UUID, child_id: uuid.UUID, canonical: bool = True) -> TutoringSession:
    if canonical:
        baseline, transfer = canonical_worked_example()
    else:
        baseline = generate_baseline_item()
        transfer = generate_transfer_item(baseline)
    s = TutoringSession(
        household_id=household_id,
        child_id=child_id,
        skill_id=SKILL_ID,
        state="orient",
        baseline_item_json=_item_to_json(baseline),
        transfer_item_json=_item_to_json(transfer),
    )
    db.add(s)
    db.flush()
    return s


def get_scoped_session(db: Session, session_id: uuid.UUID, household_id: uuid.UUID, child_id: uuid.UUID) -> TutoringSession:
    s = (
        db.query(TutoringSession)
        .filter(
            TutoringSession.id == session_id,
            TutoringSession.household_id == household_id,
            TutoringSession.child_id == child_id,
        )
        .one_or_none()
    )
    if s is None:
        raise ScopeError("session not found for this household/child")
    return s


@dataclass
class TurnResponse:
    tutor_text: str
    state: str
    gate_outcome: str
    verification: dict | None
    visual: dict | None


def _log_turn(db, s, *, speaker, state, intent=None, child_input=None, raw=None, gated=None, outcome=None):
    s.current_turn_sequence += 1
    db.add(TutoringTurn(
        session_id=s.id, household_id=s.household_id, child_id=s.child_id,
        sequence=s.current_turn_sequence, speaker=speaker, state_at_turn=state,
        turn_intent=intent, child_input=child_input, raw_model_output=raw,
        gated_output=gated, gate_outcome=outcome,
    ))


def _record_attempt(db, s, item: GeneratedItem, raw_answer: str, assistance: str):
    v = verify_answer(item.item, raw_answer)
    attempt = AssessmentAttempt(
        household_id=s.household_id, child_id=s.child_id, session_id=s.id,
        item_family=item.family, item_prompt=item.prompt, response_raw=raw_answer[:64],
        assistance_level=assistance, is_value_correct=v.is_value_correct,
        is_form_correct=v.is_form_correct, result_detail=v.detail,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.flush()
    record_attempt_evidence(db, household_id=s.household_id, child_id=s.child_id, skill_id=s.skill_id, attempt=attempt)
    return v


def _visual_for(item: GeneratedItem) -> dict:
    return {"type": "fraction_bar", "denominator": item.denominator,
            "a": item.item.numerator_a, "b": item.item.numerator_b}


def process_turn(db: Session, s: TutoringSession, child_input: str) -> TurnResponse:
    baseline = _item_from_json(s.baseline_item_json)
    transfer = _item_from_json(s.transfer_item_json)
    hint_level = s.__dict__.get("_hint_level", 0)
    intent = classify_intent_heuristic(child_input)
    state_before = s.state

    # Safeguarding-shaped input: fixed safe response, no generation (rule 9).
    if intent == "report_concern":
        from .safety_gate import SAFE_CONCERN_RESPONSE
        _log_turn(db, s, speaker="child", state=state_before, intent=intent, child_input=child_input)
        _log_turn(db, s, speaker="tutor", state=state_before, gated=SAFE_CONCERN_RESPONSE, outcome="blocked_concern")
        return TurnResponse(SAFE_CONCERN_RESPONSE, s.state, "blocked_concern", None, None)

    _log_turn(db, s, speaker="child", state=state_before, intent=intent, child_input=child_input)
    verification = None
    machine = SessionState(state=s.state)
    item = baseline

    if s.state == "orient":
        machine.transition("elicit_attempt")
        visual = _visual_for(baseline)
        text = f"Hi! Let's try {baseline.prompt}. What do you think the answer is?"
        s.state = machine.state
        _log_turn(db, s, speaker="tutor", state=s.state, gated=text, outcome="approved")
        return TurnResponse(text, s.state, "approved", None, visual)

    if s.state == "elicit_attempt":
        # Diagnostic attempt before any help; recorded as an attempt but
        # NOT counted as independent evidence (not in independent_transfer).
        v = verify_answer(baseline.item, child_input)
        verification = {"value_correct": v.is_value_correct, "form_correct": v.is_form_correct, "detail": v.detail}
        machine.transition("diagnose")
        if v.is_fully_correct:
            machine.transition("independent_transfer")
            item = transfer
            text = f"Great thinking! Now try a new one on your own: {transfer.prompt}"
            s.state = machine.state
            _log_turn(db, s, speaker="tutor", state=s.state, gated=text, outcome="approved")
            return TurnResponse(text, s.state, "approved", verification, _visual_for(transfer))
        machine.transition("teach_or_hint")
        s.state = machine.state

    if s.state == "teach_or_hint" and state_before != "learner_try":
        result = generate_tutor_turn(state=s.state, child_input=child_input, item=baseline, hint_level=1)
        machine.state = s.state
        machine.transition("learner_try")
        s.state = machine.state
        d = result.gate_decision
        _log_turn(db, s, speaker="tutor", state=s.state, raw=result.raw_model_output, gated=d.output_text, outcome=d.outcome)
        return TurnResponse(d.output_text, s.state, d.outcome, verification, _visual_for(baseline))

    if s.state == "learner_try":
        machine.state = s.state
        v = _record_attempt(db, s, baseline, child_input, "assisted")
        verification = {"value_correct": v.is_value_correct, "form_correct": v.is_form_correct, "detail": v.detail}
        machine.transition("feedback")
        if v.is_fully_correct:
            machine.transition("independent_transfer")
            s.state = machine.state
            text = f"Well done! You had some help that time, so let's see you do a new one on your own: {transfer.prompt}"
            _log_turn(db, s, speaker="tutor", state=s.state, gated=text, outcome="approved")
            return TurnResponse(text, s.state, "approved", verification, _visual_for(transfer))
        machine.transition("teach_or_hint")
        s.state = "learner_try"  # allow another try after a bigger hint
        result = generate_tutor_turn(state="teach_or_hint", child_input=child_input, item=baseline, hint_level=2)
        d = result.gate_decision
        _log_turn(db, s, speaker="tutor", state=s.state, raw=result.raw_model_output, gated=d.output_text, outcome=d.outcome)
        return TurnResponse(d.output_text, s.state, d.outcome, verification, _visual_for(baseline))

    if s.state == "independent_transfer":
        machine.state = s.state
        machine.record_independent_attempt()
        v = _record_attempt(db, s, transfer, child_input, "independent")
        verification = {"value_correct": v.is_value_correct, "form_correct": v.is_form_correct, "detail": v.detail}
        machine.transition("summarise")
        s.state = machine.state
        s.ended_at = datetime.now(timezone.utc)
        write_resolution_capsule(db, household_id=s.household_id, child_id=s.child_id, skill_id=s.skill_id)
        text = ("Thanks for trying that on your own! Your parent can see how you got on."
                if v.is_value_correct else
                "Thanks for having a go on your own. We'll practise this more next time.")
        _log_turn(db, s, speaker="tutor", state=s.state, gated=text, outcome="approved")
        return TurnResponse(text, s.state, "approved", verification, None)

    text = "This session is finished."
    return TurnResponse(text, s.state, "approved", None, None)
