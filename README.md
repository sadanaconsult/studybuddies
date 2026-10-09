# Tutor Buddy — Single-Skill Prototype (Same-Denominator Fraction Addition)

This is a **scoped, reviewable prototype**, not the full Tutor Buddy
product described in the nine specification documents it is derived from.
It implements one teaching skill end-to-end — same-denominator fraction
addition for denominators 4–12 — so the architecture, evidence model, and
safety gate can be reviewed before further build-out.

Read **`AGENTS.md` first**. It lists the hard rules this codebase follows
(synthetic data only, no evidence upgrades, exact-rational verification,
etc.) and what is explicitly out of scope.

## What's here

- `services/api` — FastAPI backend: household/child models, a tutoring
  session state machine, an exact-rational fraction verifier, a same-
  denominator item generator, an evidence/memory writer, an LLM-backed
  tutoring text loop behind a safety/validation gate, a fraction-bar
  visual, and a parent view.
- `tests/` — pytest suite for the verifier, generator, state machine, and
  evidence writer's no-upgrade rule.
- `scripts/` — seed script for synthetic households/children and a dev
  bootstrap.

## What this is not

- Not the Years 4–6 multi-subject platform.
- No real payment/billing, no real guardian/child auth, no safeguarding
  escalation beyond a fixed safe response, no voice (voice is a named
  stretch goal and is not implemented here).
- No real child data anywhere, ever, in this repository.

## Running it locally

```bash
cp .env.example .env            # set ANTHROPIC_API_KEY if you want live LLM turns
docker compose up -d db         # Postgres
cd services/api
pip install -r requirements.txt
python ../../scripts/seed.py    # creates tables + one synthetic household/child; prints ids
uvicorn app.main:app --reload --port 8000
# tests (needs the db above): cd ../.. && python -m pytest
```

Then `POST /sessions` (see `/docs`) with the seeded ids, open
`/session/{session_id}?household_id=...&child_id=...` for the child page
(fraction bar + chat), and `/parent` for the parent view.

Without `ANTHROPIC_API_KEY` set, the tutor loop falls back to the safe
static response template rather than an unreviewed provider (AGENTS.md
rule 6) — useful for running the deterministic parts of the demo offline.

## Status

Prototype / pre-review. Educational validity, safeguarding behaviour, and
legal/privacy posture have **not** been signed off by a specialist; that
review is the next step, owned by the product owner, not this codebase.
