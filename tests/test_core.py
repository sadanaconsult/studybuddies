import ast
import uuid
from pathlib import Path

import pytest

from app.core.fractions import FractionItem, verify_answer
from app.core.items import canonical_worked_example, generate_baseline_item, generate_transfer_item
from app.core.safety_gate import GateContext, run_safety_gate
from app.core.state_machine import InvalidTransitionError, SessionState, classify_intent_heuristic


def test_canonical_examples():
    base, transfer = canonical_worked_example()
    assert str(base.item.exact_sum) == "1/2"
    assert str(transfer.item.exact_sum) == "2/3"


def test_verifier_distinguishes_value_and_form():
    item = FractionItem(3, 1, 8)
    assert verify_answer(item, "1/2").is_fully_correct
    r = verify_answer(item, "4/8")
    assert r.is_value_correct and not r.is_form_correct
    assert not verify_answer(item, "4/16").is_fully_correct or False
    assert verify_answer(item, "banana").detail == "unparsable_answer"
    assert not verify_answer(item, "1/0").is_value_correct


def test_verifier_has_no_float_use():
    src = Path(__file__).resolve().parents[1] / "services/api/app/core/fractions.py"
    tree = ast.parse(src.read_text())
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "float" not in names and "Decimal" not in names


def test_generator_ranges_and_transfer_differs():
    for seed in range(50):
        b = generate_baseline_item(seed=seed)
        assert 4 <= b.denominator <= 12
        assert b.item.numerator_a < b.denominator and b.item.numerator_b < b.denominator
        t = generate_transfer_item(b, seed=seed)
        assert (t.item.numerator_a, t.item.numerator_b, t.denominator) != (
            b.item.numerator_a, b.item.numerator_b, b.denominator)


def test_state_machine_rules():
    m = SessionState()
    with pytest.raises(InvalidTransitionError):
        m.transition("independent_transfer")
    for s in ("elicit_attempt", "diagnose", "teach_or_hint", "learner_try", "feedback"):
        m.transition(s)
    m.transition("teach_or_hint")
    assert m.hint_level == 1
    with pytest.raises(InvalidTransitionError):
        m.record_independent_attempt()


def test_intent_concern():
    assert classify_intent_heuristic("I want to hurt myself") == "report_concern"


def test_gate_blocks_leak_and_concern():
    ctx = GateContext(session_state="independent_transfer", protected_answer_strings=("2/3",))
    assert run_safety_gate("The answer is 2/3", ctx).outcome == "blocked_leak"
    assert run_safety_gate("Try it yourself", ctx).outcome == "approved"
    assert run_safety_gate("x", GateContext("orient", turn_intent="report_concern")).outcome == "blocked_concern"
