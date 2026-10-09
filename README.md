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

Open `/` for the home page: "Start a lesson" opens the child page (fraction bar + chat) for the demo child, and "Open parent view" shows the evidence. The demo child is created on first use. (`/docs` still lists the raw API.)
`/session/{session_id}?household_id=...&child_id=...` for the child page
(fraction bar + chat), and `/parent` for the parent view.

Without `ANTHROPIC_API_KEY` set, the tutor loop falls back to the safe
static response template rather than an unreviewed provider (AGENTS.md
rule 6) — useful for running the deterministic parts of the demo offline.

## Status

Prototype / pre-review. Educational validity, safeguarding behaviour, and
legal/privacy posture have **not** been signed off by a specialist; that
review is the next step, owned by the product owner, not this codebase.

## Deploying a demo on Render

`render.yaml` defines a free Postgres database and a web service.

1. Render dashboard → New → Blueprint → select this repo.
2. When prompted, set `ANTHROPIC_API_KEY` (from console.anthropic.com) and `DEMO_PASSWORD` (any shared password; the browser will ask for it, username can be anything).
3. After the first deploy, open the service's Shell and run `python scripts/seed.py` to create the one synthetic household/child and print their ids. Tables are also created automatically on startup.
4. `POST /sessions` via `/docs` with those ids, then open `/session/{id}?household_id=...&child_id=...`.

Set a monthly spend limit on the API key in the Console. Synthetic data only. The password is a demo gate, not real authentication.
