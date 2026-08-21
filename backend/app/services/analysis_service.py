from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mcif import analyze_source_text
from app.services.identity_service import assert_encounter_identity_safe
from app.services.reconciliation_service import reconcile_encounter
from app.services.synthesis_service import synthesize_encounter
from app.models import (
    ClinicalFact,
    ClinicalProblem,
    ConsultantRecommendation,
    DispositionState,
    Encounter,
    LabResult,
    Medication,
    MedicationState,
    PendingItem,
    Procedure,
    SourceDocument,
    VitalSign,
)

EXTRACTION_VERSION = "mcif-deterministic-0.1"


def _source_category(document_type: str) -> str:
    return {
        "lab": "objective",
        "radiology": "objective",
        "microbiology": "objective",
        "mar": "objective",
        "orders": "objective",
        "nursing_note": "nursing_documented",
        "consult_note": "consultant_documented",
        "therapy": "clinician_documented",
        "case_management": "clinician_documented",
    }.get(document_type, "clinician_documented")


def _fact_exists(db: Session, encounter_id: UUID, source_id: UUID, candidate) -> bool:
    stmt = select(ClinicalFact.id).where(
        ClinicalFact.encounter_id == encounter_id,
        ClinicalFact.source_document_id == source_id,
        ClinicalFact.fact_type == candidate.fact_type,
        ClinicalFact.concept == candidate.concept,
        ClinicalFact.source_start == candidate.source_start,
        ClinicalFact.source_end == candidate.source_end,
    )
    return db.scalar(stmt) is not None


def _lab_exists(db: Session, encounter_id: UUID, source_id: UUID, candidate) -> bool:
    stmt = select(LabResult.id).where(
        LabResult.encounter_id == encounter_id,
        LabResult.source_document_id == source_id,
        LabResult.test_name == candidate.test_name,
        LabResult.value_numeric == candidate.value_numeric,
    )
    return db.scalar(stmt) is not None


def _get_or_create_medication(db: Session, encounter_id: UUID, candidate) -> Medication:
    med = db.scalar(
        select(Medication).where(
            Medication.encounter_id == encounter_id,
            Medication.normalized_name == candidate.normalized_name,
        )
    )
    if med:
        return med
    med = Medication(
        encounter_id=encounter_id,
        normalized_name=candidate.normalized_name,
        display_name=candidate.display_name,
    )
    db.add(med)
    db.flush()
    return med


def analyze_encounter(db: Session, encounter_id: UUID) -> dict:
    assert_encounter_identity_safe(db, encounter_id)
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise LookupError("Encounter not found")

    sources = list(
        db.scalars(
            select(SourceDocument)
            .where(SourceDocument.encounter_id == encounter_id)
            .order_by(SourceDocument.imported_at)
        )
    )

    counts = defaultdict(int)
    source_reports = []

    for source in sources:
        category = _source_category(source.document_type)
        bundle = analyze_source_text(source.raw_text, source.source_datetime, category)

        for fact in bundle.facts:
            if _fact_exists(db, encounter_id, source.id, fact):
                continue
            db.add(ClinicalFact(
                encounter_id=encounter_id,
                source_document_id=source.id,
                fact_type=fact.fact_type,
                concept=fact.concept,
                value_text=fact.value_text,
                value_numeric=fact.value_numeric,
                units=fact.units,
                evidence_text=fact.evidence_text,
                source_start=fact.source_start,
                source_end=fact.source_end,
                observed_datetime=fact.observed_datetime,
                source_datetime=source.source_datetime,
                fact_state=fact.fact_state,
                confidence=fact.confidence,
                source_category=fact.source_category,
                is_current=True,
                extracted_by="deterministic",
                extraction_version=EXTRACTION_VERSION,
            ))
            counts["facts_created"] += 1

        for lab in bundle.labs:
            if _lab_exists(db, encounter_id, source.id, lab):
                continue
            db.add(LabResult(
                encounter_id=encounter_id,
                source_document_id=source.id,
                test_name=lab.test_name,
                value_numeric=lab.value_numeric,
                value_text=lab.value_text,
                units=lab.units,
                collection_datetime=source.source_datetime,
                result_datetime=source.source_datetime,
            ))
            counts["labs_created"] += 1

        for vital in bundle.vitals:
            exists = db.scalar(
                select(VitalSign.id).where(
                    VitalSign.encounter_id == encounter_id,
                    VitalSign.source_document_id == source.id,
                    VitalSign.vital_type == vital.vital_type,
                    VitalSign.value_numeric == vital.value_numeric,
                    VitalSign.value_text == vital.value_text,
                )
            )
            if exists:
                continue
            db.add(VitalSign(
                encounter_id=encounter_id,
                source_document_id=source.id,
                vital_type=vital.vital_type,
                value_numeric=vital.value_numeric,
                value_text=vital.value_text,
                units=vital.units,
                oxygen_device=vital.oxygen_device,
                oxygen_flow_lpm=vital.oxygen_flow_lpm,
                observed_datetime=source.source_datetime,
            ))
            counts["vitals_created"] += 1

        for problem in bundle.problems:
            existing = db.scalar(
                select(ClinicalProblem).where(
                    ClinicalProblem.encounter_id == encounter_id,
                    ClinicalProblem.normalized_name == problem.normalized_name,
                ).order_by(ClinicalProblem.created_at.desc())
            )
            if existing:
                # A diagnosis explicitly resolved/ruled-out is a conservative tombstone: a later bare
                # copied-forward mention must not silently resurrect it. Explicit trajectory language
                # can still update an active problem, while recurrence should require a future dedicated rule.
                if existing.status == "resolved" and problem.status == "active":
                    continue
                if problem.status in {"improving", "worsening", "stable", "resolved"}:
                    existing.status = problem.status
                    if problem.status == "resolved":
                        existing.resolved_datetime = source.source_datetime
                continue
            db.add(ClinicalProblem(
                encounter_id=encounter_id,
                name=problem.name,
                normalized_name=problem.normalized_name,
                certainty=problem.certainty,
                status=problem.status,
                onset_datetime=source.source_datetime,
            ))
            counts["problems_created"] += 1

        for med_candidate in bundle.medications:
            med = _get_or_create_medication(db, encounter_id, med_candidate)
            current_states = list(db.scalars(select(MedicationState).where(
                MedicationState.medication_id == med.id,
                MedicationState.domain == med_candidate.domain,
                MedicationState.is_current.is_(True),
            )))
            if any(state.status == med_candidate.status and state.source_document_id == source.id for state in current_states):
                continue
            for state in current_states:
                state.is_current = False
            db.add(MedicationState(
                medication_id=med.id,
                source_document_id=source.id,
                domain=med_candidate.domain,
                status=med_candidate.status,
                effective_datetime=source.source_datetime,
                reason=med_candidate.reason,
                is_current=True,
                physician_confirmed=False,
            ))
            counts["medication_states_created"] += 1

        for consult in bundle.consultants:
            exists = db.scalar(select(ConsultantRecommendation.id).where(
                ConsultantRecommendation.encounter_id == encounter_id,
                ConsultantRecommendation.source_document_id == source.id,
                ConsultantRecommendation.service == consult.service,
                ConsultantRecommendation.recommendation == consult.recommendation,
            ))
            if exists:
                continue
            db.add(ConsultantRecommendation(
                encounter_id=encounter_id,
                source_document_id=source.id,
                service=consult.service,
                recommendation_datetime=source.source_datetime,
                recommendation=consult.recommendation,
                implementation_status="unclear",
                current_relevance="current",
                conflict_status="unknown",
            ))
            counts["consultants_created"] += 1

        for pending in bundle.pending_items:
            exists = db.scalar(select(PendingItem.id).where(
                PendingItem.encounter_id == encounter_id,
                PendingItem.description == pending.description,
                PendingItem.status == "pending",
            ))
            if exists:
                continue
            db.add(PendingItem(
                encounter_id=encounter_id,
                item_type=pending.item_type,
                description=pending.description,
                status="pending",
            ))
            counts["pending_items_created"] += 1

        for proc_candidate in bundle.procedures:
            name = proc_candidate.procedure_name.strip().lower()
            existing = db.scalar(select(Procedure).where(
                Procedure.encounter_id == encounter_id,
                Procedure.procedure_name == name,
            ))
            if existing:
                # Terminal states must not regress to a stale copied-forward planned/pending statement.
                if existing.status in {"cancelled", "completed"} and proc_candidate.status in {"planned", "pending", "scheduled"}:
                    continue
                existing.status = proc_candidate.status
                existing.source_document_id = source.id
                if proc_candidate.status in {"planned", "pending", "scheduled"}:
                    existing.planned_datetime = source.source_datetime
                elif proc_candidate.status == "completed":
                    existing.performed_datetime = source.source_datetime
                counts["procedures_updated"] += 1
            else:
                db.add(Procedure(
                    encounter_id=encounter_id,
                    source_document_id=source.id,
                    procedure_name=name,
                    status=proc_candidate.status,
                    planned_datetime=source.source_datetime if proc_candidate.status in {"planned", "pending", "scheduled"} else None,
                    performed_datetime=source.source_datetime if proc_candidate.status == "completed" else None,
                ))
                counts["procedures_created"] += 1

        for resolved in bundle.resolved_items:
            needle = resolved.description.lower().strip()
            candidates = list(db.scalars(select(PendingItem).where(
                PendingItem.encounter_id == encounter_id,
                PendingItem.status == "pending",
            )))
            for item in candidates:
                desc = item.description.lower().strip()
                if needle in desc or desc in needle or needle.rstrip("s") in desc.rstrip("s"):
                    item.status = "resolved"
                    item.resolved_at = source.source_datetime
                    if resolved.result_text:
                        item.clinical_significance = f"Final result: {resolved.result_text}"
                    counts["pending_items_resolved"] += 1

        for disposition in bundle.dispositions:
            exists = db.scalar(select(DispositionState.id).where(
                DispositionState.encounter_id == encounter_id,
                DispositionState.source_datetime == source.source_datetime,
                DispositionState.anticipated_destination == disposition.anticipated_destination,
                DispositionState.pt_recommendation == disposition.pt_recommendation,
                DispositionState.ot_recommendation == disposition.ot_recommendation,
                DispositionState.slp_recommendation == disposition.slp_recommendation,
                DispositionState.mobility_status == disposition.mobility_status,
                DispositionState.oxygen_need == disposition.oxygen_need,
            ))
            if exists:
                continue
            db.add(DispositionState(
                encounter_id=encounter_id,
                anticipated_destination=disposition.anticipated_destination,
                current_barriers=disposition.current_barriers or None,
                mobility_status=disposition.mobility_status,
                pt_recommendation=disposition.pt_recommendation,
                ot_recommendation=disposition.ot_recommendation,
                slp_recommendation=disposition.slp_recommendation,
                oxygen_need=disposition.oxygen_need,
                source_datetime=source.source_datetime,
            ))
            counts["disposition_states_created"] += 1

        source_reports.append({
            "source_document_id": str(source.id),
            "document_type": source.document_type,
            "candidate_counts": {
                "facts": len(bundle.facts),
                "problems": len(bundle.problems),
                "medications": len(bundle.medications),
                "labs": len(bundle.labs),
                "vitals": len(bundle.vitals),
                "consultants": len(bundle.consultants),
                "pending_items": len(bundle.pending_items),
                "resolved_items": len(bundle.resolved_items),
                "procedures": len(bundle.procedures),
                "dispositions": len(bundle.dispositions),
            },
        })

    db.commit()
    reconciliation = reconcile_encounter(db, encounter_id)
    synthesis = synthesize_encounter(db, encounter_id)
    return {
        "encounter_id": str(encounter_id),
        "status": "complete",
        "extraction_version": EXTRACTION_VERSION,
        "sources_analyzed": len(sources),
        **dict(counts),
        "source_reports": source_reports,
        "reconciliation": reconciliation,
        "synthesis": synthesis,
        "limitations": [
            "Extraction remains conservative and deterministic for the Step 41 pilot scaffold.",
            "Only explicit home-medication, exam, therapy/disposition, and final-result language is structured; ambiguous statements remain unstructured rather than guessed.",
            "No autonomous clinical decisions are created or physician-confirmed.",
        ],
    }
