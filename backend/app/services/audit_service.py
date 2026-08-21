import re
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.services.state_version_service import document_state_status
from app.models import (
    ClinicalDocument, ClinicalFact, ClinicalProblem, Contradiction, DocumentSection, Encounter,
    Medication, MedicationState, PendingItem, Procedure, SafetyFlag, DispositionState,
)

AUDIT_VERSION = "audit-deterministic-v0.1"
BLOCKING = {"critical", "high"}
UNCERTAIN = {"possible", "suspected", "probable", "concern_for", "unclear"}
QUALIFIERS = ("possible", "possibly", "suspected", "probable", "likely", "concern for", "may have", "could be")
EXAM_PATTERNS = {
    "lungs_clear": (r"\blungs? (?:are )?(?:clear|ctab)\b", {"lungs_clear", "clear_to_auscultation", "ctab"}),
    "no_edema": (r"\bno (?:lower extremity |peripheral )?edema\b", {"no_edema", "edema"}),
    "regular_rhythm": (r"\b(?:rrr|regular rate and rhythm)\b", {"rrr", "regular_rate_rhythm"}),
    "abdomen_soft": (r"\babdomen (?:is )?soft\b", {"abdomen_soft"}),
    "neuro_intact": (r"\bneurolog(?:ically|ic) intact\b", {"neurologically_intact"}),
}


def _text(section: DocumentSection) -> str:
    return section.physician_content or section.current_generated_content or section.generated_content or ""


def _add(db, doc, section, category, severity, description, claim=None, evidence=None):
    flag = SafetyFlag(encounter_id=doc.encounter_id, document_id=doc.id, section_id=section.id if section else None,
                      category=category, severity=severity, description=description, claim_text=claim,
                      supporting_evidence=evidence or [], audit_version=AUDIT_VERSION)
    db.add(flag)
    return flag


def _value_strings(fact: ClinicalFact) -> set[str]:
    vals = set()
    if fact.value_text:
        vals.add(str(fact.value_text).lower())
    if fact.value_numeric is not None:
        n = Decimal(fact.value_numeric)
        vals.add(format(n, "f").rstrip("0").rstrip("."))
    return {v for v in vals if v}


def audit_document(db: Session, document_id: UUID) -> dict:
    doc = db.get(ClinicalDocument, document_id)
    if not doc:
        raise LookupError("Document not found")
    sections = list(db.scalars(select(DocumentSection).where(DocumentSection.document_id == doc.id).order_by(DocumentSection.sort_order)))
    db.execute(delete(SafetyFlag).where(SafetyFlag.document_id == doc.id, SafetyFlag.status == "open"))

    state_status = document_state_status(db, doc)
    if state_status["stale"]:
        _add(
            db, doc, None, "stale_clinical_state", "critical",
            f"Document was generated from MCIF state version {state_status['generated_state_version']}, but the encounter is now at version {state_status['current_state_version']}. Refresh and re-review the document before finalization.",
            evidence=state_status,
        )

    # Existing unresolved contradictions are always visible to the document audit.
    contradictions = list(db.scalars(select(Contradiction).where(Contradiction.encounter_id == doc.encounter_id, Contradiction.status == "unresolved")))
    for c in contradictions:
        sev = "high" if c.severity in {"high", "critical"} else "moderate"
        _add(db, doc, None, "unresolved_contradiction", sev, c.description or f"Unresolved {c.category} contradiction.", evidence={"contradiction_id": str(c.id)})

    problems = list(db.scalars(select(ClinicalProblem).where(ClinicalProblem.encounter_id == doc.encounter_id, ClinicalProblem.status != "resolved")))
    meds = list(db.scalars(select(Medication).where(Medication.encounter_id == doc.encounter_id)))
    pending = list(db.scalars(select(PendingItem).where(PendingItem.encounter_id == doc.encounter_id, PendingItem.status == "pending")))
    procedures = list(db.scalars(select(Procedure).where(Procedure.encounter_id == doc.encounter_id)))
    current_facts = list(db.scalars(select(ClinicalFact).where(ClinicalFact.encounter_id == doc.encounter_id, ClinicalFact.is_current == True)))  # noqa: E712
    old_facts = list(db.scalars(select(ClinicalFact).where(ClinicalFact.encounter_id == doc.encounter_id, ClinicalFact.is_current == False)))  # noqa: E712
    exam_concepts = {f.concept.lower() for f in current_facts if f.fact_type in {"exam", "physical_exam"}}

    for section in sections:
        text = _text(section)
        low = text.lower()

        # Diagnostic certainty cannot be silently strengthened.
        for p in problems:
            if p.certainty not in UNCERTAIN:
                continue
            names = {p.name.lower(), (p.normalized_name or "").replace("_", " ").lower()}
            names.discard("")
            for name in names:
                idx = low.find(name)
                if idx >= 0:
                    window = low[max(0, idx-35):idx+len(name)+10]
                    if not any(q in window for q in QUALIFIERS):
                        _add(db, doc, section, "certainty_mismatch", "high",
                             f"'{p.name}' is stored as {p.certainty}, but the section presents it without uncertainty language.",
                             claim=text[max(0, idx-35):idx+len(name)+35], evidence={"problem_id": str(p.id), "certainty": p.certainty})
                    break

        # Medication current-state conflicts.
        for med in meds:
            med_name = (med.display_name or med.normalized_name).lower()
            if med_name not in low:
                continue
            states = list(db.scalars(select(MedicationState).where(MedicationState.medication_id == med.id, MedicationState.is_current == True)))  # noqa: E712
            for state in states:
                if state.domain == "hospital" and state.status in {"held", "stopped", "not_administered"}:
                    conflict_match = re.search(rf"\b(?:continue|resume|restart|give|administer)\b[^.\n]{{0,60}}\b{re.escape(med_name)}\b|\b{re.escape(med_name)}\b[^.\n]{{0,60}}\b(?:continue|resume|restart)\b", low)
                    hold_language = re.search(rf"\bcontinue(?:\s+to)?\s+hold(?:ing)?\b[^.\n]{{0,60}}\b{re.escape(med_name)}\b|\b{re.escape(med_name)}\b[^.\n]{{0,60}}\bremain(?:s)?\s+held\b", low)
                    if conflict_match and not hold_language:
                        _add(db, doc, section, "medication_conflict", "critical",
                             f"{med.display_name or med.normalized_name} is currently {state.status} in the {state.domain} state, but the document implies active continuation/resumption.",
                             evidence={"medication_id": str(med.id), "state_id": str(state.id), "domain": state.domain, "status": state.status})
                if state.domain == "discharge" and state.status in {"unclear", "requires_decision"} and any(w in low for w in ("discharge", "home")):
                    if re.search(rf"\b{re.escape(med_name)}\b", low):
                        _add(db, doc, section, "medication_discharge_unresolved", "high",
                             f"Discharge state for {med.display_name or med.normalized_name} remains {state.status} and requires clinician review.",
                             evidence={"medication_id": str(med.id), "state_id": str(state.id)})

        # Unsupported templated physical exam statements.
        for label, (pattern, concepts) in EXAM_PATTERNS.items():
            match = re.search(pattern, low)
            if match and not (exam_concepts & concepts):
                _add(db, doc, section, "unsupported_exam", "high",
                     f"Physical exam claim '{match.group(0)}' is not supported by a current structured exam fact.", claim=match.group(0))

        # Pending items must not be described as final/completed when clearly named.
        for item in pending:
            key = item.description.lower().strip()
            if len(key) >= 4 and key in low and re.search(r"\b(?:final|finalized|completed|resulted|negative|positive)\b", low):
                _add(db, doc, section, "pending_result_issue", "high",
                     f"Pending item '{item.description}' appears in text that describes a final/completed state.", evidence={"pending_item_id": str(item.id)})

        # Planned/pending procedures cannot become completed/status-post claims.
        for proc in procedures:
            pname = proc.procedure_name.lower()
            if pname in low and proc.status in {"planned", "pending", "scheduled", "deferred"}:
                if re.search(rf"\b(?:status post|s/p|completed|underwent|performed)\b[^.\n]{{0,80}}\b{re.escape(pname)}\b|\b{re.escape(pname)}\b[^.\n]{{0,80}}\b(?:completed|performed)\b", low):
                    _add(db, doc, section, "procedure_state_error", "critical",
                         f"{proc.procedure_name} is {proc.status}, but the document implies it was completed.", evidence={"procedure_id": str(proc.id), "status": proc.status})

        # Discharge-specific completion and follow-up safeguards.
        if doc.document_type == "discharge":
            completion_patterns = [
                r"\bfollow[- ]?up (?:is )?scheduled\b",
                r"\bappointment (?:is )?scheduled\b",
                r"\bprescriptions? (?:were )?sent\b",
                r"\btransportation (?:was )?arranged\b",
                r"\bhome oxygen (?:was )?arranged\b",
                r"\bpatient (?:was )?educated\b",
                r"\breturn precautions (?:were )?reviewed\b",
                r"\bverbalized understanding\b",
            ]
            for pattern in completion_patterns:
                m = re.search(pattern, low)
                if m:
                    _add(db, doc, section, "unsupported_discharge_completion", "high",
                         "Discharge text claims a completed arrangement/education action that is not represented as a verified structured completion state.",
                         claim=m.group(0))
            if section.section_type == "disposition":
                disposition = list(db.scalars(select(DispositionState).where(DispositionState.encounter_id == doc.encounter_id).order_by(DispositionState.source_datetime.desc())))
                latest_dispo = disposition[0] if disposition else None
                if not latest_dispo or not latest_dispo.anticipated_destination:
                    _add(db, doc, section, "discharge_destination_unconfirmed", "high",
                         "Final discharge destination is not established in structured data.")

        # Signout-specific safeguard: code status may only appear when a current structured code-status fact exists.
        if doc.document_type == "signout" and section.section_type == "code_status":
            code_facts = [f for f in current_facts if (f.concept or "").lower().replace(" ", "_") in {"code_status", "resuscitation_status", "dnr_status"} and f.value_text]
            if not code_facts and re.search(r"\b(?:full code|dnr|dni|do not resuscitate|do not intubate)\b", low):
                _add(db, doc, section, "unsupported_code_status", "critical",
                     "Signout contains a code-status designation without a current structured code-status fact.")

        # Detect explicitly stale objective values when a newer current value exists.
        current_by_concept = {f.concept: f for f in current_facts}
        for old in old_facts:
            current = current_by_concept.get(old.concept)
            if not current:
                continue
            for old_val in _value_strings(old):
                if re.search(rf"(?<![\d.]){re.escape(old_val)}(?![\d.])", low) and not any(v in low for v in _value_strings(current)):
                    _add(db, doc, section, "temporal_conflict", "moderate",
                         f"Section contains an older {old.concept} value ({old_val}) without the newer current value.",
                         evidence={"old_fact_id": str(old.id), "current_fact_id": str(current.id)})
                    break

    db.commit()
    flags = list(db.scalars(select(SafetyFlag).where(SafetyFlag.document_id == doc.id, SafetyFlag.status == "open").order_by(SafetyFlag.created_at)))
    blocking = sum(1 for f in flags if f.severity in BLOCKING)
    warning = sum(1 for f in flags if f.severity == "moderate")
    info = sum(1 for f in flags if f.severity == "low")
    return {"document_id": doc.id, "status": "review_required" if blocking or warning else "pass", "blocking_flags": blocking,
            "warning_flags": warning, "informational_flags": info, "flags": flags, "audit_version": AUDIT_VERSION}


def list_flags(db: Session, document_id: UUID):
    if not db.get(ClinicalDocument, document_id):
        raise LookupError("Document not found")
    return list(db.scalars(select(SafetyFlag).where(SafetyFlag.document_id == document_id).order_by(SafetyFlag.created_at)))


def resolve_flag(db: Session, flag_id: UUID, resolution: str, actor_id: UUID | None = None, resolution_type: str = "physician_reviewed"):
    flag = db.get(SafetyFlag, flag_id)
    if not flag:
        raise LookupError("Safety flag not found")
    flag.status = "resolved"
    flag.resolution = f"{resolution_type}: {resolution}"
    flag.resolved_by = actor_id
    flag.resolved_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(flag)
    return flag


def refresh_document(db: Session, document_id: UUID, actor_id: UUID | None = None) -> dict:
    doc = db.get(ClinicalDocument, document_id)
    if not doc:
        raise LookupError("Document not found")
    if doc.status == "finalized":
        raise ValueError("Finalized documents are immutable; create a new document for newer clinical state")
    encounter = db.get(Encounter, doc.encounter_id)
    if not encounter:
        raise LookupError("Encounter not found")

    # Incorporate newly imported sources before regenerating the note.
    from app.services.analysis_service import analyze_encounter
    from app.services.progress_service import regenerate_progress_section
    analyze_encounter(db, doc.encounter_id)

    doc.status = "in_review"
    doc.approved_by = None
    doc.approved_at = None
    db.commit()

    sections = list(db.scalars(select(DocumentSection).where(DocumentSection.document_id == doc.id).order_by(DocumentSection.sort_order)))
    refreshed_ids = []
    for section in sections:
        regenerate_progress_section(db, doc.id, section.id, instruction="Refresh from newer MCIF state", actor_id=actor_id)
        refreshed_ids.append(section.id)

    encounter = db.get(Encounter, doc.encounter_id)
    doc = db.get(ClinicalDocument, doc.id)
    doc.generated_state_version = int(encounter.clinical_state_version or 1)
    doc.status = "in_review"
    db.commit(); db.refresh(doc)
    state_status = document_state_status(db, doc)
    return {
        "document_id": doc.id,
        "status": doc.status,
        **state_status,
        "refreshed_section_ids": refreshed_ids,
        "pending_review": True,
    }


def finalize_document(db: Session, document_id: UUID, actor_id: UUID | None = None, expected_document_version: int | None = None):
    doc = db.get(ClinicalDocument, document_id)
    if not doc:
        raise LookupError("Document not found")
    from app.services.concurrency_service import assert_version
    assert_version(expected_document_version, int(doc.edit_version or 1), "Document")
    if doc.status != "approved":
        raise ValueError("Document must be physician-approved before finalization")
    # Always audit the current approved text at finalization time.
    audit_document(db, document_id)
    blockers = list(db.scalars(select(SafetyFlag).where(SafetyFlag.document_id == document_id, SafetyFlag.status == "open", SafetyFlag.severity.in_(BLOCKING))))
    if blockers:
        return {"document_id": doc.id, "status": doc.status, "finalized_at": doc.finalized_at, "blocking_flag_ids": [f.id for f in blockers]}
    doc.status = "finalized"
    doc.finalized_at = datetime.now(timezone.utc)
    doc.edit_version = int(doc.edit_version or 1) + 1
    db.commit(); db.refresh(doc)
    return {"document_id": doc.id, "status": doc.status, "finalized_at": doc.finalized_at, "blocking_flag_ids": []}
