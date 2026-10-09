import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://tutorbuddy@localhost:5432/tutorbuddy")
os.environ["ANTHROPIC_API_KEY"] = ""  # tests never call a live provider

import pytest  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.models.tables import ChildProfile, Household  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def family(db):
    """Two synthetic households, one child each, for isolation tests."""
    out = []
    for n in ("A", "B"):
        h = Household()
        db.add(h)
        db.flush()
        c = ChildProfile(household_id=h.id, display_name=f"Synthetic Child {n}", age_band="9-10", school_year_label="Year 5")
        db.add(c)
        db.flush()
        out.append((h, c))
    db.commit()
    return out
