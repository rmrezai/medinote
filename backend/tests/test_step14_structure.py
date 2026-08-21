from fastapi.routing import APIRoute

from app.db.base import Base
from app.main import app
import app.models as models  # noqa: F401


def test_mcif_tables_registered():
    expected = {
        "clinical_facts",
        "clinical_problems",
        "problem_evidence",
        "medications",
        "medication_states",
        "lab_results",
        "vital_signs",
        "consultant_recommendations",
        "pending_items",
        "disposition_states",
        "contradictions",
    }
    assert expected.issubset(set(Base.metadata.tables))


def test_shared_state_route_exists():
    routes = {
        (route.path, tuple(sorted(route.methods or [])))
        for route in app.routes
        if isinstance(route, APIRoute)
    }
    assert ("/api/v1/encounters/{encounter_id}/state", ("GET",)) in routes


def test_medication_state_preserves_domains():
    table = Base.metadata.tables["medication_states"]
    assert "domain" in table.c
    assert "status" in table.c
    assert "physician_confirmed" in table.c
