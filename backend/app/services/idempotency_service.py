import hashlib, json
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder
from app.models import IdempotencyReceipt

class IdempotencyConflict(Exception):
    pass


def _digest(payload) -> str:
    encoded = json.dumps(jsonable_encoder(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def begin(db: Session, *, organization_id: UUID, user_id: UUID, key: str | None, method: str, path: str, payload):
    if not key:
        return None, None
    key = key.strip()
    if not key or len(key) > 120:
        raise ValueError("Idempotency-Key must be 1-120 characters")
    digest = _digest(payload)
    existing = db.scalar(select(IdempotencyReceipt).where(
        IdempotencyReceipt.organization_id == organization_id,
        IdempotencyReceipt.user_id == user_id,
        IdempotencyReceipt.idempotency_key == key,
    ))
    if existing:
        if existing.method != method or existing.path != path or existing.request_hash != digest:
            raise IdempotencyConflict("Idempotency key was already used for a different request")
        if existing.status == "completed":
            return existing, existing.response_json
        raise IdempotencyConflict("Prior request with this idempotency key has an uncertain/in-progress outcome; refresh the resource before retrying")
    receipt = IdempotencyReceipt(
        organization_id=organization_id, user_id=user_id, idempotency_key=key,
        method=method, path=path, request_hash=digest, status="in_progress"
    )
    db.add(receipt)
    try:
        db.commit(); db.refresh(receipt)
    except IntegrityError:
        db.rollback()
        raise IdempotencyConflict("Concurrent request with the same idempotency key is already being processed")
    return receipt, None


def complete(db: Session, receipt: IdempotencyReceipt | None, response):
    if receipt is None:
        return response
    receipt.status = "completed"
    receipt.response_json = jsonable_encoder(response)
    receipt.completed_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(receipt)
    return response


def abandon_known_failure(db: Session, receipt: IdempotencyReceipt | None):
    # Use only when the operation is known not to have committed any clinical state.
    if receipt is not None:
        db.delete(receipt); db.commit()
