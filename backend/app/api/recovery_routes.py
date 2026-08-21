from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import IdempotencyReceipt, User
from app.services.security_service import current_user

router = APIRouter(prefix="/api/v1", tags=["recovery"])

@router.get("/operations/idempotency/{key}")
def idempotency_status(key: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    receipt = db.scalar(select(IdempotencyReceipt).where(
        IdempotencyReceipt.organization_id == user.organization_id,
        IdempotencyReceipt.user_id == user.id,
        IdempotencyReceipt.idempotency_key == key,
    ))
    if not receipt:
        raise HTTPException(status_code=404, detail="Operation not found")
    return {
        "idempotency_key": receipt.idempotency_key,
        "status": receipt.status,
        "method": receipt.method,
        "path": receipt.path,
        "created_at": receipt.created_at,
        "completed_at": receipt.completed_at,
        "response": receipt.response_json if receipt.status == "completed" else None,
        "recovery_action": "use_cached_response" if receipt.status == "completed" else "refresh_target_resource_before_retrying",
    }
