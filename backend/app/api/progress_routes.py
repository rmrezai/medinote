from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.services.security_service import current_user, require_finalizer, audit
from app.services.concurrency_service import ConcurrencyConflict
from app.services.idempotency_service import begin as idem_begin, complete as idem_complete, IdempotencyConflict
from app.schemas.progress import (
    DocumentApprovalResponse, DocumentApproveRequest, PhysicianEditRead,
    ProgressDocumentResponse, ProgressGenerateRequest, ProgressSection,
    ProgressSectionRegenerateRequest, ProgressSectionUpdate,
)
from app.services.progress_service import (
    approve_progress_document, generate_progress_document, get_progress_document,
    list_physician_edits, regenerate_progress_section, update_progress_section,
)

router = APIRouter(prefix="/api/v1")


@router.post("/encounters/{encounter_id}/documents/progress", response_model=ProgressDocumentResponse)
def generate_progress(encounter_id: UUID, payload: ProgressGenerateRequest, user: User = Depends(current_user), db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    try:
        receipt, cached = idem_begin(db, organization_id=user.organization_id, user_id=user.id, key=idempotency_key, method="POST", path=f"/api/v1/encounters/{encounter_id}/documents/progress", payload=payload.model_dump())
        if cached is not None:
            return cached
        result = generate_progress_document(db, encounter_id, payload.variant, user.id)
        audit(db, user=user, event_type="document_generated", encounter_id=encounter_id, object_type="clinical_document", object_id=result["document_id"], metadata={"document_type":"progress","variant":payload.variant,"generated_state_version":result.get("generated_state_version")})
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


@router.get("/documents/{document_id}/progress", response_model=ProgressDocumentResponse)
def read_progress(document_id: UUID, db: Session = Depends(get_db)):
    try:
        return get_progress_document(db, document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/documents/{document_id}/sections/{section_id}", response_model=ProgressSection)
def update_section(document_id: UUID, section_id: UUID, payload: ProgressSectionUpdate, user: User = Depends(current_user), db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    try:
        receipt, cached = idem_begin(db, organization_id=user.organization_id, user_id=user.id, key=idempotency_key, method="PATCH", path=f"/api/v1/documents/{document_id}/sections/{section_id}", payload=payload.model_dump())
        if cached is not None:
            return cached
        result = update_progress_section(db, document_id, section_id, payload.physician_content, payload.action, user.id, payload.expected_section_version, payload.expected_document_version)
        audit(db, user=user, event_type="document_section_updated", object_type="document_section", object_id=section_id, metadata={"document_id":str(document_id),"action":payload.action,"section_version":result.edit_version,"content_sha256":__import__("hashlib").sha256((payload.physician_content or "").encode()).hexdigest()})
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


@router.post("/documents/{document_id}/sections/{section_id}/regenerate", response_model=ProgressSection)
def regenerate_section(document_id: UUID, section_id: UUID, payload: ProgressSectionRegenerateRequest, user: User = Depends(current_user), db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    try:
        receipt, cached = idem_begin(db, organization_id=user.organization_id, user_id=user.id, key=idempotency_key, method="POST", path=f"/api/v1/documents/{document_id}/sections/{section_id}/regenerate", payload=payload.model_dump())
        if cached is not None:
            return cached
        result = regenerate_progress_section(db, document_id, section_id, payload.instruction, user.id, payload.expected_section_version, payload.expected_document_version)
        audit(db, user=user, event_type="document_section_regenerated", object_type="document_section", object_id=section_id, metadata={"document_id":str(document_id),"section_version":result.edit_version,"instruction_sha256":__import__("hashlib").sha256((payload.instruction or "").encode()).hexdigest()})
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


@router.post("/documents/{document_id}/approve", response_model=DocumentApprovalResponse)
def approve_document(document_id: UUID, payload: DocumentApproveRequest, user: User = Depends(require_finalizer), db: Session = Depends(get_db), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    try:
        receipt, cached = idem_begin(db, organization_id=user.organization_id, user_id=user.id, key=idempotency_key, method="POST", path=f"/api/v1/documents/{document_id}/approve", payload=payload.model_dump())
        if cached is not None:
            return cached
        result = approve_progress_document(db, document_id, user.id, payload.expected_document_version)
        audit(db, user=user, event_type="document_approved", object_type="clinical_document", object_id=document_id, metadata={"document_version":result.edit_version})
        db.commit()
        return idem_complete(db, receipt, result)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "recovery": "refresh_resource"}) from exc
    except ConcurrencyConflict as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "current_version": exc.current_version}) from exc


@router.get("/documents/{document_id}/edits", response_model=list[PhysicianEditRead])
def document_edits(document_id: UUID, db: Session = Depends(get_db)):
    try:
        return list_physician_edits(db, document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
