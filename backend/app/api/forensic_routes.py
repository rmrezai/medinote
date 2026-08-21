from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import User
from app.services.security_service import require_admin
from app.services.audit_ledger_service import encounter_forensic_export, verify_chain

router = APIRouter(prefix='/api/v1/forensics', tags=['forensics'])

@router.get('/audit-chain/verify')
def verify_audit_chain(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return verify_chain(db, admin.organization_id)

@router.get('/encounters/{encounter_id}/export')
def forensic_export(encounter_id: UUID, include_content: bool = False, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        return encounter_forensic_export(db, admin.organization_id, encounter_id, include_content=include_content)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
