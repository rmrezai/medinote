from __future__ import annotations

from datetime import datetime, timezone
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.state_version_service import document_state_status
from app.services.concurrency_service import assert_version, bump_document, bump_section
from app.models import (
    Encounter,
    ClinicalDocument, DocumentSection, ClinicalProblem, ProblemEvidence,
    ClinicalFact, Contradiction, SectionRevision, PhysicianEdit,
)
from app.services.overview_service import build_patient_overview


ALLOWED_VARIANTS = {"standard", "daily", "short", "mini", "complex", "interval"}
GENERATOR_VERSION = "progress-deterministic-v0.2"
SECTION_READY_STATES = {"accepted", "edited"}


def _active_generated(section: DocumentSection) -> str:
    return section.current_generated_content if section.current_generated_content is not None else section.generated_content


def _evidence_phrase(evidence: list[dict]) -> str:
    pieces = []
    for item in evidence[:4]:
        concept = item.get("concept") or "evidence"
        value = item.get("value")
        pieces.append(f"{concept} {value}" if value else concept)
    return "; ".join(pieces)


def _problem_text(problem: dict) -> str:
    label = problem["name"]
    certainty = problem.get("certainty")
    status = problem.get("status")
    title_bits = [label]
    if certainty and certainty not in {"confirmed", "unclear"}:
        title_bits.append(f"({certainty})")
    if status and status not in {"active", "new"}:
        title_bits.append(f"- {status}")
    title = " ".join(title_bits)
    ev = _evidence_phrase(problem.get("evidence", []))
    if ev:
        return f"{title}\nObjective evidence: {ev}."
    return f"{title}\nNo structured supporting evidence is currently linked; physician review required."


def _interval_hpi(overview: dict) -> str:
    picture = overview["current_clinical_picture"].strip()
    # Patient Overview may contain a second Review sentence; the Progress contract requires
    # exactly two HPI sentences, so keep only the clinical-picture sentence here.
    first = re.split(r"(?<=[.!?])\s+", picture, maxsplit=1)[0].strip()
    if not first.endswith("."):
        first += "."
    needs = []
    counts = overview["attention_counts"]
    if counts.get("unresolved_medications"):
        needs.append(f'{counts["unresolved_medications"]} unresolved medication decision(s)')
    if counts.get("pending_items"):
        needs.append(f'{counts["pending_items"]} pending item(s)')
    if counts.get("unresolved_contradictions"):
        needs.append(f'{counts["unresolved_contradictions"]} unresolved contradiction(s)')
    second = "Current review needs include " + ", ".join(needs) + "." if needs else "No structured review flags are currently open."
    return f"{first} {second}"


def _disposition_text(overview: dict) -> str:
    disposition = overview.get("disposition")
    if not disposition:
        return "Disposition: no structured disposition state is currently documented."
    parts = []
    if disposition.get("anticipated_destination"):
        parts.append(f'anticipated destination: {disposition["anticipated_destination"]}')
    barriers = disposition.get("current_barriers")
    if barriers:
        parts.append(f"current barriers: {barriers}")
    if disposition.get("pt_recommendation"):
        parts.append(f'PT: {disposition["pt_recommendation"]}')
    if disposition.get("oxygen_need"):
        parts.append(f'oxygen need: {disposition["oxygen_need"]}')
    return "Disposition: " + ("; ".join(parts) if parts else "structured disposition record present without a documented destination/barrier summary") + "."


def _problem_evidence(db: Session, problem_id: UUID) -> list[dict]:
    evidence = []
    for link in db.scalars(select(ProblemEvidence).where(ProblemEvidence.problem_id == problem_id)):
        fact = db.get(ClinicalFact, link.fact_id)
        if fact:
            val = str(fact.value_numeric) if fact.value_numeric is not None else fact.value_text
            if val and fact.units:
                val = f"{val} {fact.units}"
            evidence.append({
                "fact_id": fact.id,
                "concept": fact.concept,
                "value": val,
                "observed_datetime": fact.observed_datetime,
                "source_document_id": fact.source_document_id,
            })
    return evidence


def _section_dict(db: Session, section: DocumentSection) -> dict:
    problem_id = None
    evidence = []
    if section.section_type in {"assessment_plan_problem", "hospital_course_problem"} and section.section_key:
        try:
            problem_id = UUID(section.section_key)
        except ValueError:
            problem_id = None
        if problem_id:
            evidence = _problem_evidence(db, problem_id)
    return {
        "id": section.id,
        "section_type": section.section_type,
        "section_key": section.section_key,
        "sort_order": section.sort_order,
        "generated_content": _active_generated(section),
        "original_generated_content": section.generated_content,
        "physician_content": section.physician_content,
        "approval_status": section.approval_status,
        "regeneration_count": section.regeneration_count,
        "edit_version": int(section.edit_version or 1),
        "problem_id": problem_id,
        "evidence": evidence,
    }


def _review_reasons(db: Session, doc: ClinicalDocument) -> list[str]:
    overview = build_patient_overview(db, doc.encounter_id)
    reasons = []
    if overview["contradictions"]:
        reasons.append(f'{len(overview["contradictions"])} unresolved contradiction(s) remain in the encounter state.')
    if overview["attention_counts"].get("unresolved_medications"):
        reasons.append(f'{overview["attention_counts"]["unresolved_medications"]} medication decision(s) remain unresolved.')
    for problem in overview["problems"]:
        if not problem.get("evidence"):
            reasons.append(f'Problem "{problem["name"]}" has no linked structured evidence.')
    return reasons


def generate_progress_document(db: Session, encounter_id: UUID, variant: str = "daily", generated_by: UUID | None = None) -> dict:
    variant = variant.lower().strip()
    if variant not in ALLOWED_VARIANTS:
        raise ValueError(f"Unsupported progress note variant: {variant}")

    overview = build_patient_overview(db, encounter_id)
    doc = ClinicalDocument(encounter_id=encounter_id, document_type="progress", variant=variant, status="draft", generator_version=GENERATOR_VERSION, generated_by=generated_by, generated_state_version=int(db.get(Encounter, encounter_id).clinical_state_version or 1))
    db.add(doc); db.flush()

    order = 10
    sections = []
    hpi = DocumentSection(document_id=doc.id, section_type="interval_hpi", section_key="interval_hpi", sort_order=order, generated_content=_interval_hpi(overview))
    db.add(hpi); db.flush(); sections.append(hpi); order += 10

    problems = overview["problems"]
    if variant == "mini":
        problems = problems[:3]
    elif variant == "short":
        problems = problems[:5]

    for problem in problems:
        section = DocumentSection(document_id=doc.id, section_type="assessment_plan_problem", section_key=str(problem["id"]), sort_order=order, generated_content=_problem_text(problem))
        db.add(section); db.flush(); sections.append(section); order += 10

    dispo = DocumentSection(document_id=doc.id, section_type="disposition", section_key="disposition", sort_order=order, generated_content=_disposition_text(overview))
    db.add(dispo); db.flush(); sections.append(dispo)
    db.commit(); db.refresh(doc)

    reasons = _review_reasons(db, doc)
    return {
        "document_id": doc.id, "encounter_id": doc.encounter_id, "document_type": doc.document_type,
        "variant": doc.variant, "status": doc.status, "generator_version": doc.generator_version,
        "generated_at": doc.generated_at, "approved_at": doc.approved_at,
        **document_state_status(db, doc),
        "edit_version": int(doc.edit_version or 1),
        "sections": [_section_dict(db, s) for s in sections],
        "review_required": bool(reasons), "review_reasons": reasons,
    }


def get_progress_document(db: Session, document_id: UUID) -> dict:
    doc = db.get(ClinicalDocument, document_id)
    if not doc or doc.document_type not in {"progress", "hp", "discharge", "signout"}:
        raise LookupError("Reviewable document not found")
    sections = list(db.scalars(select(DocumentSection).where(DocumentSection.document_id == document_id).order_by(DocumentSection.sort_order.asc())))
    reasons = _review_reasons(db, doc)
    return {
        "document_id": doc.id, "encounter_id": doc.encounter_id, "document_type": doc.document_type,
        "variant": doc.variant or "daily", "status": doc.status, "generator_version": doc.generator_version,
        "generated_at": doc.generated_at, "approved_at": doc.approved_at,
        **document_state_status(db, doc),
        "edit_version": int(doc.edit_version or 1),
        "sections": [_section_dict(db, s) for s in sections],
        "review_required": bool(reasons), "review_reasons": reasons,
    }


def _log_edit(db: Session, doc: ClinicalDocument, section: DocumentSection, action: str, prior: str | None, final: str | None, actor_id: UUID | None = None, instruction: str | None = None) -> None:
    db.add(PhysicianEdit(
        document_id=doc.id,
        section_id=section.id,
        action=action,
        original_generated_content=section.generated_content,
        active_generated_content=_active_generated(section),
        prior_physician_content=prior,
        final_physician_content=final,
        instruction=instruction,
        edited_by=actor_id,
    ))


def update_progress_section(db: Session, document_id: UUID, section_id: UUID, physician_content: str | None, action: str, actor_id: UUID | None = None, expected_section_version: int | None = None, expected_document_version: int | None = None) -> dict:
    doc = db.get(ClinicalDocument, document_id)
    section = db.get(DocumentSection, section_id)
    if not doc or doc.document_type not in {"progress", "hp", "discharge", "signout"} or not section or section.document_id != document_id:
        raise LookupError("Document section not found")
    assert_version(expected_document_version, int(doc.edit_version or 1), "Document")
    assert_version(expected_section_version, int(section.edit_version or 1), "Section")
    if doc.status in {"approved", "finalized"}:
        raise ValueError("Approved/finalized documents cannot be edited without reopening")
    action = action.lower().strip()
    if action not in {"edit", "accept"}:
        raise ValueError("Section action must be 'edit' or 'accept'")
    prior = section.physician_content
    if action == "edit":
        if physician_content is None or not physician_content.strip():
            raise ValueError("physician_content is required for edit")
        section.physician_content = physician_content
        section.approval_status = "edited"
    else:
        section.physician_content = physician_content if physician_content is not None else _active_generated(section)
        section.approval_status = "accepted"
    section.approved_by = actor_id
    section.approved_at = datetime.now(timezone.utc)
    doc.status = "in_review"
    bump_section(section); bump_document(doc)
    _log_edit(db, doc, section, action, prior, section.physician_content, actor_id)
    db.commit(); db.refresh(section)
    return _section_dict(db, section)


def _regenerated_content(db: Session, doc: ClinicalDocument, section: DocumentSection) -> str:
    overview = build_patient_overview(db, doc.encounter_id)
    if section.section_type == "interval_hpi":
        return _interval_hpi(overview)
    if section.section_type == "disposition":
        return _disposition_text(overview)
    if section.section_type in {"assessment_plan_problem", "hospital_course_problem"} and section.section_key:
        problem = next((p for p in overview["problems"] if str(p["id"]) == section.section_key), None)
        if not problem:
            return "Problem is no longer present in the active structured problem state; physician review required."
        return _problem_text(problem)
    return _active_generated(section)


def regenerate_progress_section(db: Session, document_id: UUID, section_id: UUID, instruction: str | None = None, actor_id: UUID | None = None, expected_section_version: int | None = None, expected_document_version: int | None = None) -> dict:
    doc = db.get(ClinicalDocument, document_id)
    section = db.get(DocumentSection, section_id)
    if not doc or doc.document_type not in {"progress", "hp", "discharge", "signout"} or not section or section.document_id != document_id:
        raise LookupError("Document section not found")
    assert_version(expected_document_version, int(doc.edit_version or 1), "Document")
    assert_version(expected_section_version, int(section.edit_version or 1), "Section")
    if doc.status in {"approved", "finalized"}:
        raise ValueError("Approved/finalized documents cannot be regenerated without reopening")

    prior_physician = section.physician_content
    if doc.document_type == "hp":
        from app.services.hp_service import regenerate_hp_content
        new_content = regenerate_hp_content(db, doc, section)
        generator_version = "hp-deterministic-v0.1"
    elif doc.document_type == "discharge":
        from app.services.discharge_service import regenerate_discharge_content
        new_content = regenerate_discharge_content(db, doc, section)
        generator_version = "discharge-deterministic-v0.1"
    elif doc.document_type == "signout":
        from app.services.signout_service import regenerate_signout_content
        new_content = regenerate_signout_content(db, doc, section)
        generator_version = "signout-deterministic-v0.1"
    else:
        new_content = _regenerated_content(db, doc, section)
        generator_version = GENERATOR_VERSION
    revision_number = section.regeneration_count + 1
    db.add(SectionRevision(
        document_id=doc.id, section_id=section.id, revision_number=revision_number,
        content=new_content, instruction=instruction, generator_version=generator_version,
        created_by=actor_id,
    ))
    section.current_generated_content = new_content
    section.regeneration_count = revision_number
    section.physician_content = None
    section.approval_status = "pending"
    section.approved_by = None
    section.approved_at = None
    doc.status = "in_review"
    bump_section(section); bump_document(doc)
    _log_edit(db, doc, section, "regenerate", prior_physician, None, actor_id, instruction)
    db.commit(); db.refresh(section)
    return _section_dict(db, section)


def approve_progress_document(db: Session, document_id: UUID, actor_id: UUID | None = None, expected_document_version: int | None = None) -> dict:
    doc = db.get(ClinicalDocument, document_id)
    if not doc or doc.document_type not in {"progress", "hp", "discharge", "signout"}:
        raise LookupError("Reviewable document not found")
    assert_version(expected_document_version, int(doc.edit_version or 1), "Document")
    sections = list(db.scalars(select(DocumentSection).where(DocumentSection.document_id == document_id)))
    pending = [s.id for s in sections if s.approval_status not in SECTION_READY_STATES]
    if pending:
        return {"document_id": doc.id, "status": doc.status, "approved_at": doc.approved_at, "edit_version": int(doc.edit_version or 1), "pending_section_ids": pending}
    doc.status = "approved"
    doc.approved_by = actor_id
    doc.approved_at = datetime.now(timezone.utc)
    bump_document(doc)
    db.commit(); db.refresh(doc)
    return {"document_id": doc.id, "status": doc.status, "approved_at": doc.approved_at, "edit_version": int(doc.edit_version or 1), "pending_section_ids": []}


def list_physician_edits(db: Session, document_id: UUID) -> list[PhysicianEdit]:
    doc = db.get(ClinicalDocument, document_id)
    if not doc:
        raise LookupError("Document not found")
    return list(db.scalars(select(PhysicianEdit).where(PhysicianEdit.document_id == document_id).order_by(PhysicianEdit.edited_at.asc())))
