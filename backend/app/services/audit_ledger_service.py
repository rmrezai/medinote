import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent, ClinicalDocument, DocumentSection, Encounter, Organization, PhysicianEdit,
    SafetyFlag, SectionRevision, SourceDocument,
)

ZERO_HASH = "0" * 64


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True)


def safe_hash_text(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def event_payload(event: AuditEvent) -> dict:
    return {
        "organization_id": str(event.organization_id),
        "sequence_number": int(event.sequence_number),
        "user_id": str(event.user_id) if event.user_id else None,
        "encounter_id": str(event.encounter_id) if event.encounter_id else None,
        "event_type": event.event_type,
        "object_type": event.object_type,
        "object_id": str(event.object_id) if event.object_id else None,
        "metadata": event.metadata_json or {},
        "occurred_at": event.occurred_at.astimezone(timezone.utc).isoformat() if event.occurred_at.tzinfo else event.occurred_at.replace(tzinfo=timezone.utc).isoformat(),
        "previous_hash": event.previous_hash,
    }


def calculate_event_hash(event: AuditEvent) -> str:
    return hashlib.sha256(_canonical(event_payload(event)).encode("utf-8")).hexdigest()


def prepare_event_chain(db: Session, event: AuditEvent) -> AuditEvent:
    # Serialize audit appends per organization in databases that support row locks.
    # This prevents two simultaneous clinicians from receiving the same sequence number.
    db.scalar(select(Organization).where(Organization.id == event.organization_id).with_for_update())
    previous = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.organization_id == event.organization_id)
        .order_by(AuditEvent.sequence_number.desc())
        .limit(1)
    )
    event.sequence_number = (int(previous.sequence_number) + 1) if previous else 1
    event.previous_hash = previous.event_hash if previous else ZERO_HASH
    if event.occurred_at is None:
        event.occurred_at = datetime.now(timezone.utc)
    event.metadata_hash = hashlib.sha256(_canonical(event.metadata_json or {}).encode("utf-8")).hexdigest()
    event.event_hash = calculate_event_hash(event)
    return event


def verify_chain(db: Session, organization_id: UUID) -> dict:
    db.expire_all()
    events = list(db.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == organization_id)
        .order_by(AuditEvent.sequence_number.asc())
    ))
    prior = ZERO_HASH
    issues = []
    expected_seq = 1
    for event in events:
        if event.sequence_number != expected_seq:
            issues.append({"event_id": str(event.id), "issue": "sequence_gap", "expected": expected_seq, "actual": event.sequence_number})
        if event.previous_hash != prior:
            issues.append({"event_id": str(event.id), "issue": "previous_hash_mismatch"})
        expected_metadata_hash = hashlib.sha256(_canonical(event.metadata_json or {}).encode("utf-8")).hexdigest()
        if event.metadata_hash != expected_metadata_hash:
            issues.append({"event_id": str(event.id), "issue": "metadata_hash_mismatch"})
        expected_hash = calculate_event_hash(event)
        if event.event_hash != expected_hash:
            issues.append({"event_id": str(event.id), "issue": "event_hash_mismatch"})
        prior = event.event_hash
        expected_seq += 1
    return {
        "organization_id": str(organization_id),
        "events": len(events),
        "valid": len(issues) == 0,
        "head_hash": prior,
        "issues": issues,
    }


def encounter_forensic_export(db: Session, organization_id: UUID, encounter_id: UUID, include_content: bool = False) -> dict:
    encounter = db.get(Encounter, encounter_id)
    if not encounter or encounter.organization_id != organization_id:
        raise LookupError("Encounter not found")

    all_events = list(db.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == organization_id)
        .order_by(AuditEvent.sequence_number.asc())
    ))
    encounter_events = [e for e in all_events if e.encounter_id == encounter_id]
    sources = list(db.scalars(select(SourceDocument).where(SourceDocument.encounter_id == encounter_id).order_by(SourceDocument.imported_at)))
    documents = list(db.scalars(select(ClinicalDocument).where(ClinicalDocument.encounter_id == encounter_id).order_by(ClinicalDocument.generated_at)))

    doc_exports = []
    for doc in documents:
        sections = list(db.scalars(select(DocumentSection).where(DocumentSection.document_id == doc.id).order_by(DocumentSection.sort_order)))
        revisions = list(db.scalars(select(SectionRevision).where(SectionRevision.document_id == doc.id).order_by(SectionRevision.created_at)))
        edits = list(db.scalars(select(PhysicianEdit).where(PhysicianEdit.document_id == doc.id).order_by(PhysicianEdit.edited_at)))
        flags = list(db.scalars(select(SafetyFlag).where(SafetyFlag.document_id == doc.id).order_by(SafetyFlag.created_at)))
        final_text = "\n\n".join((s.physician_content if s.physician_content is not None else (s.current_generated_content or s.generated_content or "")).strip() for s in sections if (s.physician_content if s.physician_content is not None else (s.current_generated_content or s.generated_content or "")).strip())
        doc_exports.append({
            "document_id": str(doc.id),
            "document_type": doc.document_type,
            "variant": doc.variant,
            "status": doc.status,
            "generator_version": doc.generator_version,
            "generated_state_version": doc.generated_state_version,
            "edit_version": doc.edit_version,
            "generated_by": str(doc.generated_by) if doc.generated_by else None,
            "approved_by": str(doc.approved_by) if doc.approved_by else None,
            "generated_at": doc.generated_at,
            "approved_at": doc.approved_at,
            "finalized_at": doc.finalized_at,
            "final_text_sha256": safe_hash_text(final_text),
            **({"final_text": final_text} if include_content else {}),
            "sections": [{
                "section_id": str(s.id),
                "section_type": s.section_type,
                "section_key": s.section_key,
                "approval_status": s.approval_status,
                "generated_sha256": safe_hash_text(s.generated_content),
                "current_generated_sha256": safe_hash_text(s.current_generated_content),
                "physician_content_sha256": safe_hash_text(s.physician_content),
                **({"generated_content": s.generated_content, "current_generated_content": s.current_generated_content, "physician_content": s.physician_content} if include_content else {}),
                "edit_version": s.edit_version,
                "approved_by": str(s.approved_by) if s.approved_by else None,
                "approved_at": s.approved_at,
            } for s in sections],
            "revisions": [{
                "revision_id": str(r.id), "section_id": str(r.section_id), "revision_number": r.revision_number,
                "content_sha256": safe_hash_text(r.content), "instruction_sha256": safe_hash_text(r.instruction),
                "generator_version": r.generator_version, "created_by": str(r.created_by) if r.created_by else None,
                "created_at": r.created_at,
            } for r in revisions],
            "physician_edits": [{
                "edit_id": str(e.id), "section_id": str(e.section_id), "action": e.action,
                "original_generated_sha256": safe_hash_text(e.original_generated_content),
                "active_generated_sha256": safe_hash_text(e.active_generated_content),
                "prior_physician_sha256": safe_hash_text(e.prior_physician_content),
                "final_physician_sha256": safe_hash_text(e.final_physician_content),
                "edited_by": str(e.edited_by) if e.edited_by else None, "edited_at": e.edited_at,
            } for e in edits],
            "safety_flags": [{
                "flag_id": str(f.id), "category": f.category, "severity": f.severity, "status": f.status,
                "audit_version": f.audit_version, "resolved_by": str(f.resolved_by) if f.resolved_by else None,
                "created_at": f.created_at, "resolved_at": f.resolved_at,
            } for f in flags],
        })

    export = {
        "format": "medinote-forensic-export-v0.1",
        "organization_id": str(organization_id),
        "encounter_id": str(encounter_id),
        "clinical_state_version": encounter.clinical_state_version,
        "generated_at": datetime.now(timezone.utc),
        "include_content": include_content,
        "encounter_event_ids": [str(e.id) for e in encounter_events],
        "audit_chain": [{
            "id": str(e.id), "sequence_number": e.sequence_number, "event_type": e.event_type,
            "user_id": str(e.user_id) if e.user_id else None, "object_type": e.object_type,
            "object_id": str(e.object_id) if e.object_id else None, "metadata": e.metadata_json or {},
            "metadata_hash": e.metadata_hash, "previous_hash": e.previous_hash, "event_hash": e.event_hash,
            "occurred_at": e.occurred_at,
        } for e in all_events],
        "source_manifest": [{
            "source_id": str(s.id), "document_type": s.document_type, "source_datetime": s.source_datetime,
            "imported_at": s.imported_at, "content_hash": s.content_hash, "identity_status": s.identity_status,
            **({"raw_text": s.raw_text} if include_content else {}),
        } for s in sources],
        "documents": doc_exports,
    }
    export["export_sha256"] = hashlib.sha256(_canonical(export).encode("utf-8")).hexdigest()
    return export
