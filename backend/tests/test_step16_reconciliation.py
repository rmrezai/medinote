from datetime import datetime, timezone

from fastapi.routing import APIRoute
from sqlalchemy.dialects import postgresql

from app.main import app
from app.mcif.reconciliation import TemporalItem, choose_current, numeric_trend, oxygen_trend
from app.models import ClinicalTrajectory


def test_reconcile_route_exists():
    routes = {
        (route.path, tuple(sorted(route.methods or [])))
        for route in app.routes
        if isinstance(route, APIRoute)
    }
    assert ("/api/v1/encounters/{encounter_id}/reconcile", ("POST",)) in routes


def test_newer_timestamp_wins_and_authority_breaks_equal_time_tie():
    t1 = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 20, 9, tzinfo=timezone.utc)
    items = [
        TemporalItem("a", "oxygen", "4L", t1, "objective"),
        TemporalItem("b", "oxygen", "2L", t2, "clinician_documented"),
    ]
    assert choose_current(items).identifier == "b"

    equal_time = [
        TemporalItem("a", "creatinine", "1.5", t2, "clinician_documented"),
        TemporalItem("b", "creatinine", "1.4", t2, "objective"),
    ]
    assert choose_current(equal_time).identifier == "b"


def test_trajectory_describes_direction_without_diagnostic_inference():
    t1 = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    assert numeric_trend([(t1, 2.4), (t2, 1.6)]) == "falling"
    assert oxygen_trend([
        (t1, "nasal_cannula", 4.0, None),
        (t2, "nasal_cannula", 2.0, None),
    ]) == "decreasing_support"
    assert oxygen_trend([
        (t1, "nasal_cannula", 2.0, None),
        (t2, "room_air", None, "room_air"),
    ]) == "decreasing_support"


def test_trajectory_table_compiles_for_postgresql():
    ddl = str(ClinicalTrajectory.__table__.compile(dialect=postgresql.dialect()))
    assert ClinicalTrajectory.__tablename__ == "clinical_trajectories"
    assert "encounter_id" in ClinicalTrajectory.__table__.columns
