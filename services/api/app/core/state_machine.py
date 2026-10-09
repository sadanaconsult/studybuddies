"""Session/turn state machine.

States, in order (doc 01 §21 informal workflow):
  orient -> elicit_attempt -> diagnose -> teach_or_hint -> learner_try
  -> feedback -> independent_transfer -> summarise

`teach_or_hint` <-> `learner_try` <-> `feedback` can loop (the hint
ladder: a wrong attempt returns to teach_or_hint with an escalated hint
level before trying again), but the machine never skips
`independent_transfer`, and `independent_transfer` is the only state in
which an attempt may be recorded with assistance_level="independent".
"""
from __future__ import annotations

from dataclasses import dataclass, field

VALID_TRANSITIONS: dict[str, set[str]] = {
    "orient": {"elicit_attempt"},
    "elicit_attempt": {"diagnose"},
    "diagnose": {"teach_or_hint", "independent_transfer"},
    # diagnose -> independent_transfer covers a child who elicits a
    # confident correct attempt with no apparent difficulty; spec allows
    # moving straight to the transfer check rather than force-feeding a
    # hint nobody needs.
    "teach_or_hint": {"learner_try"},
    "learner_try": {"feedback"},
    "feedback": {"teach_or_hint", "independent_transfer"},
    # feedback -> teach_or_hint is the hint-ladder loop on a wrong
    # assisted attempt; feedback -> independent_transfer follows a
    # correct assisted attempt.
    "independent_transfer": {"summarise", "independent_transfer"},
    # independent_transfer -> independent_transfer: spec note "one
    # success alone does not meet demonstrated status" means we may need
    # a second, later transfer item in a future session; within one
    # session we still only record one independent attempt per item.
    "summarise": set(),
}

MAX_HINT_LEVEL = 3


class InvalidTransitionError(ValueError):
    pass


@dataclass
class SessionState:
    state: str = "orient"
    hint_level: int = 0
    assisted_attempts: int = 0
    independent_attempts: int = 0
    history: list[str] = field(default_factory=lambda: ["orient"])

    def can_transition(self, to_state: str) -> bool:
        return to_state in VALID_TRANSITIONS.get(self.state, set())

    def transition(self, to_state: str) -> None:
        if not self.can_transition(to_state):
            raise InvalidTransitionError(
                f"cannot move from {self.state!r} to {to_state!r}; "
                f"valid next states: {sorted(VALID_TRANSITIONS.get(self.state, set()))}"
            )
        if to_state == "teach_or_hint" and self.state == "feedback":
            self.hint_level = min(self.hint_level + 1, MAX_HINT_LEVEL)
        self.state = to_state
        self.history.append(to_state)

    def record_assisted_attempt(self) -> None:
        if self.state != "feedback" and self.state != "learner_try":
            raise InvalidTransitionError(
                "assisted attempts are only recorded while in learner_try/feedback"
            )
        self.assisted_attempts += 1

    def record_independent_attempt(self) -> None:
        if self.state != "independent_transfer":
            raise InvalidTransitionError(
                "independent attempts are only recorded while in independent_transfer"
            )
        self.independent_attempts += 1

    @property
    def is_terminal(self) -> bool:
        return self.state == "summarise"


TURN_INTENTS = {
    "answer",
    "ask_question",
    "clarify",
    "shorten",
    "expand",
    "change_topic",
    "resume_thread",
    "request_hint",
    "request_example",
    "request_break",
    "stop_output",
    "correct_history",
    "report_concern",
}


def classify_intent_heuristic(child_input: str) -> str:
    """A deliberately simple, non-LLM heuristic classifier for the
    turn-intent taxonomy, used to decide control flow (e.g. whether to
    route to the safety gate) before any model call is made. This is not
    a replacement for the model's own understanding of the turn -- it is
    a fast pre-check so safety-relevant intents never depend on an LLM
    call succeeding."""
    text = child_input.strip().lower()
    if not text:
        return "answer"
    concern_markers = (
        "hurt myself", "kill myself", "scared of", "someone touched",
        "don't feel safe", "hate my life", "nobody loves me",
    )
    if any(marker in text for marker in concern_markers):
        return "report_concern"
    if text in {"stop", "stop it", "stop talking"}:
        return "stop_output"
    if text in {"break", "i need a break", "can i take a break"}:
        return "request_break"
    if "hint" in text:
        return "request_hint"
    if "example" in text or "show me" in text:
        return "request_example"
    if text.startswith("that's wrong") or "i meant" in text or "actually i" in text:
        return "correct_history"
    if "?" in text and not any(ch.isdigit() for ch in text):
        return "ask_question"
    return "answer"
