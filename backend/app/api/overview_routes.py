from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.overview import PatientOverviewResponse
from app.services.overview_service import build_patient_overview

router = APIRouter(prefix="/api/v1")


@router.get("/encounters/{encounter_id}/overview", response_model=PatientOverviewResponse)
def patient_overview(encounter_id: UUID, db: Session = Depends(get_db)):
    try:
        return build_patient_overview(db, encounter_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
