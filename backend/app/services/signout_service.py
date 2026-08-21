from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.state_version_service import document_state_status
from app.models import (
    Encounter,
    ClinicalDocument, DocumentSection, ClinicalFact, Medication, MedicationState,
)
from app.services.overview_service import build_patient_overview
from app.services.progress_service import _section_dict

ALLOWED_VARIANTS = {"standard", "night", "weekend", "short", "complex"}
GENERATOR_VERSION = "signout-deterministic-v0.1"


def _qualifier(certainty: str | None) -> str:
    if certainty in {None, "confirmed", "unclear"}:
        return ""
    return f" ({certainty})"


def _one_liner(overview: dict) -> str:
    problems = overview.get("problems", [])
    if not problems:
        return "Current signout: no active structured clinical problem is established; physician review required."
    top = problems[:3]
    labels = []
    for p in top:
        label = f'{p["name"]}{_qualifier(p.get("certainty"))}'
        if p.get("status") not in {None, "active", "new"}:
            label += f' - {p["status"]}'
        labels.append(label)
    summary = "; ".join(labels)
    counts = overview.get("attention_counts", {})
    needs = []
    if counts.get("pending_items"):
        needs.append(f'{counts["pending_items"]} pending item(s)')
    if counts.get("unresolved_medications"):
        needs.append(f'{counts["unresolved_medications"]} unresolved medication decision(s)')
    if counts.get("unresolved_contradictions"):
        needs.append(f'{counts["unresolved_contradictions"]} unresolved contradiction(s)')
    suffix = f" Review needs: {', '.join(needs)}." if needs else ""
    return f"Current signout: {summary}.{suffix}"


def _active_problem_text(problem: dict) -> str:
    title = f'{problem["name"]}{_qualifier(problem.get("certainty"))}'
    status = problem.get("status")
    if status not in {None, "active", "new"}:
        title += f" - {status}"
    evidence = problem.get("evidence") or []
    ev = []
    for item in evidence[:3]:
        concept = item.get("concept") or "evidence"
        value = item.get("value")
        ev.append(f"{concept} {value}" if value else concept)
    if ev:
        return f"{title}\nCurrent evidence: {'; '.join(ev)}."
    return f"{title}\nNo linked structured evidence is currently available; physician review required."


def _current_treatment_text(db: Session, encounter_id: UUID) -> str:
    meds = list(db.scalars(select(Medication).where(Medication.encounter_id == encounter_id)))
    rows = []
    for med in meds:
        states = list(db.scalars(select(MedicationState).where(
            MedicationState.medication_id == med.id,
            MedicationState.is_current == True,  # noqa: E712
        )))
        hospital = next((s for s in states if s.domain == "hospital"), None)
        if not hospital:
            continue
        name = med.display_name or med.normalized_name
        detail = f"{name}: {hospital.status}"
        if hospital.reason:
            detail += f" ({hospital.reason})"
        rows.append(detail)
    if not rows:
        return "Current treatment/medications: no current structured hospital medication states are available; physician review required."
    return "Current treatment/medications:\n- " + "\n- ".join(rows[:12])


def _pending_text(overview: dict) -> str:
    items = overview.get("pending_items") or []
    if not items:
        return "Pending studies/items: none are currently represented in structured data."
    lines = []
    for item in items[:12]:
        line = item.get("description") or item.get("item_type") or "Pending item"
        if item.get("clinical_significance"):
            line += f' - significance: {item["clinical_significance"]}'
        if item.get("owner"):
            line += f' - owner: {item["owner"]}'
        lines.append(line)
    return "Pending studies/items:\n- " + "\n- ".join(lines)


def _overnight_risks(overview: dict) -> str:
    risks = []
    for p in overview.get("problems", [])[:5]:
        if p.get("status") in {"worsening", "new"} or (p.get("acuity_rank") is not None and p.get("acuity_rank") <= 3):
            risks.append(f'{p["name"]}: current status {p.get("status") or "active"}.')
    counts = overview.get("attention_counts", {})
    if counts.get("unresolved_medications"):
        risks.append(f'{counts["unresolved_medications"]} unresolved medication decision(s) require cross-cover awareness.')
    if counts.get("unresolved_contradictions"):
        risks.append(f'{counts["unresolved_contradictions"]} unresolved contradiction(s) remain in the chart state.')
    if not risks:
        return "Overnight risks: no specific structured overnight risk is established; physician should add case-specific risks if applicable."
    return "Overnight risks:\n- " + "\n- ".join(risks)


def _contingencies() -> str:
    return (
        "If/then contingencies: no physician-approved structured contingency orders are currently stored. "
        "Add only case-specific contingencies that reflect the treating clinician's plan; MediNote does not invent treatment thresholds or orders."
    )


def _code_status(db: Session, encounter_id: UUID) -> str:
    facts = list(db.scalars(select(ClinicalFact).where(
        ClinicalFact.encounter_id == encounter_id,
        ClinicalFact.is_current == True,  # noqa: E712
    )))
    for fact in facts:
        concept = (fact.concept or "").lower().replace(" ", "_")
        if concept in {"code_status", "resuscitation_status", "dnr_status"} and fact.value_text:
            return f"Code status: {fact.value_text}."
    return "Code status: not included because no current documented structured code-status fact is available."


def _disposition(overview: dict) -> str:
    d = overview.get("disposition")
    if not d:
        return "Disposition: no structured disposition state is currently documented."
    bits = []
    if d.get("anticipated_destination"):
        bits.append(f'anticipated destination: {d["anticipated_destination"]}')
    if d.get("current_barriers"):
        bits.append(f'barriers: {d["current_barriers"]}')
    if d.get("pt_recommendation"):
        bits.append(f'PT: {d["pt_recommendation"]}')
    return "Disposition: " + ("; ".join(bits) if bits else "structured disposition record present without a documented destination/barrier summary") + "."


def generate_signout_document(db: Session, encounter_id: UUID, variant: str = "standard", generated_by: UUID | None = None) -> dict:
    variant = variant.lower().strip()
    if variant not in ALLOWED_VARIANTS:
        raise ValueError(f"Unsupported signout variant: {variant}")
    overview = build_patient_overview(db, encounter_id)
    doc = ClinicalDocument(
        encounter_id=encounter_id, document_type="signout", variant=variant,
        status="draft", generator_version=GENERATOR_VERSION, generated_by=generated_by,
        generated_state_version=int(db.get(Encounter, encounter_id).clinical_state_version or 1),
    )
    db.add(doc); db.flush()

    specs: list[tuple[str, str, str]] = [
        ("one_liner", "one_liner", _one_liner(overview)),
    ]
    problems = overview.get("problems", [])
    if variant == "short":
        problems = problems[:3]
    elif variant in {"standard", "night"}:
        problems = problems[:5]
    for p in problems:
        specs.append(("active_problem", str(p["id"]), _active_problem_text(p)))
    specs.extend([
        ("current_treatment", "current_treatment", _current_treatment_text(db, encounter_id)),
        ("pending_items", "pending_items", _pending_text(overview)),
        ("overnight_risks", "overnight_risks", _overnight_risks(overview)),
        ("contingencies", "contingencies", _contingencies()),
        ("code_status", "code_status", _code_status(db, encounter_id)),
        ("disposition", "disposition", _disposition(overview)),
    ])

    sections = []
    for idx, (stype, skey, content) in enumerate(specs, start=1):
        s = DocumentSection(document_id=doc.id, section_type=stype, section_key=skey, sort_order=idx * 10, generated_content=content)
        db.add(s); db.flush(); sections.append(s)
    db.commit(); db.refresh(doc)
    reasons = []
    counts = overview.get("attention_counts", {})
    if counts.get("unresolved_medications"):
        reasons.append(f'{counts["unresolved_medications"]} medication decision(s) remain unresolved.')
    if counts.get("unresolved_contradictions"):
        reasons.append(f'{counts["unresolved_contradictions"]} unresolved contradiction(s) remain in the encounter state.')
    return {
        "document_id": doc.id, "encounter_id": doc.encounter_id, "document_type": doc.document_type,
        "variant": doc.variant, "status": doc.status, "generator_version": doc.generator_version,
        "generated_at": doc.generated_at, "approved_at": doc.approved_at,
        **document_state_status(db, doc),
        "sections": [_section_dict(db, s) for s in sections],
        "review_required": bool(reasons), "review_reasons": reasons,
    }


def regenerate_signout_content(db: Session, doc: ClinicalDocument, section: DocumentSection) -> str:
    overview = build_patient_overview(db, doc.encounter_id)
    st = section.section_type
    if st == "one_liner":
        return _one_liner(overview)
    if st == "active_problem" and section.section_key:
        p = next((x for x in overview.get("problems", []) if str(x["id"]) == section.section_key), None)
        return _active_problem_text(p) if p else "Problem is no longer active in the structured state; physician review required."
    if st == "current_treatment":
        return _current_treatment_text(db, doc.encounter_id)
    if st == "pending_items":
        return _pending_text(overview)
    if st == "overnight_risks":
        return _overnight_risks(overview)
    if st == "contingencies":
        return _contingencies()
    if st == "code_status":
        return _code_status(db, doc.encounter_id)
    if st == "disposition":
        return _disposition(overview)
    return section.current_generated_content or section.generated_content
