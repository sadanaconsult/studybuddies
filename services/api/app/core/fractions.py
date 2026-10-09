"""Exact-rational fraction verification for same-denominator addition.

AGENTS.md rule 5: exact rational arithmetic only. This module must never
import float-based comparison into the verification path. All values are
`fractions.Fraction`, constructed from integers, never from a float
literal or a float-producing operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import gcd


class MalformedFractionError(ValueError):
    """Raised when a submitted answer cannot be parsed as a/b with
    positive integers a, b (b != 0)."""


@dataclass(frozen=True)
class FractionItem:
    """A same-denominator addition item: a/d + b/d."""

    numerator_a: int
    numerator_b: int
    denominator: int

    def __post_init__(self) -> None:
        if self.denominator <= 0:
            raise ValueError("denominator must be a positive integer")
        if self.numerator_a < 0 or self.numerator_b < 0:
            raise ValueError("numerators must be non-negative integers")

    @property
    def exact_sum(self) -> Fraction:
        """The exact value of a/d + b/d, as a Fraction. Fraction's own
        arithmetic (not manual float division) performs the addition, so
        this is exact by construction."""
        return Fraction(self.numerator_a, self.denominator) + Fraction(
            self.numerator_b, self.denominator
        )

    @property
    def unsimplified_numerator(self) -> int:
        return self.numerator_a + self.numerator_b

    @property
    def unsimplified_denominator(self) -> int:
        return self.denominator

    @property
    def is_simplification_required(self) -> bool:
        """True when a/d + b/d does not already reduce to lowest terms,
        i.e. simplification is a genuine part of this item, not just a
        no-op check."""
        n, d = self.unsimplified_numerator, self.unsimplified_denominator
        divisor = gcd(n, d) if n else d
        return divisor != 1


@dataclass(frozen=True)
class VerificationResult:
    is_value_correct: bool
    is_form_correct: bool  # fully simplified, as the spec requires
    expected_value: Fraction
    expected_simplified: Fraction
    submitted_value: Fraction | None
    detail: str

    @property
    def is_fully_correct(self) -> bool:
        return self.is_value_correct and self.is_form_correct


def parse_fraction_answer(raw: str) -> Fraction:
    """Parse a learner-submitted answer of the form 'a/b', 'a / b', or a
    bare whole number 'a' (meaning a/1). Never falls back to float()."""
    text = raw.strip()
    if "/" in text:
        parts = text.split("/")
        if len(parts) != 2:
            raise MalformedFractionError(f"cannot parse fraction from {raw!r}")
        num_str, den_str = (p.strip() for p in parts)
        try:
            num, den = int(num_str), int(den_str)
        except ValueError as exc:
            raise MalformedFractionError(f"cannot parse fraction from {raw!r}") from exc
        if den == 0:
            raise MalformedFractionError("denominator cannot be zero")
        return Fraction(num, den)
    try:
        return Fraction(int(text), 1)
    except ValueError as exc:
        raise MalformedFractionError(f"cannot parse fraction from {raw!r}") from exc


def verify_answer(item: FractionItem, raw_answer: str) -> VerificationResult:
    """Exact verification against the item's true sum.

    Required form, per spec: the *simplified* fraction. A value-correct
    but unsimplified answer (e.g. 4/8 instead of 1/2) is value-correct but
    not form-correct, and `is_fully_correct` reflects that distinction so
    the evidence writer can record exactly what was demonstrated.
    """
    expected_value = item.exact_sum
    expected_simplified = Fraction(expected_value.numerator, expected_value.denominator)

    try:
        submitted = parse_fraction_answer(raw_answer)
    except MalformedFractionError:
        return VerificationResult(
            is_value_correct=False,
            is_form_correct=False,
            expected_value=expected_value,
            expected_simplified=expected_simplified,
            submitted_value=None,
            detail="unparsable_answer",
        )

    is_value_correct = submitted == expected_value
    # Fraction always normalizes on construction/arithmetic, so a
    # "simplified form" check compares the submitted numerator/denominator
    # as given (not re-simplified) against the already-lowest-terms
    # expected value.
    submitted_num, submitted_den = _extract_as_given(raw_answer, submitted)
    is_form_correct = (
        is_value_correct
        and submitted_num == expected_simplified.numerator
        and submitted_den == expected_simplified.denominator
    )

    if not is_value_correct:
        detail = "incorrect_value"
    elif not is_form_correct:
        detail = "correct_value_not_simplified"
    else:
        detail = "correct_and_simplified"

    return VerificationResult(
        is_value_correct=is_value_correct,
        is_form_correct=is_form_correct,
        expected_value=expected_value,
        expected_simplified=expected_simplified,
        submitted_value=submitted,
        detail=detail,
    )


def _extract_as_given(raw_answer: str, parsed: Fraction) -> tuple[int, int]:
    """Return numerator/denominator exactly as the learner wrote them
    (not Fraction's auto-simplified form), so we can tell a correct-but-
    unsimplified answer apart from a correctly simplified one."""
    text = raw_answer.strip()
    if "/" in text:
        num_str, den_str = (p.strip() for p in text.split("/"))
        return int(num_str), int(den_str)
    return parsed.numerator, parsed.denominator
