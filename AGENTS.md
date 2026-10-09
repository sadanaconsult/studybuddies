# AGENTS.md — Hard Rules for This Repository

This file binds every contributor and every automated agent (including AI
coding assistants) working in this repository. These rules exist because
this prototype is a scoped slice of a product intended for children. They
are not style preferences; a change that violates one of them must not be
merged, regardless of how it is framed or who asks for it.

## Scope of this prototype

This repository implements **one** teaching skill end-to-end: same-
denominator fraction addition (denominators 4–12), for a single synthetic
child persona, as a reviewable proof of the Tutor Buddy architecture
described in the nine specification documents this build is derived from.
It is explicitly **not** the Years 4–6 multi-subject platform. Anything
outside this skill's scope (other subjects, other skills, billing, real
guardian/child authentication, safeguarding escalation, voice) is either
stubbed or deliberately absent.

## Hard rules

1. **Synthetic data only.** No real child's name, work, voice, image, or
   identifying detail may be entered, imported, or referenced anywhere in
   this repository — code, fixtures, tests, docs, or commit history. All
   households, children, and transcripts used anywhere in this repo are
   fabricated for development purposes. There is no "approved live data"
   switch in this prototype; moving to real data is a decision this repo
   does not make and a gate this repo does not open.

2. **No raw model output reaches a simulated child unfiltered.** Every
   LLM-generated tutoring utterance must pass through the output
   validation/safety gate (`app/core/safety_gate.py`) before it is stored
   as a turn or returned from an API response. A call site that bypasses
   the gate is a bug, not a shortcut.

3. **The model never writes learner state directly.** `learning_evidence`,
   `skill_state`, and `memory_fact` rows are written only by the
   evidence/memory writer (`app/core/evidence.py`), which applies the
   admissibility rules below. The LLM proposes; it does not persist. No
   LLM call result is written straight into these tables.

4. **No evidence upgrades.** An observation recorded as `assisted` can
   never be silently reclassified as `independent`, and partial credit
   cannot be promoted to full mastery evidence after the fact. A new,
   genuinely independent attempt is a new row, not an edit to an old one.
   `learning_evidence` rows are append-only; corrections invalidate
   (`invalidated_at`) rather than mutate.

5. **Exact rational arithmetic only for maths verification.** The fraction
   verifier (`app/core/fractions.py`) must use Python's `fractions.Fraction`
   (or equivalent exact rational representation) for every comparison. No
   `float`, `Decimal` rounding, or approximate comparison may enter the
   verification path for mathematical correctness or simplification
   checks.

6. **No unsafe fallback provider.** If the LLM provider is unavailable, the
   system degrades to a safe static response (or pauses the session) — it
   never falls back to an unreviewed, unvalidated, or lower-safety
   provider to keep a conversation going.

7. **No unreviewed content publication.** Revision artifacts (saved notes,
   worked examples) are marked `pending` until explicitly reviewed in this
   prototype's workflow; nothing is presented to the simulated parent view
   as validated/published without that status being true in the data.

8. **No test-skipping.** `pytest` must run with no `skip`/`xfail` markers
   added to make a red test disappear. A failing test is fixed or the code
   under test is fixed; it is not silenced.

9. **Safeguarding concerns get a safe static response, nothing more.**
   This prototype does not implement escalation, triage, or contact with
   any real authority. Any input pattern resembling a safeguarding concern
   routes to a fixed, non-generative safe response and ends generative
   tutoring for that turn. Building this out further is explicitly out of
   scope and is the user's responsibility, not this codebase's.

10. **Household/child isolation is load-bearing, not cosmetic.** Every
    query that touches `child_profile`, `tutoring_session`,
    `assessment_attempt`, `learning_evidence`, `skill_state`, or
    `memory_fact` must be scoped by `household_id` and `child_id` at the
    repository/query layer. A code path that fetches child-scoped data
    without both identifiers is a bug.

## Explicitly out of scope for this build

- Real payment/billing (Stripe or otherwise).
- Real guardian/child authentication (a minimal stub session exists only
  to demonstrate the household/child boundary).
- Safeguarding escalation beyond the fixed safe response in rule 9.
- Voice input/output (named stretch goal, sequenced last, not started).
- Any subject or skill other than same-denominator fraction addition.

## Provenance

This repository is derived from nine specification documents (Tutor Buddy
v1.3 + addendum) supplied by the product owner, who holds responsibility
for educational review, safeguarding sign-off, legal/privacy sign-off, and
vendor contracting. This codebase does not claim any of those approvals.
