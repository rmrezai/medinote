from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Contradiction, Encounter, User
from app.schemas.clinical import ContradictionAdjudicateRequest
from app.services.contradiction_service import adjudicate_contradiction, contradiction_detail
from app.services.security_service import audit, current_user, require_finalizer
from app.services.concurrency_service import ConcurrencyConflict
from app.services.idempotency_service import begin as idem_begin, complete as idem_complete, IdempotencyConflict

router = APIRouter(prefix="/api/v1")


@router.get("/contradictions/{contradiction_id}")
def read_contradiction(contradiction_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    contradiction = db.get(Contradiction, contradiction_id)
    if not contradiction:
        raise HTTPException(status_code=404, detail="Contradiction not found")
    encounter = db.get(Encounter, contradiction.encounter_id)
    if not encounter or encounter.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Contradiction not found")
    return contradiction_detail(db, contradiction_id)


@router.post("/contradictions/{contradiction_id}/adjudicate")
def adjudicate(contradiction_id: UUID, payload: ContradictionAdjudicateRequest, user: User = Depends(require_finalizer), db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    contradiction = db.get(Contradiction, contradiction_id)
    if not contradiction:
        raise HTTPException(status_code=404, detail="Contradiction not found")
    encounter = db.get(Encounter, contradiction.encounter_id)
    if not encounter or encounter.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Contradiction not found")
    try:
        receipt, cached = idem_begin(db, organization_id=user.organization_id, user_id=user.id, key=idempotency_key, method="POST", path=f"/api/v1/contradictions/{contradiction_id}/adjudicate", payload=payload.model_dump())
        if cached is not None:
            return cached
        result = adjudicate_contradiction(db, contradiction_id, payload.resolution_type, payload.reason, user.id, payload.decision_text, payload.expected_revision)
        audit(db, user=user, event_type="contradiction_adjudicated", encounter_id=encounter.id, object_type="contradiction", object_id=contradiction_id, metadata={"resolution_type": payload.resolution_type})
        db.commit()
        return idem_complete(db, receipt, result)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConcurrencyConflict as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "current_version": exc.current_version}) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "recovery": "refresh_resource"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
