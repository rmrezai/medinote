from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.services.security_service import current_user, require_finalizer, audit
from app.services.idempotency_service import begin as idem_begin, complete as idem_complete, IdempotencyConflict
from app.schemas.hp import HPDocumentResponse, HPGenerateRequest
from app.services.hp_service import generate_hp_document, get_hp_document

router = APIRouter(prefix="/api/v1")


@router.post("/encounters/{encounter_id}/documents/hp", response_model=HPDocumentResponse)
def generate_hp(encounter_id: UUID, payload: HPGenerateRequest, user: User = Depends(current_user), db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    try:
        receipt, cached = idem_begin(db, organization_id=user.organization_id, user_id=user.id, key=idempotency_key, method="POST", path=f"/api/v1/encounters/{encounter_id}/documents/hp", payload=payload.model_dump())
        if cached is not None:
            return cached
        result = generate_hp_document(db, encounter_id, payload.variant, user.id)
        audit(db, user=user, event_type="document_generated", encounter_id=encounter_id, object_type="clinical_document", object_id=result["document_id"], metadata={"document_type":"hp","variant":payload.variant,"generated_state_version":result.get("generated_state_version")})
        db.commit()
        return idem_complete(db, receipt, result)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "recovery": "refresh_resource"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/documents/{document_id}/hp", response_model=HPDocumentResponse)
def read_hp(document_id: UUID, db: Session = Depends(get_db)):
    try:
        return get_hp_document(db, document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
