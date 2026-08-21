from datetime import datetime, timezone
from uuid import UUID
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.security import hash_session_token, utcnow
from app.db.session import get_db
from app.models import AuthSession, AuditEvent, User, Organization
from app.core.config import settings
from app.services.audit_ledger_service import prepare_event_chain

ALLOWED_ROLES = {'attending', 'resident', 'app', 'administrator'}
FINALIZER_ROLES = {'attending', 'administrator'}


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    if settings.test_bypass_auth:
        user = db.scalar(select(User).order_by(User.created_at))
        if user:
            return user
        org = db.scalar(select(Organization).order_by(Organization.created_at))
        if not org:
            org = Organization(name='Test Organization'); db.add(org); db.flush()
        user = User(organization_id=org.id, email='test@medinote.local', display_name='Test User', role='administrator', active=True)
        db.add(user); db.commit(); db.refresh(user)
        return user
    existing = getattr(request.state, 'current_user', None)
    if existing is not None:
        return existing
    auth = request.headers.get('authorization', '')
    if not auth.lower().startswith('bearer '):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required')
    raw = auth.split(' ', 1)[1].strip()
    token_hash = hash_session_token(raw)
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash, AuthSession.revoked == False))  # noqa: E712
    now = utcnow()
    if not session or session.expires_at.replace(tzinfo=session.expires_at.tzinfo or timezone.utc) <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Session expired or invalid')
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User inactive')
    session.last_seen_at = now
    db.commit()
    request.state.current_user = user
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != 'administrator':
        raise HTTPException(status_code=403, detail='Administrator role required')
    return user


def require_finalizer(user: User = Depends(current_user)) -> User:
    if user.role not in FINALIZER_ROLES:
        raise HTTPException(status_code=403, detail='Attending or administrator role required')
    return user


def audit(db: Session, *, user: User, event_type: str, encounter_id: UUID | None = None, object_type: str | None = None, object_id: UUID | None = None, metadata: dict | None = None):
    # Do not place raw chart text, names, MRNs, DOBs, note bodies, or other PHI in metadata.
    event = AuditEvent(
        organization_id=user.organization_id,
        user_id=user.id,
        encounter_id=encounter_id,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        metadata_json=metadata,
    )
    prepare_event_chain(db, event)
    db.add(event)
    return event
