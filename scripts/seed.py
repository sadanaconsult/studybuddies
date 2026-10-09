"""Seed ONE synthetic household and child (AGENTS.md rule 1)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.models.tables import ChildProfile, GuardianMembership, Household  # noqa: E402

Base.metadata.create_all(engine)
with SessionLocal() as db:
    h = Household()
    db.add(h)
    db.flush()
    db.add(GuardianMembership(household_id=h.id, adult_label="Synthetic Guardian A"))
    c = ChildProfile(household_id=h.id, display_name="Synthetic Child A", age_band="9-10", school_year_label="Year 5")
    db.add(c)
    db.commit()
    print(f"household_id={h.id}\nchild_id={c.id}")
