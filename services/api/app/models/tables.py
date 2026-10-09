"""SQLAlchemy models for the single-skill prototype.

Table names and key columns follow the spec (doc 02 §entity list) where
this prototype implements that entity; several spec columns (billing
refs, policy versioning, deletion_generation, row_version, etc.) are
omitted here because this prototype has no billing, no live retention
jobs, and no concurrent-write load to protect against -- AGENTS.md scope
note. Every child-scoped table carries both household_id and child_id
(rule 10), even where child_id alone would be unique, so every query can
be written scoped by both without a join.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Household(Base):
    __tablename__ = "household"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String(32), default="active")
    region: Mapped[str] = mapped_column(String(8), default="GB")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    children: Mapped[list["ChildProfile"]] = relationship(back_populates="household")
    guardians: Mapped[list["GuardianMembership"]] = relationship(back_populates="household")


class GuardianMembership(Base):
    """Minimal stub: demonstrates the household/child boundary without
    implementing real authentication (AGENTS.md: out of scope)."""

    __tablename__ = "guardian_membership"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("household.id"), nullable=False
    )
    adult_label: Mapped[str] = mapped_column(String(120))  # synthetic label only, never a real name
    role: Mapped[str] = mapped_column(String(32), default="guardian")
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    household: Mapped[Household] = relationship(back_populates="guardians")


class ChildProfile(Base):
    __tablename__ = "child_profile"
    __table_args__ = (UniqueConstraint("household_id", "id", name="uq_child_household"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    household_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("household.id"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(120))  # synthetic only
    age_band: Mapped[str] = mapped_column(String(16))
    school_year_label: Mapped[str] = mapped_column(String(16))
    jurisdiction: Mapped[str] = mapped_column(String(8), default="england")
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    household: Mapped[Household] = relationship(back_populates="children")


class TutoringSession(Base):
    __tablename__ = "tutoring_session"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    household_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(64), default="fraction_addition_same_denominator")
    state: Mapped[str] = mapped_column(String(32), default="orient")
    current_turn_sequence: Mapped[int] = mapped_column(Integer, default=0)
    baseline_item_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    transfer_item_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TutoringTurn(Base):
    """One turn of the conversational loop. `raw_model_output` is stored
    only for dev inspection; `gated_output` is what the gate approved and
    what is ever shown. If a turn was blocked, `gated_output` holds the
    safe static response instead (AGENTS.md rule 2)."""

    __tablename__ = "tutoring_turn"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tutoring_session.id"), nullable=False
    )
    household_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(16))  # "child" | "tutor"
    state_at_turn: Mapped[str] = mapped_column(String(32))
    turn_intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    child_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_model_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    gated_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempt"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    household_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tutoring_session.id"), nullable=False
    )
    item_family: Mapped[str] = mapped_column(String(16))  # "baseline" | "transfer"
    item_prompt: Mapped[str] = mapped_column(String(64))
    response_raw: Mapped[str] = mapped_column(String(64))
    assistance_level: Mapped[str] = mapped_column(String(16))  # "assisted" | "independent"
    is_value_correct: Mapped[bool] = mapped_column(Boolean)
    is_form_correct: Mapped[bool] = mapped_column(Boolean)
    result_detail: Mapped[str] = mapped_column(String(32))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LearningEvidence(Base):
    """Append-only. Never mutated to change assistance_level or result
    after the fact (AGENTS.md rule 4). Corrections create a new row and
    set `invalidated_at` on the old one; they do not edit it in place."""

    __tablename__ = "learning_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    household_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(64))
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_attempt.id"), nullable=False
    )
    observation_kind: Mapped[str] = mapped_column(String(32))  # "supported_correct" | "independent_correct" | "independent_incorrect" | ...
    assistance_level: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[str] = mapped_column(String(32), default="direct_observation")
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance_hash: Mapped[str] = mapped_column(String(64))


class SkillState(Base):
    """Rebuildable projection over learning_evidence. Never written to
    directly by the LLM; only recomputed by the evidence writer from
    `learning_evidence` rows (AGENTS.md rule 3)."""

    __tablename__ = "skill_state"
    __table_args__ = (UniqueConstraint("child_id", "skill_id", name="uq_skill_state_child_skill"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    household_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    skill_id: Mapped[str] = mapped_column(String(64))
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    independent_successes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="not_yet_observed")
    # not_yet_observed -> emerging -> demonstrated (never set to
    # "demonstrated" from assisted evidence alone -- see core/evidence.py)
    last_independent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MemoryFact(Base):
    """A compact, dated, evidence-bound fact the tutor may recall later.
    `recall_allowed` is flipped off immediately on correction/expiry
    rather than the row being silently reinterpreted."""

    __tablename__ = "memory_fact"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    household_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    child_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32))  # e.g. "resolution_capsule"
    structured_payload: Mapped[dict] = mapped_column(JSONB)
    evidence_refs: Mapped[list] = mapped_column(JSONB, default=list)
    recall_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
