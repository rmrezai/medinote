from fastapi.routing import APIRoute

from app.main import app
from app.mcif import analyze_source_text


def test_analyze_route_exists():
    routes = {
        (route.path, tuple(sorted(route.methods or [])))
        for route in app.routes
        if isinstance(route, APIRoute)
    }
    assert ("/api/v1/encounters/{encounter_id}/analyze", ("POST",)) in routes


def test_conservative_extraction_preserves_uncertainty_and_states():
    text = (
        "Possible pneumonia. AKI with Cr 2.4. Creatinine 1.6 today. "
        "Patient is currently on 2 L NC. Losartan remains held. "
        "Nephrology recommends continue holding losartan until renal function stabilizes. "
        "Blood cultures remain pending."
    )
    bundle = analyze_source_text(text)

    problems = {(p.normalized_name, p.certainty) for p in bundle.problems}
    assert ("pneumonia", "possible") in problems
    assert ("acute_kidney_injury", "confirmed") in problems

    labs = {(x.test_name, x.value_numeric) for x in bundle.labs}
    assert ("creatinine", 2.4) in labs
    assert ("creatinine", 1.6) in labs

    oxygen = [x for x in bundle.vitals if x.oxygen_flow_lpm == 2.0]
    assert oxygen

    meds = {(m.normalized_name, m.status) for m in bundle.medications}
    assert ("losartan remains", "held") not in meds
    assert any(m.status == "held" and "losartan" in m.normalized_name for m in bundle.medications)

    assert any(c.service == "Nephrology" for c in bundle.consultants)
    assert any("cultures" in x.description.lower() for x in bundle.pending_items)


def test_does_not_infer_diagnosis_from_risk_only():
    bundle = analyze_source_text("Patient has dysphagia and aspiration risk. No pneumonia documented.")
    # The literal word pneumonia is present in a negated statement, which the deterministic MVP cannot yet safely interpret.
    # For Step 15, we explicitly avoid testing negation as a validated clinical diagnosis feature; that arrives in reconciliation.
    assert all(p.normalized_name != "aspiration_pneumonia" for p in bundle.problems)
