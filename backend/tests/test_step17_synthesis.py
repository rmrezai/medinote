from fastapi.routing import APIRoute

from app.main import app
from app.mcif.synthesis import acuity_rank, synthesize_problem_status


def test_synthesis_route_exists():
    routes = {
        (route.path, tuple(sorted(route.methods or [])))
        for route in app.routes
        if isinstance(route, APIRoute)
    }
    assert ("/api/v1/encounters/{encounter_id}/synthesize", ("POST",)) in routes


def test_aki_uses_creatinine_direction_only_when_problem_exists():
    result = synthesize_problem_status("acute_kidney_injury", {("lab", "creatinine"): "falling"})
    assert result.status == "improving"
    assert result.trajectory_basis == "creatinine_falling"

    result = synthesize_problem_status("acute_kidney_injury", {("lab", "creatinine"): "rising"})
    assert result.status == "worsening"


def test_respiratory_failure_uses_support_direction_not_oxygen_alone_to_create_diagnosis():
    result = synthesize_problem_status(
        "acute_hypoxemic_respiratory_failure",
        {("respiratory_support", "oxygen_support"): "decreasing_support"},
    )
    assert result.status == "improving"

    # Pneumonia does not inherit a respiratory-failure trajectory in v0.1.
    pneumonia = synthesize_problem_status(
        "pneumonia",
        {("respiratory_support", "oxygen_support"): "decreasing_support"},
    )
    assert pneumonia.status == "active"
    assert pneumonia.trajectory_basis is None


def test_default_acuity_priority_is_status_sensitive_but_conservative():
    assert acuity_rank("acute_hypoxemic_respiratory_failure", "worsening") < acuity_rank("acute_kidney_injury", "worsening")
    assert acuity_rank("acute_kidney_injury", "worsening") < acuity_rank("acute_kidney_injury", "improving")
    assert acuity_rank("unknown_problem", "active") == 500
