"""Longitudinal patient record for returning-patient continuity.

The active EMR keeps one Patient linked to many Encounter rows. This service
retrieves prior encounters for the same verified patient and projects historical
clinical context into a new visit without silently making old facts current.

No historical item is copied into the new encounter by this service.
"""
from dataclasses import asdict, dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ClinicalDocument,
    ClinicalProblem,
    Encounter,
    Medication,
    MedicationState,
    Patient,
    RetentionSnapshot,
)


LONGITUDINAL_RECORD_VERSION = "medinote-longitudinal-record-v1"


class LongitudinalRecordError(ValueError):
    pass


@dataclass(frozen=True)
class HistoricalProblem:
    encounter_id: str
    problem_id: str
    name: str
    normalized_name: str | None
    status_at_encounter: str
    certainty: str
    icd10_candidate: str | None
    physician_approved: bool
    historical_only: bool = True
    requires_reconfirmation: bool = True


@dataclass(frozen=True)
class HistoricalMedication:
    encounter_id: str
    medication_id: str
    normalized_name: str
    display_name: str | None
    dose: str | None
    route: str | None
    frequency: str | None
    last_recorded_domain: str | None
    last_recorded_status: str | None
    physician_confirmed: bool
    historical_only: bool = True
    requires_reconciliation: bool = True


@dataclass(frozen=True)
class HistoricalEncounter:
    encounter_id: str
    admission_datetime: object | None
    discharge_datetime: object | None
    status: str
    service: str | None
    location: str | None
    finalized_document_refs: tuple[str, ...]
    archived_record_refs: tuple[str, ...]


@dataclass(frozen=True)
class ReturningPatientContext:
    patient_id: str
    current_encounter_id: str
    prior_encounters: tuple[HistoricalEncounter, ...]
    historical_problems: tuple[HistoricalProblem, ...]
    historical_medications: tuple[HistoricalMedication, ...]
    history_available: bool
    historical_items_are_current: bool = False
    clinician_reconfirmation_required: bool = True
    version: str = LONGITUDINAL_RECORD_VERSION


@dataclass(frozen=True)
class PatientRecordManifest:
    patient_id: str
    encounter_ids: tuple[str, ...]
    archived_encounter_ids: tuple[str, ...]
    missing_archive_encounter_ids: tuple[str, ...]
    archive_complete: bool
    version: str = LONGITUDINAL_RECORD_VERSION


def resolve_returning_patient(
    db: Session,
    organization_id: UUID,
    *,
    mrn: str,
    date_of_birth: date,
):
    """Resolve only an exact organization-local MRN + DOB identity.

    No fuzzy matching or automatic merge is permitted. Ambiguity fails closed.
    """
    if not isinstance(mrn, str) or not mrn.strip():
        raise LongitudinalRecordError("mrn-required")
    if not isinstance(date_of_birth, date):
        raise LongitudinalRecordError("date-of-birth-required")

    matches = list(
        db.scalars(
            select(Patient).where(
                Patient.organization_id == organization_id,
                Patient.mrn == mrn.strip(),
                Patient.date_of_birth == date_of_birth,
            )
        )
    )
    if len(matches) > 1:
        raise LongitudinalRecordError("ambiguous-patient-identity")
    return matches[0] if matches else None


def _latest_medication_state(db, medication_id):
    states = list(
        db.scalars(
            select(MedicationState)
            .where(MedicationState.medication_id == medication_id)
            .order_by(MedicationState.created_at.desc())
        )
    )
    return states[0] if states else None


def returning_patient_context(
    db: Session,
    organization_id: UUID,
    current_encounter_id: UUID,
):
    """Project prior encounters as historical context requiring reconfirmation."""
    current = db.get(Encounter, current_encounter_id)
    if not current or current.organization_id != organization_id:
        raise LookupError("Encounter not found")

    patient = db.get(Patient, current.patient_id)
    if not patient or patient.organization_id != organization_id:
        raise LookupError("Patient not found")

    prior = list(
        db.scalars(
            select(Encounter)
            .where(
                Encounter.organization_id == organization_id,
                Encounter.patient_id == patient.id,
                Encounter.id != current.id,
            )
            .order_by(Encounter.admission_datetime.asc(), Encounter.created_at.asc())
        )
    )

    encounter_rows = []
    problems = []
    medications = []
    for encounter in prior:
        docs = list(
            db.scalars(
                select(ClinicalDocument).where(
                    ClinicalDocument.encounter_id == encounter.id,
                    ClinicalDocument.status == "finalized",
                )
            )
        )
        archives = list(
            db.scalars(
                select(RetentionSnapshot).where(
                    RetentionSnapshot.organization_id == organization_id,
                    RetentionSnapshot.encounter_id == encounter.id,
                    RetentionSnapshot.format_version == "medinote-emr-record-v1",
                )
            )
        )
        encounter_rows.append(
            HistoricalEncounter(
                encounter_id=str(encounter.id),
                admission_datetime=encounter.admission_datetime,
                discharge_datetime=encounter.discharge_datetime,
                status=encounter.status,
                service=encounter.service,
                location=encounter.location,
                finalized_document_refs=tuple(sorted(str(doc.id) for doc in docs)),
                archived_record_refs=tuple(sorted(str(row.id) for row in archives)),
            )
        )

        for problem in db.scalars(
            select(ClinicalProblem).where(
                ClinicalProblem.encounter_id == encounter.id,
                ClinicalProblem.physician_approved.is_(True),
            )
        ):
            problems.append(
                HistoricalProblem(
                    encounter_id=str(encounter.id),
                    problem_id=str(problem.id),
                    name=problem.name,
                    normalized_name=problem.normalized_name,
                    status_at_encounter=problem.status,
                    certainty=problem.certainty,
                    icd10_candidate=problem.icd10_candidate,
                    physician_approved=problem.physician_approved,
                )
            )

        for medication in db.scalars(
            select(Medication).where(Medication.encounter_id == encounter.id)
        ):
            state = _latest_medication_state(db, medication.id)
            medications.append(
                HistoricalMedication(
                    encounter_id=str(encounter.id),
                    medication_id=str(medication.id),
                    normalized_name=medication.normalized_name,
                    display_name=medication.display_name,
                    dose=medication.dose,
                    route=medication.route,
                    frequency=medication.frequency,
                    last_recorded_domain=state.domain if state else None,
                    last_recorded_status=state.status if state else None,
                    physician_confirmed=bool(state and state.physician_confirmed),
                )
            )

    return ReturningPatientContext(
        patient_id=str(patient.id),
        current_encounter_id=str(current.id),
        prior_encounters=tuple(encounter_rows),
        historical_problems=tuple(problems),
        historical_medications=tuple(medications),
        history_available=bool(prior),
    )


def patient_record_manifest(db: Session, organization_id: UUID, patient_id: UUID):
    """Report whether every encounter has a full encrypted EMR archive."""
    patient = db.get(Patient, patient_id)
    if not patient or patient.organization_id != organization_id:
        raise LookupError("Patient not found")

    encounters = list(
        db.scalars(
            select(Encounter)
            .where(
                Encounter.organization_id == organization_id,
                Encounter.patient_id == patient.id,
            )
            .order_by(Encounter.created_at.asc())
        )
    )
    encounter_ids = tuple(str(enc.id) for enc in encounters)
    archived = []
    for enc in encounters:
        archive = db.scalar(
            select(RetentionSnapshot)
            .where(
                RetentionSnapshot.organization_id == organization_id,
                RetentionSnapshot.encounter_id == enc.id,
                RetentionSnapshot.format_version == "medinote-emr-record-v1",
            )
            .order_by(RetentionSnapshot.created_at.desc())
            .limit(1)
        )
        if archive is not None:
            archived.append(str(enc.id))

    archived_ids = tuple(archived)
    archived_set = set(archived_ids)
    missing = tuple(enc_id for enc_id in encounter_ids if enc_id not in archived_set)
    return PatientRecordManifest(
        patient_id=str(patient.id),
        encounter_ids=encounter_ids,
        archived_encounter_ids=archived_ids,
        missing_archive_encounter_ids=missing,
        archive_complete=bool(encounter_ids) and not missing,
    )


def context_to_dict(context):
    if not isinstance(context, ReturningPatientContext):
        raise LongitudinalRecordError("invalid-returning-patient-context")
    return asdict(context)


__all__ = [
    "LONGITUDINAL_RECORD_VERSION",
    "LongitudinalRecordError",
    "HistoricalProblem",
    "HistoricalMedication",
    "HistoricalEncounter",
    "ReturningPatientContext",
    "PatientRecordManifest",
    "resolve_returning_patient",
    "returning_patient_context",
    "patient_record_manifest",
    "context_to_dict",
]
