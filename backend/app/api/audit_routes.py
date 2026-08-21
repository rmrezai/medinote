from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.services.security_service import current_user, require_finalizer, audit
from app.schemas.audit import AuditResponse, FinalizeRequest, FinalizeResponse, SafetyFlagRead, SafetyFlagResolveRequest
from app.services.audit_service import audit_document, finalize_document, list_flags, resolve_flag, refresh_document
from app.services.concurrency_service import ConcurrencyConflict
from app.services.idempotency_service import begin as idem_begin, complete as idem_complete, IdempotencyConflict

router = APIRouter(prefix="/api/v1")

@router.post("/documents/{document_id}/audit", response_model=AuditResponse)
def run_audit(document_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        result = audit_document(db, document_id)
        audit(db, user=user, event_type="safety_audit_run", object_type="clinical_document", object_id=document_id, metadata={"audit_version":result.get("audit_version"),"blocking_flags":result.get("blocking_flags"),"warning_flags":result.get("warning_flags")})
        db.commit()
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/documents/{document_id}/safety-flags", response_model=list[SafetyFlagRead])
def read_flags(document_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return list_flags(db, document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.post("/safety-flags/{flag_id}/resolve", response_model=SafetyFlagRead)
def resolve(flag_id: UUID, payload: SafetyFlagResolveRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        flag = resolve_flag(db, flag_id, payload.resolution, user.id, payload.resolution_type)
        audit(db, user=user, event_type="safety_flag_resolved", encounter_id=flag.encounter_id, object_type="safety_flag", object_id=flag.id, metadata={"category":flag.category,"severity":flag.severity,"resolution_type":payload.resolution_type,"resolution_sha256":__import__("hashlib").sha256(payload.resolution.encode()).hexdigest()})
        db.commit()
        return flag
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/documents/{document_id}/refresh")
def refresh(document_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        result = refresh_document(db, document_id, user.id)
        audit(db, user=user, event_type="document_refreshed_from_current_state", object_type="clinical_document", object_id=document_id, metadata={"generated_state_version": result["generated_state_version"], "current_state_version": result["current_state_version"]})
        db.commit()
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConcurrencyConflict as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "current_version": exc.current_version}) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "recovery": "refresh_resource"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/documents/{document_id}/finalize", response_model=FinalizeResponse)
def finalize(document_id: UUID, payload: FinalizeRequest, user: User = Depends(require_finalizer), db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    try:
        receipt, cached = idem_begin(db, organization_id=user.organization_id, user_id=user.id, key=idempotency_key, method="POST", path=f"/api/v1/documents/{document_id}/finalize", payload=payload.model_dump())
        if cached is not None:
            return cached
        result = finalize_document(db, document_id, user.id, payload.expected_document_version)
        audit(db, user=user, event_type="document_finalized", object_type="clinical_document", object_id=document_id, metadata={"status":result.get("status"),"finalized_at":str(result.get("finalized_at")) if result.get("finalized_at") else None,"document_version":payload.expected_document_version})
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
