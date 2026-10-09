"""Item-family generator: same-denominator fraction addition.

Scope: denominators 4-12 inclusive. Generates two related families per
spec doc 03 §9 (worked-example 3/8 + 1/8):

- `baseline`: items used during the taught/assisted phase (hints, worked
  examples may be shown).
- `transfer`: an "unseen" item with the same single-operation structure
  (same denominator, add two proper fractions) but different numerators/
  denominator, used for the independent-transfer check. Per spec, a
  switch to a different denominator structure is not an equivalent item
  -- transfer items stay within the same same-denominator-addition family.

Both families are produced from owned templates (no scraped worksheet
content), and both numerators are always < denominator (proper
fractions), with the resulting sum requiring simplification on a
configurable fraction of generated items so the "simplify your answer"
skill is actually exercised.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from math import gcd

from .fractions import FractionItem

MIN_DENOMINATOR = 4
MAX_DENOMINATOR = 12


@dataclass(frozen=True)
class GeneratedItem:
    item: FractionItem
    family: str  # "baseline" | "transfer"
    requires_simplification: bool
    prompt: str

    @property
    def denominator(self) -> int:
        return self.item.denominator


def _make_item(denominator: int, want_simplifiable: bool, rng: random.Random) -> FractionItem:
    """Build a proper-fraction a/d + b/d item for the given denominator,
    optionally constrained so the sum needs simplifying."""
    attempts = 0
    while True:
        attempts += 1
        a = rng.randint(1, denominator - 1)
        b = rng.randint(1, denominator - 1)
        if a + b >= denominator * 2:
            continue  # keep sums sane; proper fractions already bound this
        item = FractionItem(numerator_a=a, numerator_b=b, denominator=denominator)
        if want_simplifiable == item.is_simplification_required:
            return item
        if attempts > 200:
            # Fall back to whatever we have rather than loop forever on an
            # unsatisfiable denominator (e.g. prime denominators where few
            # sums simplify) -- deterministic, not a silent float shortcut.
            return item


def generate_baseline_item(
    denominator: int | None = None, *, seed: int | None = None
) -> GeneratedItem:
    rng = random.Random(seed)
    d = denominator or rng.randint(MIN_DENOMINATOR, MAX_DENOMINATOR)
    if not (MIN_DENOMINATOR <= d <= MAX_DENOMINATOR):
        raise ValueError(f"denominator must be between {MIN_DENOMINATOR} and {MAX_DENOMINATOR}")
    item = _make_item(d, want_simplifiable=False, rng=rng)
    return GeneratedItem(
        item=item,
        family="baseline",
        requires_simplification=item.is_simplification_required,
        prompt=f"{item.numerator_a}/{item.denominator} + {item.numerator_b}/{item.denominator}",
    )


def generate_transfer_item(
    baseline: GeneratedItem, *, seed: int | None = None
) -> GeneratedItem:
    """Generate an unseen item in the same family (same-denominator
    addition) as `baseline`, but with different numerator/denominator
    values, and requiring simplification -- this is the independent-
    transfer check, so it should not be identical in form to a worked
    example the learner has already seen."""
    rng = random.Random(seed)
    candidates = [d for d in range(MIN_DENOMINATOR, MAX_DENOMINATOR + 1) if d != baseline.denominator]
    d = rng.choice(candidates) if candidates else baseline.denominator
    item = _make_item(d, want_simplifiable=True, rng=rng)
    while (
        item.numerator_a == baseline.item.numerator_a
        and item.numerator_b == baseline.item.numerator_b
        and item.denominator == baseline.denominator
    ):
        item = _make_item(d, want_simplifiable=True, rng=rng)
    return GeneratedItem(
        item=item,
        family="transfer",
        requires_simplification=item.is_simplification_required,
        prompt=f"{item.numerator_a}/{item.denominator} + {item.numerator_b}/{item.denominator}",
    )


def canonical_worked_example() -> tuple[GeneratedItem, GeneratedItem]:
    """The spec's own canonical worked example (doc 01 §21, doc 03 §9,
    doc 09 M7 contract): baseline 3/8 + 1/8, transfer 2/9 + 4/9."""
    baseline = GeneratedItem(
        item=FractionItem(numerator_a=3, numerator_b=1, denominator=8),
        family="baseline",
        requires_simplification=True,  # 4/8 -> 1/2
        prompt="3/8 + 1/8",
    )
    transfer = GeneratedItem(
        item=FractionItem(numerator_a=2, numerator_b=4, denominator=9),
        family="transfer",
        requires_simplification=True,
        prompt="2/9 + 4/9",
    )
    return baseline, transfer
