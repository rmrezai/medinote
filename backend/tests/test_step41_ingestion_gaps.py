from app.mcif import analyze_source_text


def test_extracts_home_medications_exam_disposition_and_final_result():
    text = (
        "Home medications include losartan and apixaban. "
        "Focused exam: bibasilar crackles; no lower extremity edema. "
        "PT recommends home with home health. Patient ambulates 150 feet with rolling walker and supervision. "
        "Blood cultures final: no growth."
    )
    bundle = analyze_source_text(text)

    home = {(m.normalized_name, m.domain, m.status) for m in bundle.medications}
    assert ("losartan", "home", "active") in home
    assert ("apixaban", "home", "active") in home

    exam = {(f.fact_type, f.concept, f.value_text) for f in bundle.facts}
    assert any(ft == "exam" and concept == "lung_exam" and "crackles" in value.lower() for ft, concept, value in exam if value)
    assert any(ft == "exam" and concept == "edema" and "no lower extremity edema" in value.lower() for ft, concept, value in exam if value)

    assert bundle.dispositions
    dispo = bundle.dispositions[0]
    assert dispo.anticipated_destination.lower() == "home with home health"
    assert "150 feet" in (dispo.mobility_status or "")

    assert any(r.description.lower() == "blood cultures" and r.result_text.lower() == "no growth" for r in bundle.resolved_items)


def test_inpatient_need_and_therapy_oxygen_are_literal_only():
    text = (
        "Requires inpatient care for oxygen requirement and renal recovery. "
        "No supplemental oxygen required during therapy session."
    )
    bundle = analyze_source_text(text)
    assert bundle.dispositions
    dispo = bundle.dispositions[0]
    assert dispo.current_barriers == ["oxygen requirement", "renal recovery"]
    assert "no supplemental oxygen required" in (dispo.oxygen_need or "").lower()
