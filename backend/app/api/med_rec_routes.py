from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.services.security_service import current_user, require_finalizer, audit
from app.services.concurrency_service import ConcurrencyConflict
from app.services.idempotency_service import begin as idem_begin, complete as idem_complete, IdempotencyConflict
from app.schemas.med_rec import MedRecDecision, MedRecWorkspace, MedRecStateSummary
from app.services.med_rec_service import build_med_rec_workspace, confirm_discharge_state

router = APIRouter(prefix="/api/v1", tags=["med-rec"])


@router.get("/encounters/{encounter_id}/med-rec", response_model=MedRecWorkspace)
def get_med_rec(encounter_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return build_med_rec_workspace(db, encounter_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/medications/{medication_id}/confirm-discharge-state", response_model=MedRecStateSummary)
def confirm_med_rec_state(medication_id: UUID, payload: MedRecDecision, user: User = Depends(require_finalizer), db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    receipt = None
    try:
        receipt, cached = idem_begin(db, organization_id=user.organization_id, user_id=user.id, key=idempotency_key, method="POST", path=f"/api/v1/medications/{medication_id}/confirm-discharge-state", payload=payload.model_dump())
        if cached is not None:
            return cached
        state = confirm_discharge_state(db, medication_id, payload.model_copy(update={"confirmed_by": user.id}))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConcurrencyConflict as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "current_version": exc.current_version}) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "recovery": "refresh_resource"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(db, user=user, event_type="medication_discharge_state_confirmed", object_type="medication_state", object_id=state.id, metadata={"medication_id":str(medication_id),"status":state.status,"revision":int(state.revision or 1),"reason_sha256":__import__("hashlib").sha256((state.reason or "").encode()).hexdigest()})
    db.commit()
    result = {
        "state_id": state.id,
        "domain": state.domain,
        "status": state.status,
        "reason": state.reason,
        "restart_criteria": state.restart_criteria,
        "effective_datetime": state.effective_datetime,
        "physician_confirmed": state.physician_confirmed,
        "revision": int(state.revision or 1),
    }
    return idem_complete(db, receipt, result)
