"""LLM-backed tutoring text loop, behind the safety gate.

AGENTS.md rules 2, 3, 6: the model generates candidate text only; it
never writes learner state, every candidate passes the gate, and when no
provider is configured (or SAFE_MODE_ONLY is set) we use a safe static
template rather than falling back to a different/unreviewed provider.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import settings
from .items import GeneratedItem
from .safety_gate import (
    SAFE_PROVIDER_UNAVAILABLE_RESPONSE,
    GateContext,
    GateDecision,
    run_safety_gate,
)

SYSTEM_PROMPT = """You are a patient, encouraging maths tutor for a primary-school child \
in England, teaching same-denominator fraction addition only.

Hard rules you must follow:
- Use a hint ladder: give a small nudge first, then a bigger hint, then a \
worked example -- never jump straight to the final numeric answer unless \
the child is in the "teach_or_hint" state and has already had at least one \
hint.
- When the current state is "independent_transfer", you must NOT reveal, \
confirm, or hint at the numeric answer to the current item under any \
circumstance, even if asked directly. Instead, encourage the child to try \
it themselves and explain their reasoning.
- Keep language simple, warm, and age-appropriate. Short sentences.
- If the child expresses something that sounds like a safety or wellbeing \
concern unrelated to maths, do not try to help with it yourself -- say you \
are not able to help with that and that it is worth telling a trusted adult.
- Never claim the child has "mastered" or "fully understood" the topic; \
that judgement belongs to the verifier and evidence system, not to you.
"""


@dataclass
class TutorTurnResult:
    raw_model_output: str
    gate_decision: GateDecision
    used_llm: bool


def _provider_available() -> bool:
    return bool(settings.anthropic_api_key) and not settings.safe_mode_only


def _call_llm(*, state: str, child_input: str, item: GeneratedItem, hint_level: int) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    user_prompt = (
        f"Current state: {state}\n"
        f"Current item: {item.prompt}\n"
        f"Hint level so far: {hint_level}\n"
        f"Child said: {child_input!r}\n\n"
        "Respond with only what you would say to the child next, in 1-3 short sentences."
    )
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    chunks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return "\n".join(chunks).strip()


def generate_tutor_turn(
    *, state: str, child_input: str, item: GeneratedItem, hint_level: int
) -> TutorTurnResult:
    protected = (item.item.exact_sum.__str__(),) if state == "independent_transfer" else ()
    gate_context = GateContext(session_state=state, protected_answer_strings=protected)

    if not _provider_available():
        a, b, d = item.item.numerator_a, item.item.numerator_b, item.denominator
        text = SAFE_PROVIDER_UNAVAILABLE_RESPONSE.format(a=a, b=b, d=d, sum_num=a + b)
        if state == "independent_transfer":
            text = (
                "Let's see what you think first -- try the problem on your "
                "own and tell me your answer."
            )
        decision = run_safety_gate(text, gate_context)
        return TutorTurnResult(raw_model_output=text, gate_decision=decision, used_llm=False)

    raw_output = _call_llm(state=state, child_input=child_input, item=item, hint_level=hint_level)
    decision = run_safety_gate(raw_output, gate_context)
    return TutorTurnResult(raw_model_output=raw_output, gate_decision=decision, used_llm=True)
