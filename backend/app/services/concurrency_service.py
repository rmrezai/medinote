from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.models import EditLease, ClinicalDocument, DocumentSection, Encounter, User

LEASE_MINUTES = 5

class ConcurrencyConflict(ValueError):
    def __init__(self, message: str, current_version: int | None = None):
        super().__init__(message)
        self.current_version = current_version

def assert_version(expected: int | None, current: int, resource: str):
    if expected is not None and expected != current:
        raise ConcurrencyConflict(f"{resource} changed since this screen was loaded. Refresh before saving.", current)

def bump_document(doc: ClinicalDocument):
    doc.edit_version = int(doc.edit_version or 1) + 1

def bump_section(section: DocumentSection):
    section.edit_version = int(section.edit_version or 1) + 1

def acquire_lease(db: Session, *, user: User, encounter_id: UUID, resource_type: str, resource_id: UUID):
    now=datetime.now(timezone.utc); expiry=now+timedelta(minutes=LEASE_MINUTES)
    db.execute(delete(EditLease).where(EditLease.expires_at <= now))
    lease=db.scalar(select(EditLease).where(EditLease.organization_id==user.organization_id, EditLease.resource_type==resource_type, EditLease.resource_id==resource_id))
    if lease and lease.user_id != user.id:
        holder=db.get(User, lease.user_id)
        return {"acquired": False, "holder_user_id": lease.user_id, "holder_display_name": holder.display_name if holder else None, "expires_at": lease.expires_at}
    if not lease:
        lease=EditLease(organization_id=user.organization_id, encounter_id=encounter_id, resource_type=resource_type, resource_id=resource_id, user_id=user.id, expires_at=expiry)
        db.add(lease)
    else:
        lease.expires_at=expiry; lease.refreshed_at=now
    db.commit(); db.refresh(lease)
    return {"acquired": True, "holder_user_id": user.id, "holder_display_name": user.display_name, "expires_at": lease.expires_at}

def release_lease(db: Session, *, user: User, resource_type: str, resource_id: UUID):
    lease=db.scalar(select(EditLease).where(EditLease.organization_id==user.organization_id, EditLease.resource_type==resource_type, EditLease.resource_id==resource_id, EditLease.user_id==user.id))
    if lease: db.delete(lease); db.commit()
    return {"released": bool(lease)}
