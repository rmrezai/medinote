from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.services.identity_service import assert_encounter_identity_safe

from app.mcif.reconciliation import TemporalItem, choose_current, numeric_trend, normalize_value, oxygen_trend
from app.models import (
    ClinicalFact,
    ClinicalTrajectory,
    Contradiction,
    Encounter,
    LabResult,
    Medication,
    MedicationState,
    ConsultantRecommendation,
    SourceDocument,
    VitalSign,
)

RECONCILIATION_VERSION = "mcif-reconcile-0.1"


def _source_times(db: Session, encounter_id: UUID) -> dict[UUID, datetime | None]:
    return {
        row.id: row.source_datetime
        for row in db.scalars(select(SourceDocument).where(SourceDocument.encounter_id == encounter_id))
    }


def _contradiction_exists(db: Session, encounter_id: UUID, category: str, description: str) -> bool:
    return db.scalar(select(Contradiction.id).where(
        Contradiction.encounter_id == encounter_id,
        Contradiction.category == category,
        Contradiction.description == description,
        Contradiction.status == "unresolved",
    )) is not None


def _add_contradiction(db: Session, encounter_id: UUID, category: str, description: str, severity: str = "moderate", fact_a_id=None, fact_b_id=None, source_a_type=None, source_a_id=None, source_b_type=None, source_b_id=None) -> bool:
    if _contradiction_exists(db, encounter_id, category, description):
        return False
    db.add(Contradiction(
        encounter_id=encounter_id,
        category=category,
        description=description,
        severity=severity,
        status="unresolved",
        fact_a_id=fact_a_id,
        fact_b_id=fact_b_id,
        source_a_type=source_a_type or ("clinical_fact" if fact_a_id else None),
        source_a_id=source_a_id or fact_a_id,
        source_b_type=source_b_type or ("clinical_fact" if fact_b_id else None),
        source_b_id=source_b_id or fact_b_id,
    ))
    return True


def _upsert_trajectory(db: Session, encounter_id: UUID, category: str, concept: str, trend: str, earliest_value: str | None, latest_value: str | None, earliest_datetime, latest_datetime, evidence_ids: list[str], interpretation: str | None = None):
    row = db.scalar(select(ClinicalTrajectory).where(
        ClinicalTrajectory.encounter_id == encounter_id,
        ClinicalTrajectory.category == category,
        ClinicalTrajectory.concept == concept,
    ))
    payload = dict(
        trend=trend,
        earliest_value=earliest_value,
        latest_value=latest_value,
        earliest_datetime=earliest_datetime,
        latest_datetime=latest_datetime,
        evidence_ids=evidence_ids,
        interpretation=interpretation,
    )
    if row:
        for key, value in payload.items():
            setattr(row, key, value)
        return row
    row = ClinicalTrajectory(encounter_id=encounter_id, category=category, concept=concept, **payload)
    db.add(row)
    return row


def reconcile_encounter(db: Session, encounter_id: UUID) -> dict:
    assert_encounter_identity_safe(db, encounter_id)
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise LookupError("Encounter not found")

    source_times = _source_times(db, encounter_id)
    contradictions_created = 0
    facts_superseded = 0
    med_states_superseded = 0
    trajectories_updated = 0

    # 1) Clinical facts: one current value per fact_type+concept using timestamp first and source authority as tie-breaker.
    facts = list(db.scalars(select(ClinicalFact).where(ClinicalFact.encounter_id == encounter_id)))
    groups: dict[tuple[str, str], list[ClinicalFact]] = defaultdict(list)
    for fact in facts:
        # Oxygen flow/device are alternate representations of one current support state.
        key = ("oxygen_support", "oxygen_support") if fact.fact_type == "oxygen_support" else (fact.fact_type, fact.concept)
        groups[key].append(fact)

    for (_, concept), rows in groups.items():
        candidates = [TemporalItem(
            identifier=str(x.id),
            concept=x.concept,
            value=normalize_value(x.value_numeric if x.value_numeric is not None else x.value_text),
            timestamp=x.observed_datetime or x.source_datetime or source_times.get(x.source_document_id),
            source_category=x.source_category,
        ) for x in rows]
        winner = choose_current(candidates)
        if not winner:
            continue
        winner_row = next(x for x in rows if str(x.id) == winner.identifier)
        for row in rows:
            should_current = row.id == winner_row.id
            if row.is_current and not should_current:
                facts_superseded += 1
            row.is_current = should_current
            row.fact_state = "current" if should_current else "historical"
            row.superseded_by = None if should_current else winner_row.id

        # Equal timestamp, differing values: preserve winner by authority but flag the disagreement.
        winner_time = winner.timestamp
        if winner_time is not None:
            peers = [x for x in candidates if x.timestamp == winner_time and x.identifier != winner.identifier and x.value != winner.value]
            for peer in peers:
                peer_row = next(x for x in rows if str(x.id) == peer.identifier)
                description = f"Conflicting {concept} values at {winner_time.isoformat()}: {winner.value} vs {peer.value}."
                if _add_contradiction(db, encounter_id, "temporal_fact_conflict", description, "high", winner_row.id, peer_row.id):
                    contradictions_created += 1

    # 2) Lab trajectories: descriptive only (rising/falling/stable), never infer diagnosis or clinical improvement.
    labs = list(db.scalars(select(LabResult).where(LabResult.encounter_id == encounter_id)))
    lab_groups: dict[str, list[LabResult]] = defaultdict(list)
    for lab in labs:
        if lab.value_numeric is not None:
            lab_groups[lab.test_name].append(lab)
    for test_name, rows in lab_groups.items():
        ordered = sorted(rows, key=lambda x: x.collection_datetime or x.result_datetime or source_times.get(x.source_document_id) or datetime.min)
        points = [(x.collection_datetime or x.result_datetime or source_times.get(x.source_document_id), float(x.value_numeric)) for x in ordered]
        trend = numeric_trend(points)
        first, last = ordered[0], ordered[-1]
        _upsert_trajectory(
            db, encounter_id, "lab", test_name, trend,
            normalize_value(first.value_numeric), normalize_value(last.value_numeric),
            points[0][0], points[-1][0], [str(x.id) for x in ordered],
            interpretation=f"{test_name} is {trend} across available timestamped results." if trend != "insufficient_data" else None,
        )
        trajectories_updated += 1

    # 3) Oxygen trajectory: room air = lower support than nasal-cannula flow. This describes support only, not respiratory diagnosis.
    oxygen_rows = list(db.scalars(select(VitalSign).where(
        VitalSign.encounter_id == encounter_id,
        VitalSign.vital_type.in_(["oxygen_flow", "oxygen_support"]),
    )))
    if oxygen_rows:
        ordered = sorted(oxygen_rows, key=lambda x: x.observed_datetime or source_times.get(x.source_document_id) or datetime.min)
        points = [(x.observed_datetime or source_times.get(x.source_document_id), x.oxygen_device, float(x.oxygen_flow_lpm) if x.oxygen_flow_lpm is not None else None, x.value_text) for x in ordered]
        trend = oxygen_trend(points)
        first, last = ordered[0], ordered[-1]
        first_value = first.value_text or (f"{first.oxygen_flow_lpm} L/min" if first.oxygen_flow_lpm is not None else first.oxygen_device)
        last_value = last.value_text or (f"{last.oxygen_flow_lpm} L/min" if last.oxygen_flow_lpm is not None else last.oxygen_device)
        _upsert_trajectory(
            db, encounter_id, "respiratory_support", "oxygen_support", trend,
            first_value, last_value, points[0][0], points[-1][0], [str(x.id) for x in ordered],
            interpretation=f"Oxygen support is {trend}." if trend != "insufficient_data" else None,
        )
        trajectories_updated += 1

    # 4) Medication states: preserve Home/Hospital/Discharge domains independently. Within a domain, newest known state wins.
    meds = list(db.scalars(select(Medication).where(Medication.encounter_id == encounter_id)))
    for med in meds:
        states = list(db.scalars(select(MedicationState).where(MedicationState.medication_id == med.id)))
        domain_groups: dict[str, list[MedicationState]] = defaultdict(list)
        for state in states:
            domain_groups[state.domain].append(state)
        for domain, rows in domain_groups.items():
            ordered = sorted(rows, key=lambda x: x.effective_datetime or source_times.get(x.source_document_id) or x.created_at or datetime.min)
            winner = ordered[-1]
            for row in rows:
                should_current = row.id == winner.id
                if row.is_current and not should_current:
                    med_states_superseded += 1
                row.is_current = should_current

            # Same effective timestamp/source period but incompatible status -> flag rather than silently collapsing.
            winner_time = winner.effective_datetime or source_times.get(winner.source_document_id)
            for peer in rows:
                if peer.id == winner.id or peer.status == winner.status:
                    continue
                peer_time = peer.effective_datetime or source_times.get(peer.source_document_id)
                if winner_time is not None and peer_time == winner_time:
                    description = f"Conflicting {domain} medication states for {med.display_name or med.normalized_name}: {winner.status} vs {peer.status}."
                    if _add_contradiction(db, encounter_id, "medication_state_conflict", description, "critical"):
                        contradictions_created += 1

        # Cross-domain states are not automatically contradictions. Home active + hospital held is a legitimate transition.
        # But hospital current 'held/stopped' versus physician-confirmed discharge 'continue/resume' deserves explicit review.
        current = {x.domain: x for x in states if x.is_current}
        hospital = current.get("hospital")
        discharge = current.get("discharge")
        if hospital and discharge and discharge.physician_confirmed:
            if hospital.status in {"held", "stopped"} and discharge.status in {"continue", "resume"}:
                description = (
                    f"{med.display_name or med.normalized_name} is {hospital.status} in hospital state but has a physician-confirmed "
                    f"discharge state of {discharge.status}; verify intentional transition and timing."
                )
                if _add_contradiction(db, encounter_id, "medication_transition_review", description, "high"):
                    contradictions_created += 1


    # 5) Consultant disagreement: preserve conflicting same-target recommendations rather than collapsing them.
    consults = list(db.scalars(select(ConsultantRecommendation).where(
        ConsultantRecommendation.encounter_id == encounter_id
    )))
    action_re = __import__("re").compile(r"\b(?P<action>hold|continue|resume|restart|stop|discontinue)\s+(?P<target>[a-zA-Z][a-zA-Z0-9_-]{1,40})", __import__("re").I)
    parsed = []
    for row in consults:
        m = action_re.search(row.recommendation or "")
        if m:
            action = m.group("action").lower()
            action = {"restart":"resume", "discontinue":"stop"}.get(action, action)
            parsed.append((row, action, m.group("target").lower()))
    opposites = {("hold","continue"), ("hold","resume"), ("stop","continue"), ("stop","resume")}
    for i, (a, act_a, target_a) in enumerate(parsed):
        for b, act_b, target_b in parsed[i+1:]:
            if target_a != target_b or a.service == b.service:
                continue
            if (act_a, act_b) not in opposites and (act_b, act_a) not in opposites:
                continue
            a.conflict_status = "conflict"
            b.conflict_status = "conflict"
            description = f"Conflicting consultant recommendations for {target_a}: {a.service} says {act_a}; {b.service} says {act_b}."
            if _add_contradiction(
                db, encounter_id, "consultant_recommendation_conflict", description, "high",
                source_a_type="consultant_recommendation", source_a_id=a.id,
                source_b_type="consultant_recommendation", source_b_id=b.id,
            ):
                contradictions_created += 1

    db.commit()
    return {
        "encounter_id": str(encounter_id),
        "status": "complete",
        "reconciliation_version": RECONCILIATION_VERSION,
        "facts_superseded": facts_superseded,
        "medication_states_superseded": med_states_superseded,
        "trajectories_updated": trajectories_updated,
        "contradictions_created": contradictions_created,
        "rules": [
            "Timestamp determines recency when available; source authority breaks equal-time ties.",
            "Unknown timestamps are never fabricated.",
            "Lab trends are descriptive (rising/falling/stable), not diagnoses or treatment conclusions.",
            "Home, hospital, and discharge medication domains remain separate.",
            "Conflicts are surfaced rather than silently resolved when source evidence remains incompatible.",
        ],
    }
