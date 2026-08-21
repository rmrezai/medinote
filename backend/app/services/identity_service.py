from __future__ import annotations

import re
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Encounter, Patient, SourceDocument, User
from app.services.security_service import audit


def _norm_mrn(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return normalized or None


def _norm_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return " ".join(normalized.split()) or None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def _extract_identity(raw_text: str) -> dict:
    # Conservative deterministic identity hints only. Name alone never proves identity.
    mrn_match = re.search(r"\bMRN\s*[:#-]?\s*([A-Za-z0-9-]{3,30})\b", raw_text, re.I)
    dob_match = re.search(r"\b(?:DOB|Date of Birth)\s*[:#-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", raw_text, re.I)
    source_name = None
    for line in raw_text.splitlines():
        name_match = re.match(r"\s*(?:Patient|Name)\s*[:#-]?\s*(.+?)\s*$", line, re.I)
        if name_match:
            candidate = name_match.group(1).replace(",", " ").strip()
            if 2 <= len(candidate.split()) <= 5 and re.fullmatch(r"[A-Za-z][A-Za-z' .-]*", candidate):
                source_name = candidate
                break
    return {
        "mrn": mrn_match.group(1) if mrn_match else None,
        "dob": _parse_date(dob_match.group(1)) if dob_match else None,
        "name": source_name,
    }


def evaluate_source_identity(patient: Patient, *, raw_text: str, asserted_mrn: str | None = None,
                             asserted_dob: date | None = None, asserted_name: str | None = None) -> tuple[str, str | None, dict]:
    extracted = _extract_identity(raw_text)
    source_mrn = asserted_mrn or extracted["mrn"]
    source_dob = asserted_dob or extracted["dob"]
    source_name = asserted_name or extracted["name"]

    patient_mrn = _norm_mrn(patient.mrn)
    candidate_mrn = _norm_mrn(source_mrn)
    patient_name = _norm_name(" ".join(x for x in [patient.first_name, patient.last_name] if x))
    candidate_name = _norm_name(source_name)

    mismatches = []
    matches = []
    if candidate_mrn and patient_mrn:
        if candidate_mrn == patient_mrn:
            matches.append("mrn")
        else:
            mismatches.append("mrn")
    if source_dob and patient.date_of_birth:
        if source_dob == patient.date_of_birth:
            matches.append("dob")
        else:
            mismatches.append("dob")
    if candidate_name and patient_name:
        if candidate_name == patient_name:
            matches.append("name")
        else:
            # Name disagreement is important but not independently a hard mismatch because formats/aliases vary.
            mismatches.append("name")

    evidence = {
        "asserted_mrn": source_mrn,
        "asserted_dob": source_dob.isoformat() if source_dob else None,
        "asserted_name": source_name,
        "matched_fields": matches,
        "mismatched_fields": mismatches,
    }

    # Exact MRN or DOB mismatch is a hard stop. Similar/one-digit MRNs are mismatches, never fuzzy matches.
    if "mrn" in mismatches or "dob" in mismatches:
        return "mismatch", "Source identifiers conflict with the selected patient encounter.", evidence
    if "mrn" in matches or ("dob" in matches and "name" in matches):
        return "matched", None, evidence
    if matches == ["name"] or "name" in matches:
        return "ambiguous", "Name match alone is insufficient to establish patient identity.", evidence
    return "not_asserted", None, evidence


def assert_encounter_identity_safe(db: Session, encounter_id: UUID) -> Encounter:
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise LookupError("Encounter not found")
    unsafe = db.scalar(select(SourceDocument).where(
        SourceDocument.encounter_id == encounter_id,
        SourceDocument.identity_status.in_(["mismatch", "ambiguous"]),
    ).limit(1))
    if unsafe:
        if unsafe.identity_status == "mismatch":
            raise ValueError("Patient identity hard stop: a quarantined source conflicts with this encounter. Remove/correct the source before analysis/document generation.")
        raise ValueError("Patient identity hard stop: a source has ambiguous identity. Physician source verification is required before analysis/document generation.")
    if encounter.identity_status == "blocked":
        raise ValueError("Patient identity hard stop: encounter identity is blocked pending physician verification.")
    return encounter


def verify_encounter_identity(db: Session, encounter_id: UUID, user: User, *, confirmed: bool, reason: str | None = None) -> dict:
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise LookupError("Encounter not found")
    if encounter.organization_id != user.organization_id:
        raise LookupError("Encounter not found")
    if not confirmed:
        encounter.identity_status = "blocked"
        encounter.identity_verified_by = user.id
        encounter.identity_verified_at = datetime.now(timezone.utc)
        audit(db, user=user, event_type="encounter_identity_blocked", encounter_id=encounter.id,
              object_type="encounter", object_id=encounter.id, metadata={"reason_recorded": bool(reason)})
    else:
        patient = db.get(Patient, encounter.patient_id)
        if not patient or not (patient.mrn or patient.date_of_birth):
            raise ValueError("Identity cannot be verified without MRN or DOB on the selected patient record.")
        encounter.identity_status = "physician_verified"
        encounter.identity_verified_by = user.id
        encounter.identity_verified_at = datetime.now(timezone.utc)
        audit(db, user=user, event_type="encounter_identity_verified", encounter_id=encounter.id,
              object_type="encounter", object_id=encounter.id, metadata={"reason_recorded": bool(reason)})
    db.commit()
    return {
        "encounter_id": encounter.id,
        "identity_status": encounter.identity_status,
        "verified_by": encounter.identity_verified_by,
        "verified_at": encounter.identity_verified_at,
    }


def identity_status(db: Session, encounter_id: UUID) -> dict:
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise LookupError("Encounter not found")
    patient = db.get(Patient, encounter.patient_id)
    sources = list(db.scalars(select(SourceDocument).where(SourceDocument.encounter_id == encounter_id).order_by(SourceDocument.imported_at)))
    return {
        "encounter_id": encounter.id,
        "identity_status": encounter.identity_status,
        "patient": {
            "patient_id": patient.id if patient else None,
            "mrn": patient.mrn if patient else None,
            "date_of_birth": patient.date_of_birth if patient else None,
            "display_name": " ".join(x for x in [patient.first_name, patient.last_name] if x) if patient else None,
        },
        "sources": [
            {
                "source_id": s.id,
                "document_type": s.document_type,
                "identity_status": s.identity_status,
                "identity_reason": s.identity_reason,
                "quarantined": s.identity_status == "mismatch",
            }
            for s in sources
        ],
        "hard_stop": any(s.identity_status in {"mismatch", "ambiguous"} for s in sources) or encounter.identity_status == "blocked",
    }


def verify_source_identity(db: Session, source_id: UUID, user: User, *, confirmed_match: bool, reason: str | None = None) -> dict:
    source = db.get(SourceDocument, source_id)
    if not source:
        raise LookupError("Source document not found")
    encounter = db.get(Encounter, source.encounter_id)
    if not encounter or encounter.organization_id != user.organization_id:
        raise LookupError("Source document not found")
    if source.identity_status == "mismatch" and confirmed_match:
        raise ValueError("An exact MRN/DOB mismatch cannot be overridden. Remove or correct the source document.")
    source.identity_status = "physician_verified" if confirmed_match else "mismatch"
    source.identity_reason = reason or ("Physician verified source belongs to selected encounter." if confirmed_match else "Physician marked source as wrong patient/chart.")
    audit(db, user=user, event_type="source_identity_verified" if confirmed_match else "source_identity_rejected",
          encounter_id=encounter.id, object_type="source_document", object_id=source.id,
          metadata={"confirmed_match": confirmed_match, "reason_recorded": bool(reason)})
    db.commit()
    return {"source_id": source.id, "encounter_id": encounter.id, "identity_status": source.identity_status, "identity_reason": source.identity_reason}
