from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.services.identity_service import assert_encounter_identity_safe
from app.services.state_version_service import bump_state_version

from app.models import Encounter, Medication, MedicationState
from app.schemas.med_rec import ALLOWED_DISCHARGE_STATES, MedRecDecision


HIGH_RISK_TERMS = (
    "warfarin", "apixaban", "rivaroxaban", "dabigatran", "edoxaban", "heparin", "enoxaparin",
    "insulin", "glargine", "lispro", "aspart", "regular insulin",
    "prednisone", "hydrocortisone", "dexamethasone", "methylprednisolone",
    "furosemide", "bumetanide", "torsemide", "spironolactone",
    "lisinopril", "losartan", "valsartan", "sacubitril", "entresto",
    "empagliflozin", "dapagliflozin", "canagliflozin",
    "levetiracetam", "valproate", "phenytoin", "carbamazepine",
    "morphine", "hydromorphone", "oxycodone", "fentanyl", "lorazepam", "diazepam",
)

UNRESOLVED = {"unclear", "requires_decision", "conflicted"}


def _current_state(db: Session, medication_id: UUID, domain: str) -> MedicationState | None:
    return db.scalar(
        select(MedicationState)
        .where(
            MedicationState.medication_id == medication_id,
            MedicationState.domain == domain,
            MedicationState.is_current.is_(True),
        )
        .order_by(MedicationState.effective_datetime.desc().nullslast(), MedicationState.created_at.desc())
        .limit(1)
    )


def _state_dict(state: MedicationState | None) -> dict | None:
    if state is None:
        return None
    return {
        "state_id": state.id,
        "domain": state.domain,
        "status": state.status,
        "reason": state.reason,
        "restart_criteria": state.restart_criteria,
        "effective_datetime": state.effective_datetime,
        "physician_confirmed": state.physician_confirmed,
        "revision": int(state.revision or 1),
    }


def _high_risk(med: Medication) -> bool:
    haystack = " ".join(filter(None, [med.normalized_name, med.display_name, med.indication])).lower()
    return any(term in haystack for term in HIGH_RISK_TERMS)


def _transition_text(home: MedicationState | None, hospital: MedicationState | None, discharge: MedicationState | None) -> str:
    parts = []
    if home:
        parts.append(f"Home: {home.status}")
    if hospital:
        parts.append(f"Hospital: {hospital.status}")
    if discharge:
        label = f"Discharge: {discharge.status}"
        if discharge.physician_confirmed:
            label += " (confirmed)"
        parts.append(label)
    if not parts:
        return "No structured medication state available."
    return " -> ".join(parts)


def build_med_rec_workspace(db: Session, encounter_id: UUID) -> dict:
    assert_encounter_identity_safe(db, encounter_id)
    if db.get(Encounter, encounter_id) is None:
        raise LookupError("Encounter not found")

    medications = list(db.scalars(
        select(Medication)
        .where(Medication.encounter_id == encounter_id)
        .order_by(Medication.normalized_name.asc())
    ))

    rows = []
    unresolved_count = 0
    high_risk_count = 0
    changed_count = 0

    for med in medications:
        home = _current_state(db, med.id, "home")
        hospital = _current_state(db, med.id, "hospital")
        discharge = _current_state(db, med.id, "discharge")

        unresolved = discharge is None or discharge.status in UNRESOLVED or not discharge.physician_confirmed
        high_risk = _high_risk(med)
        changed = bool(
            (home and hospital and home.status != hospital.status)
            or (hospital and discharge and hospital.status != discharge.status)
            or (home and discharge and home.status != discharge.status)
        )

        unresolved_count += int(unresolved)
        high_risk_count += int(high_risk)
        changed_count += int(changed)

        rows.append({
            "medication_id": med.id,
            "name": med.display_name or med.normalized_name,
            "normalized_name": med.normalized_name,
            "dose": med.dose,
            "route": med.route,
            "frequency": med.frequency,
            "indication": med.indication,
            "home": _state_dict(home),
            "hospital": _state_dict(hospital),
            "discharge": _state_dict(discharge),
            "unresolved": unresolved,
            "high_risk": high_risk,
            "transition_summary": _transition_text(home, hospital, discharge),
        })

    return {
        "encounter_id": encounter_id,
        "medications": rows,
        "unresolved_count": unresolved_count,
        "high_risk_count": high_risk_count,
        "changed_count": changed_count,
    }


def confirm_discharge_state(db: Session, medication_id: UUID, payload: MedRecDecision) -> MedicationState:
    med = db.get(Medication, medication_id)
    if med is None:
        raise LookupError("Medication not found")
    if payload.status not in ALLOWED_DISCHARGE_STATES:
        raise ValueError(f"Unsupported discharge medication state: {payload.status}")

    current_before = _current_state(db, medication_id, "discharge")
    if "expected_current_state_id" in payload.model_fields_set:
        current_id = current_before.id if current_before else None
        if current_id != payload.expected_current_state_id:
            from app.services.concurrency_service import ConcurrencyConflict
            raise ConcurrencyConflict("Medication discharge state changed since this screen was loaded. Refresh Med Rec before saving.")

    existing = list(db.scalars(
        select(MedicationState).where(
            MedicationState.medication_id == medication_id,
            MedicationState.domain == "discharge",
            MedicationState.is_current.is_(True),
        )
    ))
    for row in existing:
        row.is_current = False

    state = MedicationState(
        medication_id=medication_id,
        domain="discharge",
        status=payload.status,
        effective_datetime=payload.effective_datetime or datetime.now(timezone.utc),
        reason=payload.reason,
        restart_criteria=payload.restart_criteria,
        is_current=True,
        physician_confirmed=True,
        confirmed_by=payload.confirmed_by,
        confirmed_at=datetime.now(timezone.utc),
    )
    db.add(state)
    bump_state_version(db, med.encounter_id)
    db.commit()
    db.refresh(state)
    return state
