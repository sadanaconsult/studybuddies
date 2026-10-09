"""Output validation / safety gate.

AGENTS.md rule 2: every LLM-generated tutoring utterance passes through
this gate before it is stored as a turn or returned from an API response.
Rule 9: a safeguarding-shaped input gets a fixed, non-generative safe
response and ends generative tutoring for that turn -- the gate enforces
that regardless of what the model would have said.
"""
from __future__ import annotations

from dataclasses import dataclass

SAFE_CONCERN_RESPONSE = (
    "Thank you for telling me. This sounds important, and I think it's "
    "best to talk to a trusted adult about it -- like a parent, carer, or "
    "teacher -- as soon as you can. I'm not able to help with this kind "
    "of thing myself. Would you like to pause our lesson for now?"
)

SAFE_PROVIDER_UNAVAILABLE_RESPONSE = (
    "I can't generate a tailored explanation right now, so let's use a "
    "worked example instead: to add {a}/{d} + {b}/{d}, add the "
    "numerators and keep the denominator the same, then simplify if you "
    "can. {a}/{d} + {b}/{d} = {sum_num}/{d}."
)

# Tutor text must never contain the final answer to the *independent*
# transfer item before the child has submitted their own attempt. This
# is a crude lexical guard appropriate to a prototype -- a production
# gate would need a structured check tied to the actual item, not string
# matching -- but it demonstrates the principle: the gate holds the
# answer, the model does not get to leak it.
@dataclass
class GateContext:
    session_state: str
    protected_answer_strings: tuple[str, ...] = ()
    turn_intent: str | None = None


@dataclass
class GateDecision:
    outcome: str  # "approved" | "blocked_concern" | "blocked_leak" | "blocked_other"
    output_text: str


def run_safety_gate(raw_model_output: str, context: GateContext) -> GateDecision:
    if context.turn_intent == "report_concern":
        return GateDecision(outcome="blocked_concern", output_text=SAFE_CONCERN_RESPONSE)

    if context.session_state == "independent_transfer":
        lowered = raw_model_output.lower()
        for protected in context.protected_answer_strings:
            if protected and protected.lower() in lowered:
                return GateDecision(
                    outcome="blocked_leak",
                    output_text=(
                        "Let's see what you think first -- try the problem "
                        "on your own and tell me your answer."
                    ),
                )

    if not raw_model_output.strip():
        return GateDecision(
            outcome="blocked_other",
            output_text="Let's try that again -- can you tell me what you're thinking so far?",
        )

    return GateDecision(outcome="approved", output_text=raw_model_output)
