from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import (
    ClinicalFact,
    ClinicalProblem,
    ConsultantRecommendation,
    Contradiction,
    ClinicalTrajectory,
    DispositionState,
    Encounter,
    LabResult,
    Medication,
    MedicationState,
    PendingItem,
    ProblemEvidence,
    SourceDocument,
    VitalSign,
)
from app.schemas.clinical import (
    ConsultantCreate,
    ContradictionCreate,
    DispositionCreate,
    FactCreate,
    FactRead,
    LabCreate,
    MedicationCreate,
    MedicationRead,
    MedicationStateCreate,
    MedicationStateRead,
    PendingItemCreate,
    ProblemCreate,
    ProblemEvidenceCreate,
    ProblemRead,
    VitalCreate,
)

router = APIRouter(prefix="/api/v1")


def require_encounter(db: Session, encounter_id: UUID) -> Encounter:
    encounter = db.get(Encounter, encounter_id)
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return encounter


def validate_source(db: Session, encounter_id: UUID, source_document_id: UUID | None) -> None:
    if source_document_id is None:
        return
    source = db.get(SourceDocument, source_document_id)
    if not source or source.encounter_id != encounter_id:
        raise HTTPException(status_code=400, detail="Source document does not belong to encounter")


@router.post("/encounters/{encounter_id}/facts", response_model=FactRead, status_code=status.HTTP_201_CREATED)
def create_fact(encounter_id: UUID, payload: FactCreate, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)
    validate_source(db, encounter_id, payload.source_document_id)
    fact = ClinicalFact(encounter_id=encounter_id, **payload.model_dump())
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


@router.get("/encounters/{encounter_id}/facts", response_model=list[FactRead])
def list_facts(encounter_id: UUID, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)
    return list(db.scalars(select(ClinicalFact).where(ClinicalFact.encounter_id == encounter_id).order_by(ClinicalFact.created_at)))


@router.post("/encounters/{encounter_id}/problems", response_model=ProblemRead, status_code=status.HTTP_201_CREATED)
def create_problem(encounter_id: UUID, payload: ProblemCreate, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)
    if payload.parent_problem_id:
        parent = db.get(ClinicalProblem, payload.parent_problem_id)
        if not parent or parent.encounter_id != encounter_id:
            raise HTTPException(status_code=400, detail="Parent problem does not belong to encounter")
    problem = ClinicalProblem(encounter_id=encounter_id, **payload.model_dump())
    db.add(problem)
    db.commit()
    db.refresh(problem)
    return problem


@router.post("/problems/{problem_id}/evidence", status_code=status.HTTP_201_CREATED)
def add_problem_evidence(problem_id: UUID, payload: ProblemEvidenceCreate, db: Session = Depends(get_db)):
    problem = db.get(ClinicalProblem, problem_id)
    fact = db.get(ClinicalFact, payload.fact_id)
    if not problem or not fact:
        raise HTTPException(status_code=404, detail="Problem or fact not found")
    if problem.encounter_id != fact.encounter_id:
        raise HTTPException(status_code=400, detail="Problem and fact belong to different encounters")
    link = ProblemEvidence(problem_id=problem_id, **payload.model_dump())
    db.add(link)
    db.commit()
    db.refresh(link)
    return {"id": str(link.id), "problem_id": str(link.problem_id), "fact_id": str(link.fact_id)}


@router.get("/encounters/{encounter_id}/problems", response_model=list[ProblemRead])
def list_problems(encounter_id: UUID, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)
    return list(db.scalars(select(ClinicalProblem).where(ClinicalProblem.encounter_id == encounter_id).order_by(ClinicalProblem.acuity_rank.nullslast(), ClinicalProblem.created_at)))


@router.post("/encounters/{encounter_id}/medications", response_model=MedicationRead, status_code=status.HTTP_201_CREATED)
def create_medication(encounter_id: UUID, payload: MedicationCreate, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)
    medication = Medication(encounter_id=encounter_id, **payload.model_dump())
    db.add(medication)
    db.commit()
    db.refresh(medication)
    return medication


@router.post("/medications/{medication_id}/states", response_model=MedicationStateRead, status_code=status.HTTP_201_CREATED)
def create_medication_state(medication_id: UUID, payload: MedicationStateCreate, db: Session = Depends(get_db)):
    medication = db.get(Medication, medication_id)
    if not medication:
        raise HTTPException(status_code=404, detail="Medication not found")
    validate_source(db, medication.encounter_id, payload.source_document_id)
    if payload.is_current:
        current_states = db.scalars(
            select(MedicationState).where(
                MedicationState.medication_id == medication_id,
                MedicationState.domain == payload.domain,
                MedicationState.is_current.is_(True),
            )
        )
        for state_row in current_states:
            state_row.is_current = False
    med_state = MedicationState(medication_id=medication_id, **payload.model_dump())
    db.add(med_state)
    db.commit()
    db.refresh(med_state)
    return med_state


@router.post("/encounters/{encounter_id}/labs", status_code=status.HTTP_201_CREATED)
def create_lab(encounter_id: UUID, payload: LabCreate, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)
    validate_source(db, encounter_id, payload.source_document_id)
    row = LabResult(encounter_id=encounter_id, **payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": str(row.id), "test_name": row.test_name}


@router.post("/encounters/{encounter_id}/vitals", status_code=status.HTTP_201_CREATED)
def create_vital(encounter_id: UUID, payload: VitalCreate, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)
    validate_source(db, encounter_id, payload.source_document_id)
    row = VitalSign(encounter_id=encounter_id, **payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": str(row.id), "vital_type": row.vital_type}


@router.post("/encounters/{encounter_id}/consultants", status_code=status.HTTP_201_CREATED)
def create_consultant(encounter_id: UUID, payload: ConsultantCreate, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)
    validate_source(db, encounter_id, payload.source_document_id)
    row = ConsultantRecommendation(encounter_id=encounter_id, **payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": str(row.id), "service": row.service}


@router.post("/encounters/{encounter_id}/pending-items", status_code=status.HTTP_201_CREATED)
def create_pending_item(encounter_id: UUID, payload: PendingItemCreate, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)
    row = PendingItem(encounter_id=encounter_id, **payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": str(row.id), "status": row.status}


@router.post("/encounters/{encounter_id}/disposition", status_code=status.HTTP_201_CREATED)
def create_disposition(encounter_id: UUID, payload: DispositionCreate, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)
    row = DispositionState(encounter_id=encounter_id, **payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": str(row.id), "anticipated_destination": row.anticipated_destination}


@router.post("/encounters/{encounter_id}/contradictions", status_code=status.HTTP_201_CREATED)
def create_contradiction(encounter_id: UUID, payload: ContradictionCreate, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)
    for fact_id in (payload.fact_a_id, payload.fact_b_id):
        if fact_id:
            fact = db.get(ClinicalFact, fact_id)
            if not fact or fact.encounter_id != encounter_id:
                raise HTTPException(status_code=400, detail="Contradiction fact does not belong to encounter")
    row = Contradiction(encounter_id=encounter_id, **payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return {"id": str(row.id), "severity": row.severity, "status": row.status}


def _row_dict(row, fields):
    return {field: getattr(row, field) for field in fields}


@router.get("/encounters/{encounter_id}/state")
def get_encounter_state(encounter_id: UUID, db: Session = Depends(get_db)):
    require_encounter(db, encounter_id)

    facts = list(db.scalars(select(ClinicalFact).where(ClinicalFact.encounter_id == encounter_id, ClinicalFact.is_current.is_(True)).order_by(ClinicalFact.created_at)))
    problems = list(db.scalars(select(ClinicalProblem).where(ClinicalProblem.encounter_id == encounter_id, ClinicalProblem.status != "resolved").order_by(ClinicalProblem.acuity_rank.nullslast(), ClinicalProblem.created_at)))
    meds = list(db.scalars(select(Medication).where(Medication.encounter_id == encounter_id).order_by(Medication.normalized_name)))
    labs = list(db.scalars(select(LabResult).where(LabResult.encounter_id == encounter_id).order_by(LabResult.collection_datetime.desc().nullslast(), LabResult.created_at.desc())))
    vitals = list(db.scalars(select(VitalSign).where(VitalSign.encounter_id == encounter_id).order_by(VitalSign.observed_datetime.desc().nullslast(), VitalSign.created_at.desc())))
    consultants = list(db.scalars(select(ConsultantRecommendation).where(ConsultantRecommendation.encounter_id == encounter_id).order_by(ConsultantRecommendation.recommendation_datetime.desc().nullslast(), ConsultantRecommendation.created_at.desc())))
    pending = list(db.scalars(select(PendingItem).where(PendingItem.encounter_id == encounter_id, PendingItem.status == "pending").order_by(PendingItem.created_at)))
    dispositions = list(db.scalars(select(DispositionState).where(DispositionState.encounter_id == encounter_id).order_by(DispositionState.source_datetime.desc().nullslast(), DispositionState.created_at.desc()).limit(1)))
    contradictions = list(db.scalars(select(Contradiction).where(Contradiction.encounter_id == encounter_id, Contradiction.status == "unresolved").order_by(Contradiction.created_at)))
    trajectories = list(db.scalars(select(ClinicalTrajectory).where(ClinicalTrajectory.encounter_id == encounter_id).order_by(ClinicalTrajectory.category, ClinicalTrajectory.concept)))

    problem_evidence = list(db.scalars(select(ProblemEvidence).join(ClinicalProblem, ProblemEvidence.problem_id == ClinicalProblem.id).where(ClinicalProblem.encounter_id == encounter_id)))
    evidence_by_problem = {}
    for link in problem_evidence:
        evidence_by_problem.setdefault(link.problem_id, []).append({
            "fact_id": link.fact_id,
            "relationship": link.relationship,
            "evidence_strength": link.evidence_strength,
        })

    medication_output = []
    for med in meds:
        states = list(db.scalars(select(MedicationState).where(MedicationState.medication_id == med.id, MedicationState.is_current.is_(True)).order_by(MedicationState.domain)))
        medication_output.append({
            "id": med.id,
            "name": med.display_name or med.normalized_name,
            "normalized_name": med.normalized_name,
            "dose": med.dose,
            "route": med.route,
            "frequency": med.frequency,
            "indication": med.indication,
            "states": [
                _row_dict(s, ["id", "domain", "status", "effective_datetime", "reason", "restart_criteria", "physician_confirmed"])
                for s in states
            ],
        })

    return {
        "encounter_id": encounter_id,
        "facts": [_row_dict(x, ["id", "fact_type", "concept", "value_text", "value_numeric", "units", "observed_datetime", "fact_state", "confidence", "source_document_id"]) for x in facts],
        "problems": [dict(_row_dict(x, ["id", "name", "normalized_name", "icd10_candidate", "certainty", "acuity_rank", "status", "parent_problem_id", "physician_approved"]), evidence=evidence_by_problem.get(x.id, [])) for x in problems],
        "medications": medication_output,
        "labs": [_row_dict(x, ["id", "test_name", "value_numeric", "value_text", "units", "abnormal_flag", "collection_datetime", "result_datetime"]) for x in labs],
        "vitals": [_row_dict(x, ["id", "vital_type", "value_numeric", "value_text", "units", "oxygen_device", "oxygen_flow_lpm", "observed_datetime"]) for x in vitals],
        "consultants": [_row_dict(x, ["id", "service", "consultant_name", "recommendation_datetime", "assessment", "recommendation", "implementation_status", "conflict_status"]) for x in consultants],
        "pending_items": [_row_dict(x, ["id", "item_type", "description", "status", "owner", "clinical_significance"]) for x in pending],
        "disposition": _row_dict(dispositions[0], ["id", "anticipated_destination", "current_barriers", "mobility_status", "pt_recommendation", "ot_recommendation", "slp_recommendation", "oxygen_need", "authorization_status"]) if dispositions else None,
        "contradictions": [_row_dict(x, ["id", "category", "description", "severity", "status", "fact_a_id", "fact_b_id", "source_a_type", "source_a_id", "source_b_type", "source_b_id"]) for x in contradictions],
        "trajectories": [_row_dict(x, ["id", "category", "concept", "trend", "earliest_value", "latest_value", "earliest_datetime", "latest_datetime", "evidence_ids", "interpretation"]) for x in trajectories],
    }
