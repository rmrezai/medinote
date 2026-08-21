from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.services.identity_service import assert_encounter_identity_safe

from app.models import (
    ClinicalFact,
    ClinicalProblem,
    ClinicalTrajectory,
    ConsultantRecommendation,
    Contradiction,
    DispositionState,
    Encounter,
    LabResult,
    Medication,
    MedicationState,
    Patient,
    PendingItem,
    ProblemEvidence,
)


def _number(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _fact_value(fact: ClinicalFact) -> str | None:
    if fact.value_numeric is not None:
        value = str(_number(fact.value_numeric))
        return f"{value} {fact.units}".strip() if fact.units else value
    return fact.value_text


def _clinical_picture(problems: list[ClinicalProblem], pending_count: int, contradiction_count: int) -> str:
    if not problems:
        base = "No active structured clinical problems are currently established in MCIF."
    else:
        phrases = []
        for problem in problems[:3]:
            label = problem.name
            if problem.status and problem.status not in {"active", "new"}:
                label = f"{label} - {problem.status}"
            if problem.certainty and problem.certainty not in {"confirmed", "unclear"}:
                label = f"{label} ({problem.certainty})"
            phrases.append(label)
        base = "Active inpatient picture: " + "; ".join(phrases) + "."

    extras = []
    if pending_count:
        extras.append(f"{pending_count} pending item{'s' if pending_count != 1 else ''}")
    if contradiction_count:
        extras.append(f"{contradiction_count} unresolved contradiction{'s' if contradiction_count != 1 else ''}")
    if extras:
        base += " Review: " + ", ".join(extras) + "."
    return base


def build_patient_overview(db: Session, encounter_id: UUID) -> dict:
    assert_encounter_identity_safe(db, encounter_id)
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise LookupError("Encounter not found")
    patient = db.get(Patient, encounter.patient_id)

    problems = list(db.scalars(select(ClinicalProblem).where(
        ClinicalProblem.encounter_id == encounter_id,
        ClinicalProblem.status != "resolved",
    ).order_by(ClinicalProblem.acuity_rank.asc().nullslast(), ClinicalProblem.created_at.asc())))

    current_facts = list(db.scalars(select(ClinicalFact).where(
        ClinicalFact.encounter_id == encounter_id,
        ClinicalFact.is_current.is_(True),
    )))
    facts_by_id = {fact.id: fact for fact in current_facts}

    evidence_links = list(db.scalars(select(ProblemEvidence).join(
        ClinicalProblem, ProblemEvidence.problem_id == ClinicalProblem.id
    ).where(ClinicalProblem.encounter_id == encounter_id)))
    evidence_by_problem: dict[UUID, list[dict]] = defaultdict(list)
    for link in evidence_links:
        fact = facts_by_id.get(link.fact_id) or db.get(ClinicalFact, link.fact_id)
        if fact is None:
            continue
        evidence_by_problem[link.problem_id].append({
            "fact_id": fact.id,
            "concept": fact.concept,
            "value": _fact_value(fact),
            "units": fact.units,
            "observed_datetime": fact.observed_datetime,
            "confidence": fact.confidence,
            "source_document_id": fact.source_document_id,
            "relationship": link.relationship,
            "evidence_strength": link.evidence_strength,
        })

    trajectories = list(db.scalars(select(ClinicalTrajectory).where(
        ClinicalTrajectory.encounter_id == encounter_id
    )))
    lab_trajectory = {
        row.concept.lower(): row for row in trajectories if row.category == "lab"
    }

    all_labs = list(db.scalars(select(LabResult).where(
        LabResult.encounter_id == encounter_id
    ).order_by(LabResult.collection_datetime.desc().nullslast(), LabResult.created_at.desc())))
    latest_labs = []
    seen_lab_names = set()
    for lab in all_labs:
        key = lab.test_name.strip().lower()
        if key in seen_lab_names:
            continue
        seen_lab_names.add(key)
        trajectory = lab_trajectory.get(key)
        latest_labs.append({
            "id": lab.id,
            "test_name": lab.test_name,
            "value_numeric": _number(lab.value_numeric),
            "value_text": lab.value_text,
            "units": lab.units,
            "abnormal_flag": lab.abnormal_flag,
            "collection_datetime": lab.collection_datetime,
            "trend": trajectory.trend if trajectory else None,
            "earliest_value": trajectory.earliest_value if trajectory else None,
            "latest_value": trajectory.latest_value if trajectory else None,
        })

    meds = list(db.scalars(select(Medication).where(
        Medication.encounter_id == encounter_id
    ).order_by(Medication.normalized_name.asc())))
    medication_output = []
    for med in meds:
        states = list(db.scalars(select(MedicationState).where(
            MedicationState.medication_id == med.id,
            MedicationState.is_current.is_(True),
        ).order_by(MedicationState.domain.asc())))
        unresolved = any(
            state.status in {"unclear", "requires_decision", "conflicted"}
            for state in states
        )
        medication_output.append({
            "id": med.id,
            "name": med.display_name or med.normalized_name,
            "normalized_name": med.normalized_name,
            "dose": med.dose,
            "route": med.route,
            "frequency": med.frequency,
            "indication": med.indication,
            "states": [
                {
                    "domain": state.domain,
                    "status": state.status,
                    "effective_datetime": state.effective_datetime,
                    "reason": state.reason,
                    "restart_criteria": state.restart_criteria,
                    "physician_confirmed": state.physician_confirmed,
                }
                for state in states
            ],
            "unresolved": unresolved,
        })

    consultants = list(db.scalars(select(ConsultantRecommendation).where(
        ConsultantRecommendation.encounter_id == encounter_id
    ).order_by(ConsultantRecommendation.recommendation_datetime.desc().nullslast(), ConsultantRecommendation.created_at.desc())))

    pending = list(db.scalars(select(PendingItem).where(
        PendingItem.encounter_id == encounter_id,
        PendingItem.status == "pending",
    ).order_by(PendingItem.created_at.asc())))

    disposition = db.scalar(select(DispositionState).where(
        DispositionState.encounter_id == encounter_id
    ).order_by(DispositionState.source_datetime.desc().nullslast(), DispositionState.created_at.desc()).limit(1))

    contradictions = list(db.scalars(select(Contradiction).where(
        Contradiction.encounter_id == encounter_id,
        Contradiction.status == "unresolved",
    ).order_by(Contradiction.severity.desc(), Contradiction.created_at.asc())))

    problem_output = []
    for problem in problems:
        problem_output.append({
            "id": problem.id,
            "name": problem.name,
            "normalized_name": problem.normalized_name,
            "certainty": problem.certainty,
            "status": problem.status,
            "acuity_rank": problem.acuity_rank,
            "physician_approved": problem.physician_approved,
            "evidence": evidence_by_problem.get(problem.id, []),
        })

    patient_name = None
    if patient:
        patient_name = " ".join(x for x in [patient.first_name, patient.last_name] if x) or None

    high_contradictions = sum(1 for item in contradictions if item.severity in {"high", "critical"})
    unresolved_meds = sum(1 for med in medication_output if med["unresolved"])

    return {
        "encounter_id": encounter.id,
        "patient_id": encounter.patient_id,
        "patient_display_name": patient_name,
        "mrn": patient.mrn if patient else None,
        "service": encounter.service,
        "location": encounter.location,
        "admission_datetime": encounter.admission_datetime,
        "encounter_status": encounter.status,
        "current_clinical_picture": _clinical_picture(problems, len(pending), len(contradictions)),
        "problems": problem_output,
        "latest_labs": latest_labs,
        "medications": medication_output,
        "consultants": [
            {
                "id": row.id,
                "service": row.service,
                "consultant_name": row.consultant_name,
                "recommendation_datetime": row.recommendation_datetime,
                "assessment": row.assessment,
                "recommendation": row.recommendation,
                "implementation_status": row.implementation_status,
                "conflict_status": row.conflict_status,
            }
            for row in consultants
        ],
        "pending_items": [
            {
                "id": row.id,
                "item_type": row.item_type,
                "description": row.description,
                "status": row.status,
                "owner": row.owner,
                "clinical_significance": row.clinical_significance,
            }
            for row in pending
        ],
        "disposition": {
            "anticipated_destination": disposition.anticipated_destination,
            "current_barriers": disposition.current_barriers,
            "mobility_status": disposition.mobility_status,
            "pt_recommendation": disposition.pt_recommendation,
            "ot_recommendation": disposition.ot_recommendation,
            "slp_recommendation": disposition.slp_recommendation,
            "oxygen_need": disposition.oxygen_need,
            "authorization_status": disposition.authorization_status,
        } if disposition else None,
        "contradictions": [
            {
                "id": row.id,
                "category": row.category,
                "description": row.description,
                "severity": row.severity,
                "status": row.status,
                "fact_a_id": row.fact_a_id,
                "fact_b_id": row.fact_b_id,
                "source_a_type": row.source_a_type,
                "source_a_id": row.source_a_id,
                "source_b_type": row.source_b_type,
                "source_b_id": row.source_b_id,
            }
            for row in contradictions
        ],
        "attention_counts": {
            "active_problems": len(problems),
            "pending_items": len(pending),
            "unresolved_contradictions": len(contradictions),
            "high_severity_contradictions": high_contradictions,
            "unresolved_medications": unresolved_meds,
        },
    }
