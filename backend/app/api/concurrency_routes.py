from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import ClinicalDocument, Medication, Contradiction, Encounter, User
from app.services.security_service import current_user
from app.services.concurrency_service import acquire_lease, release_lease

router=APIRouter(prefix="/api/v1", tags=["concurrency"])

def _encounter_for(db, resource_type, resource_id):
    if resource_type == "document":
        obj=db.get(ClinicalDocument, resource_id); return obj.encounter_id if obj else None
    if resource_type == "medication":
        obj=db.get(Medication, resource_id); return obj.encounter_id if obj else None
    if resource_type == "contradiction":
        obj=db.get(Contradiction, resource_id); return obj.encounter_id if obj else None
    if resource_type == "encounter": return resource_id if db.get(Encounter, resource_id) else None
    return None

@router.post("/edit-leases/{resource_type}/{resource_id}")
def acquire(resource_type: str, resource_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    enc_id=_encounter_for(db, resource_type, resource_id)
    enc=db.get(Encounter, enc_id) if enc_id else None
    if not enc or enc.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Resource not found")
    return acquire_lease(db,user=user,encounter_id=enc.id,resource_type=resource_type,resource_id=resource_id)

@router.delete("/edit-leases/{resource_type}/{resource_id}")
def release(resource_type: str, resource_id: UUID, user: User=Depends(current_user), db: Session=Depends(get_db)):
    return release_lease(db,user=user,resource_type=resource_type,resource_id=resource_id)
