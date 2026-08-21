from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.services.identity_service import assert_encounter_identity_safe

from app.mcif.synthesis import SYNTHESIS_VERSION, acuity_rank, synthesize_problem_status
from app.models import ClinicalFact, ClinicalProblem, ClinicalTrajectory, Encounter, ProblemEvidence


def _link_evidence(db: Session, problem: ClinicalProblem, fact: ClinicalFact, relationship: str, strength: str = "supporting") -> bool:
    exists = db.scalar(select(ProblemEvidence.id).where(
        ProblemEvidence.problem_id == problem.id,
        ProblemEvidence.fact_id == fact.id,
    ))
    if exists:
        return False
    db.add(ProblemEvidence(
        problem_id=problem.id,
        fact_id=fact.id,
        relationship=relationship,
        evidence_strength=strength,
    ))
    return True


def synthesize_encounter(db: Session, encounter_id: UUID) -> dict:
    assert_encounter_identity_safe(db, encounter_id)
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise LookupError("Encounter not found")

    problems = list(db.scalars(select(ClinicalProblem).where(
        ClinicalProblem.encounter_id == encounter_id,
        ClinicalProblem.status != "resolved",
    )))
    trajectories = list(db.scalars(select(ClinicalTrajectory).where(
        ClinicalTrajectory.encounter_id == encounter_id,
    )))
    current_facts = list(db.scalars(select(ClinicalFact).where(
        ClinicalFact.encounter_id == encounter_id,
        ClinicalFact.is_current.is_(True),
    )))

    trajectory_map = {(row.category, row.concept): row.trend for row in trajectories}
    facts_by_concept: dict[str, list[ClinicalFact]] = {}
    for fact in current_facts:
        facts_by_concept.setdefault(fact.concept, []).append(fact)

    updated = 0
    evidence_links_created = 0
    summaries = []

    for problem in problems:
        result = synthesize_problem_status(problem.normalized_name, trajectory_map)

        # Never alter diagnostic certainty here. When an objective trajectory rule applies,
        # it may update status. Otherwise preserve an explicit source-derived status such as
        # "improving" rather than resetting the problem to generic active.
        target_status = result.status if result.trajectory_basis is not None else problem.status
        if problem.status != target_status:
            problem.status = target_status
            updated += 1
        rank = acuity_rank(problem.normalized_name, problem.status)
        if problem.acuity_rank != rank:
            problem.acuity_rank = rank
            updated += 1

        linked_fact_ids: list[str] = []
        for concept in result.evidence_concepts:
            for fact in facts_by_concept.get(concept, []):
                if _link_evidence(db, problem, fact, relationship="trajectory_support"):
                    evidence_links_created += 1
                linked_fact_ids.append(str(fact.id))

        summaries.append({
            "problem_id": str(problem.id),
            "name": problem.name,
            "normalized_name": problem.normalized_name,
            "certainty": problem.certainty,
            "status": problem.status,
            "acuity_rank": problem.acuity_rank,
            "trajectory_basis": result.trajectory_basis,
            "evidence_fact_ids": sorted(set(linked_fact_ids)),
            "physician_approved": problem.physician_approved,
        })

    db.commit()
    summaries.sort(key=lambda x: (x["acuity_rank"] if x["acuity_rank"] is not None else 9999, x["name"]))
    return {
        "encounter_id": str(encounter_id),
        "status": "complete",
        "synthesis_version": SYNTHESIS_VERSION,
        "problems_processed": len(problems),
        "problem_fields_updated": updated,
        "evidence_links_created": evidence_links_created,
        "problems": summaries,
        "rules": [
            "Synthesis never creates a diagnosis from a lab or vital trend alone.",
            "Diagnostic certainty is preserved exactly; synthesis does not promote possible/suspected diagnoses.",
            "Only conservative problem-to-trajectory mappings are enabled in v0.1.",
            "Acuity rank is a default synthesis priority and is not physician approval.",
            "Objective evidence links remain traceable to current MCIF facts.",
        ],
    }
