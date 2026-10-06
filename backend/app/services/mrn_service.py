"""Stable internal MRN issuance and external identifier mapping."""
import secrets
import string
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Patient, PatientExternalIdentifier


MRN_VERSION = "medinote-mrn-v1"
_ALPHABET = string.ascii_uppercase + string.digits


class MrnError(ValueError):
    pass


def _candidate_mrn():
    # Nonsemantic: contains no DOB, initials, location, phone, SSN, or other PHI.
    return "CLN-" + "".join(secrets.choice(_ALPHABET) for _ in range(12))


def issue_patient_mrn(db: Session, organization_id: UUID, patient_id: UUID):
    """Assign one stable organization-local MRN if the patient lacks one."""
    patient = db.get(Patient, patient_id)
    if not patient or patient.organization_id != organization_id:
        raise LookupError("Patient not found")
    if patient.mrn:
        return patient.mrn

    for _ in range(20):
        candidate = _candidate_mrn()
        exists = db.scalar(
            select(Patient.id).where(
                Patient.organization_id == organization_id,
                Patient.mrn == candidate,
            )
        )
        if exists is None:
            patient.mrn = candidate
            db.flush()
            return candidate
    raise MrnError("mrn-generation-collision-limit")


def map_external_identifier(
    db: Session,
    organization_id: UUID,
    patient_id: UUID,
    *,
    source_system,
    identifier_value,
    identifier_type="external-mrn",
    assigning_authority=None,
    source_record_ref=None,
):
    """Map an outside identifier to the internal patient without changing MRN."""
    patient = db.get(Patient, patient_id)
    if not patient or patient.organization_id != organization_id:
        raise LookupError("Patient not found")
    if not isinstance(source_system, str) or not source_system.strip():
        raise MrnError("source-system-required")
    if not isinstance(identifier_value, str) or not identifier_value.strip():
        raise MrnError("identifier-required")

    existing = db.scalar(
        select(PatientExternalIdentifier).where(
            PatientExternalIdentifier.organization_id == organization_id,
            PatientExternalIdentifier.source_system == source_system.strip(),
            PatientExternalIdentifier.identifier_type == identifier_type,
            PatientExternalIdentifier.identifier_value == identifier_value.strip(),
        )
    )
    if existing:
        if existing.patient_id != patient.id:
            raise MrnError("external-identifier-already-linked")
        return existing, "duplicate"

    row = PatientExternalIdentifier(
        organization_id=organization_id,
        patient_id=patient.id,
        source_system=source_system.strip(),
        identifier_type=identifier_type,
        identifier_value=identifier_value.strip(),
        assigning_authority=(
            assigning_authority.strip()
            if isinstance(assigning_authority, str) and assigning_authority.strip()
            else None
        ),
        source_record_ref=(
            source_record_ref.strip()
            if isinstance(source_record_ref, str) and source_record_ref.strip()
            else None
        ),
    )
    db.add(row)
    db.flush()
    return row, "accepted"


def resolve_external_identifier(
    db: Session,
    organization_id: UUID,
    *,
    source_system,
    identifier_value,
    identifier_type="external-mrn",
):
    row = db.scalar(
        select(PatientExternalIdentifier).where(
            PatientExternalIdentifier.organization_id == organization_id,
            PatientExternalIdentifier.source_system == source_system,
            PatientExternalIdentifier.identifier_type == identifier_type,
            PatientExternalIdentifier.identifier_value == identifier_value,
        )
    )
    return db.get(Patient, row.patient_id) if row else None


__all__ = [
    "MRN_VERSION",
    "MrnError",
    "issue_patient_mrn",
    "map_external_identifier",
    "resolve_external_identifier",
]
