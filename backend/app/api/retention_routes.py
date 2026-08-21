from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import User
from app.services.security_service import require_admin
from app.services.retention_service import create_external_anchor, verify_external_anchors, place_legal_hold, release_legal_hold, create_retention_snapshot, retention_status, verify_retention_snapshot

router=APIRouter(prefix='/api/v1/retention',tags=['retention'])

class HoldRequest(BaseModel):
    matter_reference:str=Field(min_length=1,max_length=200)
    reason:str=Field(min_length=1,max_length=2000)
    encounter_id:UUID|None=None
class ReleaseRequest(BaseModel):
    reason:str=Field(min_length=1,max_length=2000)
class SnapshotRequest(BaseModel):
    retention_days:int|None=Field(default=None,ge=1,le=36500)

@router.post('/audit-anchors')
def anchor(admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return create_external_anchor(db,admin)
    except ValueError as e: raise HTTPException(status_code=409,detail=str(e))

@router.get('/audit-anchors/verify')
def verify(admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    return verify_external_anchors(db,admin.organization_id)

@router.post('/legal-holds')
def create_hold(body:HoldRequest,admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:r=place_legal_hold(db,admin,body.matter_reference,body.reason,body.encounter_id); return {'hold_id':str(r.id),'status':r.status,'matter_reference':r.matter_reference,'encounter_id':str(r.encounter_id) if r.encounter_id else None,'placed_at':r.placed_at}
    except LookupError as e: raise HTTPException(status_code=404,detail=str(e))

@router.post('/legal-holds/{hold_id}/release')
def release(hold_id:UUID,body:ReleaseRequest,admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:r=release_legal_hold(db,admin,hold_id,body.reason); return {'hold_id':str(r.id),'status':r.status,'released_at':r.released_at}
    except LookupError as e: raise HTTPException(status_code=404,detail=str(e))
    except ValueError as e: raise HTTPException(status_code=409,detail=str(e))

@router.post('/encounters/{encounter_id}/snapshot')
def snapshot(encounter_id:UUID,body:SnapshotRequest,admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:r=create_retention_snapshot(db,admin,encounter_id,body.retention_days); return {'snapshot_id':str(r.id),'content_sha256':r.content_sha256,'storage_uri':r.storage_uri,'retention_until':r.retention_until,'legal_hold_active':r.legal_hold_active}
    except LookupError as e: raise HTTPException(status_code=404,detail=str(e))

@router.get('/encounters/{encounter_id}/status')
def status(encounter_id:UUID,admin:User=Depends(require_admin),db:Session=Depends(get_db)):
    try:return retention_status(db,admin.organization_id,encounter_id)
    except LookupError as e: raise HTTPException(status_code=404,detail=str(e))

@router.get('/snapshots/{snapshot_id}/verify')
def verify_snapshot(snapshot_id:UUID, include_decrypted_payload:bool=False, admin:User=Depends(require_admin), db:Session=Depends(get_db)):
    try:return verify_retention_snapshot(db,admin.organization_id,snapshot_id,decrypt=include_decrypted_payload)
    except LookupError as e: raise HTTPException(status_code=404,detail=str(e))
    except ValueError as e: raise HTTPException(status_code=503,detail=str(e))
