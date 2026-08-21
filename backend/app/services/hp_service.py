from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.state_version_service import document_state_status
from app.models import Encounter, ClinicalDocument, ClinicalFact, DocumentSection, Medication, MedicationState
from app.services.overview_service import build_patient_overview
from app.services.progress_service import _problem_evidence, _section_dict, _evidence_phrase

ALLOWED_VARIANTS = {"standard", "admission", "short", "complex", "updated", "consult_style"}
GENERATOR_VERSION = "hp-deterministic-v0.1"


def _hpi(overview: dict, variant: str) -> str:
    problems = overview.get("problems", [])
    if problems:
        lead = problems[0]
        certainty = lead.get("certainty")
        qualifier = f" ({certainty})" if certainty and certainty not in {"confirmed", "unclear"} else ""
        first = f"Admitted for {lead['name']}{qualifier}"
        if len(problems) > 1:
            first += f" with {len(problems) - 1} additional active structured problem(s)"
        first += "."
    else:
        first = "Admission diagnosis has not yet been established in the structured patient state."

    counts = overview.get("attention_counts", {})
    details = []
    if counts.get("unresolved_medications"):
        details.append(f"{counts['unresolved_medications']} unresolved medication decision(s)")
    if counts.get("pending_items"):
        details.append(f"{counts['pending_items']} pending item(s)")
    if counts.get("unresolved_contradictions"):
        details.append(f"{counts['unresolved_contradictions']} unresolved contradiction(s)")
    if details:
        second = "Current admission review needs include " + ", ".join(details) + "."
    else:
        second = "No structured medication, pending-item, or contradiction review flags are currently open."
    return f"{first} {second}"


def _objective_snapshot(overview: dict) -> str:
    bits = []
    for lab in overview.get("labs", [])[:6]:
        val = lab.get("value")
        if val is None:
            continue
        unit = f" {lab['units']}" if lab.get("units") else ""
        trend = f" ({lab['trajectory']})" if lab.get("trajectory") else ""
        bits.append(f"{lab['test_name']} {val}{unit}{trend}")
    return "Objective data: " + ("; ".join(bits) + "." if bits else "no structured current laboratory snapshot is available.")


def _relevant_history(db: Session, encounter_id: UUID) -> str:
    facts = list(db.scalars(select(ClinicalFact).where(
        ClinicalFact.encounter_id == encounter_id,
        ClinicalFact.fact_state == "historical",
    )))
    concepts = []
    for fact in facts:
        c = (fact.concept or "").replace("_", " ")
        if c and c not in concepts:
            concepts.append(c)
    if not concepts:
        return "Relevant past medical history: no structured historical condition is available for safe inclusion."
    return "Relevant past medical history: " + "; ".join(concepts[:8]) + "."


def _focused_exam(db: Session, encounter_id: UUID) -> str:
    facts = list(db.scalars(select(ClinicalFact).where(
        ClinicalFact.encounter_id == encounter_id,
        ClinicalFact.is_current == True,  # noqa: E712
        ClinicalFact.fact_type.in_(["exam", "physical_exam"]),
    )))
    findings = []
    for fact in facts:
        value = fact.value_text or (str(fact.value_numeric) if fact.value_numeric is not None else None)
        if value:
            findings.append(f"{fact.concept.replace('_', ' ')}: {value}")
        else:
            findings.append(fact.concept.replace("_", " "))
    if not findings:
        return "Focused physical exam: no current structured exam findings are available; physician examination required."
    return "Focused physical exam: " + "; ".join(findings[:10]) + "."


def _med_reconciliation(db: Session, encounter_id: UUID) -> str:
    meds = list(db.scalars(select(Medication).where(Medication.encounter_id == encounter_id)))
    lines = []
    for med in meds:
        states = list(db.scalars(select(MedicationState).where(MedicationState.medication_id == med.id, MedicationState.is_current == True)))  # noqa: E712
        hospital = next((s for s in states if s.domain == "hospital"), None)
        home = next((s for s in states if s.domain == "home"), None)
        if hospital:
            lines.append(f"{med.display_name or med.normalized_name}: hospital state {hospital.status}" + (f" ({hospital.reason})" if hospital.reason else ""))
        elif home:
            lines.append(f"{med.display_name or med.normalized_name}: home state {home.status}; inpatient state not established")
    if not lines:
        return "Medication reconciliation: no structured medication states are currently available."
    return "Medication reconciliation:\n- " + "\n- ".join(lines[:12])


def _disposition(overview: dict) -> str:
    d = overview.get("disposition")
    if not d:
        return "Disposition / inpatient need: no structured disposition state is currently available; physician review required."
    pieces = []
    if d.get("anticipated_destination"):
        pieces.append(f"anticipated destination {d['anticipated_destination']}")
    if d.get("current_barriers"):
        pieces.append(f"barriers {d['current_barriers']}")
    if d.get("oxygen_need"):
        pieces.append(f"oxygen need {d['oxygen_need']}")
    if d.get("pt_recommendation"):
        pieces.append(f"PT {d['pt_recommendation']}")
    if not pieces:
        return "Disposition / inpatient need: structured disposition record present without a documented destination or barrier summary."
    return "Disposition / inpatient need: " + "; ".join(pieces) + "."


def _problem_text(problem: dict) -> str:
    title = problem["name"]
    certainty = problem.get("certainty")
    if certainty and certainty not in {"confirmed", "unclear"}:
        title += f" ({certainty})"
    if problem.get("status") not in {None, "active", "new"}:
        title += f" - {problem['status']}"
    ev = _evidence_phrase(problem.get("evidence", []))
    if ev:
        return f"{title}\nObjective evidence: {ev}.\nPlan: physician treatment plan required/confirm current documented plan."
    return f"{title}\nNo structured supporting evidence is currently linked; physician review required.\nPlan: physician treatment plan required."


def _review_reasons(db: Session, encounter_id: UUID, overview: dict) -> list[str]:
    reasons = []
    if overview.get("contradictions"):
        reasons.append(f"{len(overview['contradictions'])} unresolved contradiction(s) remain in the encounter state.")
    if overview.get("attention_counts", {}).get("unresolved_medications"):
        reasons.append(f"{overview['attention_counts']['unresolved_medications']} medication decision(s) remain unresolved.")
    if not list(db.scalars(select(ClinicalFact).where(ClinicalFact.encounter_id == encounter_id, ClinicalFact.fact_type.in_(["exam", "physical_exam"])))):
        reasons.append("No structured physical examination findings are available.")
    for problem in overview.get("problems", []):
        if not problem.get("evidence"):
            reasons.append(f'Problem "{problem["name"]}" has no linked structured evidence.')
    return reasons


def generate_hp_document(db: Session, encounter_id: UUID, variant: str = "admission", generated_by: UUID | None = None) -> dict:
    variant = variant.lower().strip()
    if variant not in ALLOWED_VARIANTS:
        raise ValueError(f"Unsupported H&P variant: {variant}")
    overview = build_patient_overview(db, encounter_id)
    doc = ClinicalDocument(encounter_id=encounter_id, document_type="hp", variant=variant, status="draft", generator_version=GENERATOR_VERSION, generated_by=generated_by, generated_state_version=int(db.get(Encounter, encounter_id).clinical_state_version or 1))
    db.add(doc); db.flush()

    sections = []
    order = 10
    def add(section_type: str, key: str, text: str):
        nonlocal order
        s = DocumentSection(document_id=doc.id, section_type=section_type, section_key=key, sort_order=order, generated_content=text)
        db.add(s); db.flush(); sections.append(s); order += 10

    add("hpi", "hpi", _hpi(overview, variant))
    if variant not in {"short"}:
        add("relevant_history", "relevant_history", _relevant_history(db, encounter_id))
        add("objective_data", "objective_data", _objective_snapshot(overview))

    problems = overview.get("problems", [])
    if variant == "short":
        problems = problems[:4]
    elif variant == "standard":
        problems = problems[:8]
    for problem in problems:
        add("assessment_plan_problem", str(problem["id"]), _problem_text(problem))

    add("focused_exam", "focused_exam", _focused_exam(db, encounter_id))
    add("medication_reconciliation", "medication_reconciliation", _med_reconciliation(db, encounter_id))
    add("disposition", "disposition", _disposition(overview))

    db.commit(); db.refresh(doc)
    reasons = _review_reasons(db, encounter_id, overview)
    return {
        "document_id": doc.id, "encounter_id": doc.encounter_id, "document_type": doc.document_type,
        "variant": doc.variant, "status": doc.status, "generator_version": doc.generator_version,
        "generated_at": doc.generated_at, "approved_at": doc.approved_at,
        **document_state_status(db, doc),
        "sections": [_section_dict(db, s) for s in sections], "review_required": bool(reasons), "review_reasons": reasons,
    }


def get_hp_document(db: Session, document_id: UUID) -> dict:
    doc = db.get(ClinicalDocument, document_id)
    if not doc or doc.document_type != "hp":
        raise LookupError("H&P document not found")
    overview = build_patient_overview(db, doc.encounter_id)
    sections = list(db.scalars(select(DocumentSection).where(DocumentSection.document_id == doc.id).order_by(DocumentSection.sort_order)))
    reasons = _review_reasons(db, doc.encounter_id, overview)
    return {
        "document_id": doc.id, "encounter_id": doc.encounter_id, "document_type": doc.document_type,
        "variant": doc.variant or "admission", "status": doc.status, "generator_version": doc.generator_version,
        "generated_at": doc.generated_at, "approved_at": doc.approved_at,
        **document_state_status(db, doc),
        "sections": [_section_dict(db, s) for s in sections], "review_required": bool(reasons), "review_reasons": reasons,
    }


def regenerate_hp_content(db: Session, doc: ClinicalDocument, section: DocumentSection) -> str:
    overview = build_patient_overview(db, doc.encounter_id)
    if section.section_type == "hpi":
        return _hpi(overview, doc.variant or "admission")
    if section.section_type == "relevant_history":
        return _relevant_history(db, doc.encounter_id)
    if section.section_type == "objective_data":
        return _objective_snapshot(overview)
    if section.section_type == "focused_exam":
        return _focused_exam(db, doc.encounter_id)
    if section.section_type == "medication_reconciliation":
        return _med_reconciliation(db, doc.encounter_id)
    if section.section_type == "disposition":
        return _disposition(overview)
    if section.section_type == "assessment_plan_problem" and section.section_key:
        problem = next((p for p in overview.get("problems", []) if str(p["id"]) == section.section_key), None)
        return _problem_text(problem) if problem else "Problem is no longer present in the active structured problem state; physician review required."
    return section.current_generated_content or section.generated_content
