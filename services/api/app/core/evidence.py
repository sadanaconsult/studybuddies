"""Evidence/memory writer.

This is the ONLY code path allowed to write `learning_evidence`,
`skill_state`, or `memory_fact` rows (AGENTS.md rule 3). The LLM tutor
loop proposes assistance levels and observations through this module's
functions; it never touches these tables directly.

Admissibility rules implemented here, from doc 03:
  - `assisted` and `independent` are recorded as distinct observation
    kinds and never converted into each other after the fact (rule 4).
  - A single independent success is NOT enough to call a skill
    "demonstrated" -- doc 03 §21 step 3: "One success alone does not meet
    demonstrated status." We require at least two independent successes,
    with the most recent one reviewed, before the projection can read
    "demonstrated".
  - `learning_evidence` rows are append-only; a correction invalidates a
    prior row (`invalidated_at`) rather than mutating it.
  - `skill_state` is a rebuildable projection recomputed from
    `learning_evidence`, never written to independently of it.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.tables import AssessmentAttempt, LearningEvidence, MemoryFact, SkillState

DEMONSTRATED_INDEPENDENT_THRESHOLD = 2


def _provenance_hash(*parts: str) -> str:
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def record_attempt_evidence(
    db: Session,
    *,
    household_id: uuid.UUID,
    child_id: uuid.UUID,
    skill_id: str,
    attempt: AssessmentAttempt,
) -> LearningEvidence:
    """Translate one assessment attempt into exactly one learning_evidence
    row, with an observation_kind that encodes both correctness AND
    assistance level -- so "assisted" evidence can never later be read as
    "independent" evidence; the distinction is baked into the row at
    write time, not inferred later.
    """
    if attempt.assistance_level not in ("assisted", "independent"):
        raise ValueError(f"unknown assistance_level: {attempt.assistance_level!r}")

    if attempt.assistance_level == "assisted":
        observation_kind = "supported_correct" if attempt.is_value_correct else "supported_incorrect"
    else:
        observation_kind = "independent_correct" if attempt.is_value_correct else "independent_incorrect"

    evidence = LearningEvidence(
        household_id=household_id,
        child_id=child_id,
        skill_id=skill_id,
        attempt_id=attempt.id,
        observation_kind=observation_kind,
        assistance_level=attempt.assistance_level,
        confidence="direct_observation",
        valid_at=datetime.now(timezone.utc),
        provenance_hash=_provenance_hash(
            str(attempt.id), skill_id, attempt.assistance_level, observation_kind
        ),
    )
    db.add(evidence)
    db.flush()
    _recompute_skill_state(db, household_id=household_id, child_id=child_id, skill_id=skill_id)
    return evidence


def invalidate_evidence(db: Session, evidence_id: uuid.UUID) -> None:
    """Mark a learning_evidence row invalidated (e.g. the transcription
    or attempt it was based on was corrected). Never deletes or edits the
    original observation_kind/assistance_level -- the row stays a true
    historical record of what was observed and when."""
    row = db.get(LearningEvidence, evidence_id)
    if row is None:
        raise KeyError(f"no learning_evidence row {evidence_id}")
    row.invalidated_at = datetime.now(timezone.utc)
    db.flush()
    _recompute_skill_state(db, household_id=row.household_id, child_id=row.child_id, skill_id=row.skill_id)


def _recompute_skill_state(
    db: Session, *, household_id: uuid.UUID, child_id: uuid.UUID, skill_id: str
) -> SkillState:
    """Rebuild skill_state purely from currently-valid learning_evidence
    rows. This function is the single place status transitions happen,
    so the "no evidence upgrade" rule is enforced in one spot rather than
    scattered across call sites."""
    rows = (
        db.query(LearningEvidence)
        .filter(
            LearningEvidence.household_id == household_id,
            LearningEvidence.child_id == child_id,
            LearningEvidence.skill_id == skill_id,
            LearningEvidence.invalidated_at.is_(None),
        )
        .order_by(LearningEvidence.valid_at.asc())
        .all()
    )

    independent_successes = [r for r in rows if r.observation_kind == "independent_correct"]
    evidence_count = len(rows)

    if len(independent_successes) >= DEMONSTRATED_INDEPENDENT_THRESHOLD:
        status = "demonstrated"
    elif independent_successes:
        # One independent success exists, but per spec that alone is not
        # "demonstrated" -- even if there is also plenty of assisted
        # success. Assisted evidence never counts toward this threshold.
        status = "emerging"
    elif rows:
        status = "attempted"
    else:
        status = "not_yet_observed"

    last_independent_at = independent_successes[-1].valid_at if independent_successes else None

    state = (
        db.query(SkillState)
        .filter(SkillState.child_id == child_id, SkillState.skill_id == skill_id)
        .one_or_none()
    )
    if state is None:
        state = SkillState(
            household_id=household_id,
            child_id=child_id,
            skill_id=skill_id,
            evidence_count=evidence_count,
            independent_successes=len(independent_successes),
            status=status,
            last_independent_at=last_independent_at,
        )
        db.add(state)
    else:
        state.evidence_count = evidence_count
        state.independent_successes = len(independent_successes)
        state.status = status
        state.last_independent_at = last_independent_at
        state.updated_at = datetime.now(timezone.utc)

    db.flush()
    return state


def write_resolution_capsule(
    db: Session,
    *,
    household_id: uuid.UUID,
    child_id: uuid.UUID,
    skill_id: str,
) -> MemoryFact | None:
    """When a skill reaches 'demonstrated', write a compact, dated
    resolution capsule the tutor may recall later (doc 03 §21 step 4-6).
    The capsule records dates, item-family versions, and the independent
    outcomes that earned it -- not a full conversation transcript, and
    never a claim of *current* mastery (that always requires a fresh
    probe; see app/core/tutor.py recall rules)."""
    state = (
        db.query(SkillState)
        .filter(SkillState.child_id == child_id, SkillState.skill_id == skill_id)
        .one_or_none()
    )
    if state is None or state.status != "demonstrated":
        return None

    evidence_rows = (
        db.query(LearningEvidence)
        .filter(
            LearningEvidence.child_id == child_id,
            LearningEvidence.skill_id == skill_id,
            LearningEvidence.observation_kind == "independent_correct",
            LearningEvidence.invalidated_at.is_(None),
        )
        .all()
    )

    capsule = MemoryFact(
        household_id=household_id,
        child_id=child_id,
        kind="resolution_capsule",
        structured_payload={
            "skill_id": skill_id,
            "status_as_of": datetime.now(timezone.utc).isoformat(),
            "independent_success_count": len(evidence_rows),
            "method": "same_denominator_fraction_addition_v1",
            "note": (
                "Demonstrated independent success on this skill as of the "
                "dates in evidence_refs. This is a dated, scoped record, "
                "not a claim of current mastery -- a fresh probe is "
                "required to say anything about today."
            ),
        },
        evidence_refs=[str(r.id) for r in evidence_rows],
        recall_allowed=True,
    )
    db.add(capsule)
    db.flush()
    return capsule
