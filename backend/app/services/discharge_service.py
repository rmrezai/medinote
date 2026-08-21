from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.state_version_service import document_state_status
from app.models import (
    Encounter,
    ClinicalDocument, DocumentSection, Medication, MedicationState,
    PendingItem, ConsultantRecommendation,
)
from app.services.overview_service import build_patient_overview
from app.services.progress_service import _section_dict, _evidence_phrase

ALLOWED_VARIANTS = {"summary", "short", "clinical_course", "med_reconciliation", "avs", "addendum"}
GENERATOR_VERSION = "discharge-deterministic-v0.1"


def _diagnoses_text(overview: dict) -> str:
    problems = overview.get("problems", [])
    if not problems:
        return "Discharge diagnoses: no active structured diagnoses are available; physician review required."
    lines = []
    for p in problems:
        label = p["name"]
        certainty = p.get("certainty")
        if certainty and certainty not in {"confirmed", "unclear"}:
            label += f" ({certainty})"
        status = p.get("status")
        if status and status not in {"active", "new"}:
            label += f" - {status}"
        lines.append(label)
    return "Discharge diagnoses:\n- " + "\n- ".join(lines[:12])


def _course_problem(problem: dict) -> str:
    title = problem["name"]
    certainty = problem.get("certainty")
    if certainty and certainty not in {"confirmed", "unclear"}:
        title += f" ({certainty})"
    status = problem.get("status")
    if status and status not in {"active", "new"}:
        title += f" - {status}"
    evidence = _evidence_phrase(problem.get("evidence", []))
    if evidence:
        return (
            f"{title}\n"
            f"Course: structured evidence includes {evidence}. "
            "Treatment course, causal attribution, and final status require physician confirmation from the documented hospitalization."
        )
    return f"{title}\nCourse: no linked structured evidence is available; physician review required."


def _medication_transitions(db: Session, encounter_id: UUID) -> str:
    meds = list(db.scalars(select(Medication).where(Medication.encounter_id == encounter_id)))
    lines = []
    for med in meds:
        states = list(db.scalars(select(MedicationState).where(
            MedicationState.medication_id == med.id,
            MedicationState.is_current == True,  # noqa: E712
        )))
        by_domain = {s.domain: s for s in states}
        home = by_domain.get("home")
        hospital = by_domain.get("hospital")
        discharge = by_domain.get("discharge")
        name = med.display_name or med.normalized_name
        parts = []
        if home:
            parts.append(f"home {home.status}")
        if hospital:
            parts.append(f"hospital {hospital.status}")
        if discharge:
            parts.append(f"discharge {discharge.status}")
        else:
            parts.append("discharge state not established")
        reason = (discharge.reason if discharge and discharge.reason else hospital.reason if hospital else None)
        text = f"{name}: " + " -> ".join(parts)
        if reason:
            text += f" ({reason})"
        lines.append(text)
    if not lines:
        return "Medication transitions: no structured medication states are available."
    return "Medication transitions:\n- " + "\n- ".join(lines[:20])


def _pending_text(db: Session, encounter_id: UUID) -> str:
    items = list(db.scalars(select(PendingItem).where(
        PendingItem.encounter_id == encounter_id,
        PendingItem.status == "pending",
    )))
    if not items:
        return "Pending at discharge: no structured pending items are currently recorded."
    lines = []
    for item in items:
        text = item.description
        if item.owner:
            text += f"; documented owner: {item.owner}"
        else:
            text += "; follow-up owner not established in structured data"
        lines.append(text)
    return "Pending at discharge:\n- " + "\n- ".join(lines)


def _followup_text(db: Session, encounter_id: UUID) -> str:
    pending = list(db.scalars(select(PendingItem).where(
        PendingItem.encounter_id == encounter_id,
        PendingItem.status == "pending",
    )))
    consultants = list(db.scalars(select(ConsultantRecommendation).where(
        ConsultantRecommendation.encounter_id == encounter_id,
    ).order_by(ConsultantRecommendation.recommendation_datetime.desc())))
    bits = []
    for item in pending[:6]:
        if item.clinical_significance:
            bits.append(f"{item.description}: {item.clinical_significance}")
    for rec in consultants[:4]:
        if rec.recommendation and (rec.current_relevance or "").lower() not in {"superseded", "inactive"}:
            bits.append(f"{rec.service}: {rec.recommendation}")
    if not bits:
        return "Follow-up needs: no structured follow-up need is available; appointments or completed arrangements must not be assumed."
    return "Follow-up needs for physician review:\n- " + "\n- ".join(bits)


def _disposition_text(overview: dict) -> str:
    d = overview.get("disposition")
    if not d:
        return "Disposition: no structured final disposition is available; physician confirmation required."
    parts = []
    if d.get("anticipated_destination"):
        parts.append(f"anticipated destination {d['anticipated_destination']}")
    if d.get("current_barriers"):
        parts.append(f"barriers {d['current_barriers']}")
    if d.get("pt_recommendation"):
        parts.append(f"PT recommendation {d['pt_recommendation']}")
    if d.get("oxygen_need"):
        parts.append(f"oxygen need {d['oxygen_need']}")
    if not parts:
        return "Disposition: structured disposition record present without a confirmed final destination; physician review required."
    return "Disposition: " + "; ".join(parts) + "."


def _avs_text(overview: dict) -> str:
    problems = overview.get("problems", [])
    if problems:
        names = ", ".join(p["name"] for p in problems[:4])
        first = f"Why you were in the hospital: care was provided for {names}."
    else:
        first = "Why you were in the hospital: the structured diagnosis list is incomplete and requires clinician review."
    return (
        first
        + " Medication instructions, follow-up appointments, return precautions, and completed education must be confirmed by the clinician before use."
    )


def _review_reasons(db: Session, encounter_id: UUID, overview: dict) -> list[str]:
    reasons = []
    if overview.get("contradictions"):
        reasons.append(f"{len(overview['contradictions'])} unresolved contradiction(s) remain in the encounter state.")
    unresolved = overview.get("attention_counts", {}).get("unresolved_medications", 0)
    if unresolved:
        reasons.append(f"{unresolved} discharge medication decision(s) remain unresolved.")
    pending = list(db.scalars(select(PendingItem).where(PendingItem.encounter_id == encounter_id, PendingItem.status == "pending")))
    if pending:
        reasons.append(f"{len(pending)} pending item(s) require explicit discharge follow-up review.")
    if not overview.get("disposition") or not overview.get("disposition", {}).get("anticipated_destination"):
        reasons.append("Final discharge destination is not established in structured data.")
    for problem in overview.get("problems", []):
        if not problem.get("evidence"):
            reasons.append(f'Problem "{problem["name"]}" has no linked structured evidence.')
    return reasons


def generate_discharge_document(db: Session, encounter_id: UUID, variant: str = "summary", generated_by: UUID | None = None) -> dict:
    variant = variant.lower().strip()
    if variant not in ALLOWED_VARIANTS:
        raise ValueError(f"Unsupported discharge variant: {variant}")
    overview = build_patient_overview(db, encounter_id)
    doc = ClinicalDocument(
        encounter_id=encounter_id, document_type="discharge", variant=variant,
        status="draft", generator_version=GENERATOR_VERSION, generated_by=generated_by,
        generated_state_version=int(db.get(Encounter, encounter_id).clinical_state_version or 1),
    )
    db.add(doc); db.flush()
    sections = []
    order = 10

    def add(section_type: str, key: str, text: str):
        nonlocal order
        s = DocumentSection(document_id=doc.id, section_type=section_type, section_key=key, sort_order=order, generated_content=text)
        db.add(s); db.flush(); sections.append(s); order += 10

    if variant == "med_reconciliation":
        add("medication_transitions", "medication_transitions", _medication_transitions(db, encounter_id))
    elif variant == "avs":
        add("avs", "avs", _avs_text(overview))
        add("medication_transitions", "medication_transitions", _medication_transitions(db, encounter_id))
        add("follow_up", "follow_up", _followup_text(db, encounter_id))
        add("pending_results", "pending_results", _pending_text(db, encounter_id))
    elif variant == "addendum":
        add("discharge_addendum", "discharge_addendum", "Discharge addendum: include only newly documented information and its clinical implication; physician completion required.")
        add("pending_results", "pending_results", _pending_text(db, encounter_id))
    else:
        add("discharge_diagnoses", "discharge_diagnoses", _diagnoses_text(overview))
        problems = overview.get("problems", [])
        if variant == "short":
            problems = problems[:4]
        for problem in problems:
            add("hospital_course_problem", str(problem["id"]), _course_problem(problem))
        add("medication_transitions", "medication_transitions", _medication_transitions(db, encounter_id))
        add("pending_results", "pending_results", _pending_text(db, encounter_id))
        add("follow_up", "follow_up", _followup_text(db, encounter_id))
        add("disposition", "disposition", _disposition_text(overview))

    db.commit(); db.refresh(doc)
    reasons = _review_reasons(db, encounter_id, overview)
    return {
        "document_id": doc.id, "encounter_id": doc.encounter_id, "document_type": doc.document_type,
        "variant": doc.variant, "status": doc.status, "generator_version": doc.generator_version,
        "generated_at": doc.generated_at, "approved_at": doc.approved_at,
        **document_state_status(db, doc),
        "sections": [_section_dict(db, s) for s in sections],
        "review_required": bool(reasons), "review_reasons": reasons,
    }


def get_discharge_document(db: Session, document_id: UUID) -> dict:
    doc = db.get(ClinicalDocument, document_id)
    if not doc or doc.document_type != "discharge":
        raise LookupError("Discharge document not found")
    overview = build_patient_overview(db, doc.encounter_id)
    sections = list(db.scalars(select(DocumentSection).where(DocumentSection.document_id == doc.id).order_by(DocumentSection.sort_order)))
    reasons = _review_reasons(db, doc.encounter_id, overview)
    return {
        "document_id": doc.id, "encounter_id": doc.encounter_id, "document_type": doc.document_type,
        "variant": doc.variant or "summary", "status": doc.status, "generator_version": doc.generator_version,
        "generated_at": doc.generated_at, "approved_at": doc.approved_at,
        **document_state_status(db, doc),
        "sections": [_section_dict(db, s) for s in sections],
        "review_required": bool(reasons), "review_reasons": reasons,
    }


def regenerate_discharge_content(db: Session, doc: ClinicalDocument, section: DocumentSection) -> str:
    overview = build_patient_overview(db, doc.encounter_id)
    if section.section_type == "discharge_diagnoses":
        return _diagnoses_text(overview)
    if section.section_type == "hospital_course_problem" and section.section_key:
        problem = next((p for p in overview.get("problems", []) if str(p["id"]) == section.section_key), None)
        return _course_problem(problem) if problem else "Problem is no longer present in the active structured problem state; physician review required."
    if section.section_type == "medication_transitions":
        return _medication_transitions(db, doc.encounter_id)
    if section.section_type == "pending_results":
        return _pending_text(db, doc.encounter_id)
    if section.section_type == "follow_up":
        return _followup_text(db, doc.encounter_id)
    if section.section_type == "disposition":
        return _disposition_text(overview)
    if section.section_type == "avs":
        return _avs_text(overview)
    if section.section_type == "discharge_addendum":
        return "Discharge addendum: include only newly documented information and its clinical implication; physician completion required."
    return section.current_generated_content or section.generated_content
