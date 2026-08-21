from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.state_version_service import bump_state_version
from app.models import (
    ClinicalDocument, ClinicalFact, ConsultantRecommendation, Contradiction,
    DocumentSection, Encounter, Medication, MedicationState,
)
from app.services.audit_service import audit_document
from app.services.progress_service import regenerate_progress_section

ACTION_RE = re.compile(r"\b(?P<action>hold|continue|resume|restart|stop|discontinue)\s+(?P<target>[a-zA-Z][a-zA-Z0-9_-]{1,40})", re.I)


def _source_text(db: Session, c: Contradiction, which: str) -> tuple[str | None, str | None, UUID | None]:
    stype = getattr(c, f"source_{which}_type")
    sid = getattr(c, f"source_{which}_id")
    if not sid:
        sid = getattr(c, f"fact_{which}_id")
        stype = stype or ("clinical_fact" if sid else None)
    if not sid or not stype:
        return None, None, None
    if stype == "clinical_fact":
        row = db.get(ClinicalFact, sid)
        if not row:
            return stype, None, sid
        value = row.value_text if row.value_text is not None else (str(row.value_numeric) if row.value_numeric is not None else row.concept)
        return stype, f"{row.concept}: {value}", sid
    if stype == "consultant_recommendation":
        row = db.get(ConsultantRecommendation, sid)
        if not row:
            return stype, None, sid
        return stype, row.recommendation or row.assessment or row.service, sid
    return stype, None, sid


def _apply_fact_selection(db: Session, selected_id: UUID, other_id: UUID | None) -> None:
    selected = db.get(ClinicalFact, selected_id)
    if not selected:
        raise ValueError("Selected fact is unavailable")
    selected.is_current = True
    selected.fact_state = "current"
    selected.superseded_by = None
    if other_id:
        other = db.get(ClinicalFact, other_id)
        if other:
            other.is_current = False
            other.fact_state = "historical"
            other.superseded_by = selected.id


def _find_or_create_medication(db: Session, encounter_id: UUID, name: str) -> Medication:
    normalized = name.strip().lower()
    med = db.scalar(select(Medication).where(Medication.encounter_id == encounter_id, Medication.normalized_name == normalized))
    if med:
        return med
    med = Medication(encounter_id=encounter_id, normalized_name=normalized, display_name=name.strip())
    db.add(med); db.flush()
    return med


def _apply_physician_medication_decision(db: Session, encounter_id: UUID, decision_text: str, actor_id: UUID) -> UUID | None:
    m = ACTION_RE.search(decision_text or "")
    if not m:
        return None
    action = m.group("action").lower()
    action = {"restart": "resume", "discontinue": "stop"}.get(action, action)
    status_map = {"hold": "held", "continue": "ordered", "resume": "resumed", "stop": "stopped"}
    med = _find_or_create_medication(db, encounter_id, m.group("target"))
    current = list(db.scalars(select(MedicationState).where(
        MedicationState.medication_id == med.id,
        MedicationState.domain == "hospital",
        MedicationState.is_current.is_(True),
    )))
    for row in current:
        row.is_current = False
    state = MedicationState(
        medication_id=med.id,
        domain="hospital",
        status=status_map[action],
        effective_datetime=datetime.now(timezone.utc),
        reason="Physician adjudication of conflicting clinical recommendations",
        is_current=True,
        physician_confirmed=True,
        confirmed_by=actor_id,
        confirmed_at=datetime.now(timezone.utc),
    )
    db.add(state); db.flush()
    return state.id


def _resolve_consult_sources(db: Session, selected_id: UUID | None, other_id: UUID | None) -> None:
    if selected_id:
        selected = db.get(ConsultantRecommendation, selected_id)
        if selected:
            selected.conflict_status = "resolved"
            selected.current_relevance = "physician_selected"
    if other_id:
        other = db.get(ConsultantRecommendation, other_id)
        if other:
            other.conflict_status = "resolved"
            other.current_relevance = "superseded_by_physician_adjudication"


def _regenerate_affected_documents(db: Session, encounter_id: UUID, actor_id: UUID) -> tuple[list[UUID], list[UUID], dict[str, str]]:
    documents = list(db.scalars(select(ClinicalDocument).where(
        ClinicalDocument.encounter_id == encounter_id,
        ClinicalDocument.document_type.in_(["progress", "signout"]),
        ClinicalDocument.status.in_(["draft", "in_review"]),
    )))
    affected_docs: list[UUID] = []
    sections: list[UUID] = []
    audit_status: dict[str, str] = {}
    for doc in documents:
        affected_docs.append(doc.id)
        doc_sections = list(db.scalars(select(DocumentSection).where(DocumentSection.document_id == doc.id).order_by(DocumentSection.sort_order)))
        for section in doc_sections:
            regenerate_progress_section(db, doc.id, section.id, instruction="Regenerated after physician contradiction adjudication", actor_id=actor_id)
            sections.append(section.id)
        encounter = db.get(Encounter, encounter_id)
        doc = db.get(ClinicalDocument, doc.id)
        doc.generated_state_version = int(encounter.clinical_state_version or 1)
        db.commit()
        result = audit_document(db, doc.id)
        audit_status[str(doc.id)] = result["status"]
    return affected_docs, sections, audit_status


def adjudicate_contradiction(db: Session, contradiction_id: UUID, resolution_type: str, reason: str, actor_id: UUID, decision_text: str | None = None, expected_revision: int | None = None) -> dict:
    c = db.get(Contradiction, contradiction_id)
    if not c:
        raise LookupError("Contradiction not found")
    from app.services.concurrency_service import assert_version
    assert_version(expected_revision, int(c.revision or 1), "Contradiction")
    if c.status != "unresolved":
        raise ValueError("Contradiction is already resolved")
    encounter = db.get(Encounter, c.encounter_id)
    if not encounter:
        raise LookupError("Encounter not found")

    type_a, text_a, id_a = _source_text(db, c, "a")
    type_b, text_b, id_b = _source_text(db, c, "b")

    if resolution_type == "select_source_a":
        selected_type, selected_id, selected_text = type_a, id_a, text_a
        other_type, other_id = type_b, id_b
    elif resolution_type == "select_source_b":
        selected_type, selected_id, selected_text = type_b, id_b, text_b
        other_type, other_id = type_a, id_a
    elif resolution_type == "new_clinical_decision":
        if not decision_text or not decision_text.strip():
            raise ValueError("decision_text is required for a new clinical decision")
        selected_type, selected_id, selected_text = "physician_decision", None, decision_text.strip()
        other_type, other_id = None, None
    else:
        raise ValueError("Unsupported resolution_type")

    if resolution_type.startswith("select_source") and (not selected_type or not selected_id):
        raise ValueError("Selected contradiction source is unavailable")

    if selected_type == "clinical_fact":
        _apply_fact_selection(db, selected_id, other_id if other_type == "clinical_fact" else None)
    elif selected_type == "consultant_recommendation":
        _resolve_consult_sources(db, selected_id, other_id if other_type == "consultant_recommendation" else None)
    elif selected_type == "physician_decision":
        # Mark both consultant sources as reviewed when this is a consultant conflict.
        if type_a == "consultant_recommendation" or type_b == "consultant_recommendation":
            _resolve_consult_sources(db, None, id_a if type_a == "consultant_recommendation" else None)
            _resolve_consult_sources(db, None, id_b if type_b == "consultant_recommendation" else None)

    decision_fact = ClinicalFact(
        encounter_id=c.encounter_id,
        fact_type="physician_adjudication",
        concept=f"contradiction_resolution:{c.id}",
        value_text=selected_text or decision_text or "Physician adjudication",
        evidence_text=reason,
        observed_datetime=datetime.now(timezone.utc),
        source_datetime=datetime.now(timezone.utc),
        fact_state="current",
        confidence="high",
        source_category="physician_decision",
        is_current=True,
        extracted_by="physician_adjudication",
        extraction_version="adjudication-0.1",
    )
    db.add(decision_fact); db.flush()

    # A physician-selected consultant recommendation/new medication decision becomes a confirmed hospital medication decision when parsable.
    if selected_text and (selected_type in {"consultant_recommendation", "physician_decision"}):
        _apply_physician_medication_decision(db, c.encounter_id, selected_text, actor_id)

    c.status = "resolved"
    bump_state_version(db, c.encounter_id)
    c.physician_resolution = selected_text or decision_text or "Resolved by physician"
    c.resolution_type = resolution_type
    c.adjudication_reason = reason
    c.decision_fact_id = decision_fact.id
    c.resolved_by = actor_id
    c.resolved_at = datetime.now(timezone.utc)
    c.revision = int(c.revision or 1) + 1
    db.commit()

    affected_docs, regenerated_sections, audits = _regenerate_affected_documents(db, c.encounter_id, actor_id)
    db.refresh(c)
    return {
        "contradiction_id": c.id,
        "status": c.status,
        "physician_resolution": c.physician_resolution,
        "resolution_type": c.resolution_type,
        "decision_fact_id": c.decision_fact_id,
        "affected_document_ids": affected_docs,
        "regenerated_section_ids": regenerated_sections,
        "audit_status_by_document": audits,
    }


def contradiction_detail(db: Session, contradiction_id: UUID) -> dict:
    c = db.get(Contradiction, contradiction_id)
    if not c:
        raise LookupError("Contradiction not found")
    type_a, text_a, id_a = _source_text(db, c, "a")
    type_b, text_b, id_b = _source_text(db, c, "b")
    return {
        "id": c.id, "encounter_id": c.encounter_id, "category": c.category,
        "description": c.description, "severity": c.severity, "status": c.status,
        "source_a": {"type": type_a, "id": id_a, "text": text_a},
        "source_b": {"type": type_b, "id": id_b, "text": text_b},
        "physician_resolution": c.physician_resolution, "resolution_type": c.resolution_type,
        "adjudication_reason": c.adjudication_reason, "decision_fact_id": c.decision_fact_id, "revision": int(c.revision or 1),
    }
