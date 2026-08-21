from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analysis import AnalysisReport
from app.services.analysis_service import analyze_encounter
from app.services.reconciliation_service import reconcile_encounter
from app.services.synthesis_service import synthesize_encounter
from app.schemas.synthesis import SynthesisReport

router = APIRouter(prefix="/api/v1")


@router.post("/encounters/{encounter_id}/analyze", response_model=AnalysisReport)
def analyze(encounter_id: UUID, db: Session = Depends(get_db)):
    try:
        return analyze_encounter(db, encounter_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/encounters/{encounter_id}/reconcile")
def reconcile(encounter_id: UUID, db: Session = Depends(get_db)):
    try:
        return reconcile_encounter(db, encounter_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/encounters/{encounter_id}/synthesize", response_model=SynthesisReport)
def synthesizer(encounter_id: UUID, db: Session = Depends(get_db)):
    try:
        return synthesize_encounter(db, encounter_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
