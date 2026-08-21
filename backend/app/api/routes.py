from app.api import concurrency_routes
import hashlib
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import Encounter, Organization, Patient, SourceDocument, ClinicalDocument, DocumentSection, User
from app.schemas.core import EncounterCreate, EncounterRead, EncounterSummary, FinalTextResponse, OrganizationCreate, OrganizationRead, SourceCreate, SourceRead, IdentityVerifyRequest, SourceIdentityVerifyRequest
from app.services.security_service import current_user, require_admin, audit
from app.services.identity_service import evaluate_source_identity, verify_encounter_identity, verify_source_identity, identity_status, assert_encounter_identity_safe
from app.services.state_version_service import bump_state_version

router = APIRouter(prefix="/api/v1")




@router.get("/organizations", response_model=list[OrganizationRead])
def list_organizations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Organization).where(Organization.id == user.organization_id, Organization.active == True).order_by(Organization.created_at)))  # noqa: E712


@router.post("/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(payload: OrganizationCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    org = Organization(name=payload.name)
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@router.get("/encounters", response_model=list[EncounterSummary])
def list_encounters(organization_id: UUID | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Encounter, Patient).join(Patient, Encounter.patient_id == Patient.id).where(Encounter.organization_id == user.organization_id)
    stmt = stmt.order_by(Encounter.updated_at.desc(), Encounter.created_at.desc())
    rows = db.execute(stmt).all()
    return [
        {
            "id": encounter.id,
            "patient_id": patient.id,
            "organization_id": encounter.organization_id,
            "patient_display_name": " ".join(x for x in [patient.first_name, patient.last_name] if x) or None,
            "mrn": patient.mrn,
            "date_of_birth": patient.date_of_birth,
            "admission_datetime": encounter.admission_datetime,
            "discharge_datetime": encounter.discharge_datetime,
            "status": encounter.status,
            "service": encounter.service,
            "location": encounter.location,
        }
        for encounter, patient in rows
    ]


@router.get("/health")
def health():
    return {"status": "ok", "service": "medinote-api"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready", "service": "medinote-api"}


@router.post("/encounters", response_model=EncounterRead, status_code=status.HTTP_201_CREATED)
def create_encounter(payload: EncounterCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Cannot create encounter outside your organization")
    patient = Patient(organization_id=user.organization_id, **payload.patient.model_dump())
    db.add(patient)
    db.flush()

    encounter = Encounter(
        patient_id=patient.id,
        organization_id=user.organization_id,
        admission_datetime=payload.admission_datetime,
        service=payload.service,
        location=payload.location,
        attending_user_id=payload.attending_user_id,
        identity_status="created_verified" if (payload.patient.mrn or payload.patient.date_of_birth) else "unverified",
    )
    db.add(encounter)
    audit(db, user=user, event_type="encounter_created", encounter_id=encounter.id, object_type="encounter", object_id=encounter.id)
    db.commit()
    db.refresh(encounter)
    return encounter


@router.get("/encounters/{encounter_id}", response_model=EncounterRead)
def get_encounter(encounter_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    encounter = db.get(Encounter, encounter_id)
    if not encounter or encounter.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Encounter not found")
    audit(db, user=user, event_type="encounter_opened", encounter_id=encounter.id, object_type="encounter", object_id=encounter.id)
    db.commit()
    return encounter


@router.post("/encounters/{encounter_id}/sources", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def add_source(encounter_id: UUID, payload: SourceCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    encounter = db.get(Encounter, encounter_id)
    if not encounter or encounter.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Encounter not found")

    content_hash = hashlib.sha256(payload.raw_text.encode("utf-8")).hexdigest()
    duplicate = db.scalar(
        select(SourceDocument).where(
            SourceDocument.encounter_id == encounter_id,
            SourceDocument.content_hash == content_hash,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Duplicate source document")

    patient = db.get(Patient, encounter.patient_id)
    identity_state, identity_reason, identity_evidence = evaluate_source_identity(
        patient, raw_text=payload.raw_text, asserted_mrn=payload.asserted_mrn,
        asserted_dob=payload.asserted_dob, asserted_name=payload.asserted_name,
    )
    source = SourceDocument(
        encounter_id=encounter_id,
        content_hash=content_hash,
        **payload.model_dump(exclude={"imported_by"}),
        imported_by=user.id,
        identity_status=identity_state,
        identity_reason=identity_reason,
    )
    db.add(source)
    bump_state_version(db, encounter_id)
    audit(db, user=user, event_type="chart_source_imported", encounter_id=encounter_id, object_type="source_document", object_id=source.id, metadata={"document_type": payload.document_type, "identity_status": identity_state, "identity_fields_present": identity_evidence["matched_fields"] + identity_evidence["mismatched_fields"]})
    db.commit()
    db.refresh(source)
    return source


@router.get("/encounters/{encounter_id}/sources", response_model=list[SourceRead])
def list_sources(encounter_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    encounter = db.get(Encounter, encounter_id)
    if not encounter or encounter.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return list(db.scalars(select(SourceDocument).where(SourceDocument.encounter_id == encounter_id).order_by(SourceDocument.imported_at)))


@router.post("/sources/{source_id}/identity/verify")
def verify_source(source_id: UUID, payload: SourceIdentityVerifyRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return verify_source_identity(db, source_id, user, confirmed_match=payload.confirmed_match, reason=payload.reason)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    source = db.get(SourceDocument, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source document not found")
    encounter = db.get(Encounter, source.encounter_id)
    if not encounter or encounter.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Source document not found")
    if source.identity_status not in {"mismatch", "ambiguous", "not_asserted"}:
        raise HTTPException(status_code=409, detail="Only untrusted/quarantined sources may be removed through this safety endpoint")
    audit(db, user=user, event_type="quarantined_source_removed", encounter_id=encounter.id, object_type="source_document", object_id=source.id, metadata={"identity_status": source.identity_status})
    db.delete(source)
    db.commit()
    return None


@router.get("/encounters/{encounter_id}/identity")
def get_identity_status(encounter_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    encounter = db.get(Encounter, encounter_id)
    if not encounter or encounter.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return identity_status(db, encounter_id)


@router.post("/encounters/{encounter_id}/identity/verify")
def verify_identity(encounter_id: UUID, payload: IdentityVerifyRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return verify_encounter_identity(db, encounter_id, user, confirmed=payload.confirmed, reason=payload.reason)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/documents/{document_id}/final-text", response_model=FinalTextResponse)
def final_text(document_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.get(ClinicalDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    sections = list(db.scalars(select(DocumentSection).where(DocumentSection.document_id == document_id).order_by(DocumentSection.sort_order)))
    parts = []
    for section in sections:
        content = section.physician_content if section.physician_content is not None else section.generated_content
        content = (content or "").strip()
        if content:
            parts.append(content)
    return {"document_id": doc.id, "document_type": doc.document_type, "status": doc.status, "text": "\n\n".join(parts)}

router.include_router(concurrency_routes.router)
