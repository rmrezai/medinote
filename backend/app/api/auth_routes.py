from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.security import hash_password, issue_session_token, session_expiry, utcnow, verify_password
from app.db.session import get_db
from app.models import AuthSession, Organization, User, AuditEvent
from app.schemas.auth import BootstrapAdminRequest, LoginRequest, LoginResponse, UserCreateRequest, UserRead
from app.services.security_service import audit, current_user, require_admin

router = APIRouter(prefix='/api/v1/auth', tags=['auth'])


@router.post('/bootstrap', response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def bootstrap(payload: BootstrapAdminRequest, db: Session = Depends(get_db)):
    if db.scalar(select(func.count(User.id))) > 0:
        raise HTTPException(status_code=409, detail='Bootstrap already completed')
    org = Organization(name=payload.organization_name)
    db.add(org); db.flush()
    user = User(organization_id=org.id, email=payload.email.strip().lower(), display_name=payload.display_name, role='administrator', password_hash=hash_password(payload.password))
    db.add(user); db.flush()
    raw, token_hash = issue_session_token(); expires = session_expiry()
    db.add(AuthSession(user_id=user.id, token_hash=token_hash, expires_at=expires))
    audit(db, user=user, event_type='bootstrap_admin_created', object_type='user', object_id=user.id)
    db.commit(); db.refresh(user)
    return LoginResponse(access_token=raw, expires_at=expires, user=user)


@router.post('/login', response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    now = utcnow()
    if not user or not user.active:
        raise HTTPException(status_code=401, detail='Invalid credentials')
    if user.locked_until and user.locked_until.replace(tzinfo=user.locked_until.tzinfo or now.tzinfo) > now:
        raise HTTPException(status_code=423, detail='Account temporarily locked')
    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= 5:
            user.locked_until = now + timedelta(minutes=15)
            user.failed_login_count = 0
        db.commit()
        raise HTTPException(status_code=401, detail='Invalid credentials')
    user.failed_login_count = 0; user.locked_until = None; user.last_login_at = now
    raw, token_hash = issue_session_token(); expires = session_expiry()
    db.add(AuthSession(user_id=user.id, token_hash=token_hash, expires_at=expires))
    audit(db, user=user, event_type='login_success', object_type='user', object_id=user.id)
    db.commit(); db.refresh(user)
    return LoginResponse(access_token=raw, expires_at=expires, user=user)


@router.post('/logout', status_code=204)
def logout(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    auth = request.headers.get('authorization', '').split(' ', 1)[1]
    from app.core.security import hash_session_token
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_session_token(auth)))
    if session: session.revoked = True
    audit(db, user=user, event_type='logout', object_type='user', object_id=user.id)
    db.commit()


@router.get('/me', response_model=UserRead)
def me(user: User = Depends(current_user)):
    return user


@router.get('/audit-events')
def audit_events(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = list(db.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == admin.organization_id)
        .order_by(AuditEvent.occurred_at.desc())
        .limit(200)
    ))
    return [
        {
            'id': str(row.id),
            'user_id': str(row.user_id) if row.user_id else None,
            'encounter_id': str(row.encounter_id) if row.encounter_id else None,
            'event_type': row.event_type,
            'object_type': row.object_type,
            'object_id': str(row.object_id) if row.object_id else None,
            'metadata': row.metadata_json or {},
            'sequence_number': row.sequence_number,
            'previous_hash': row.previous_hash,
            'metadata_hash': row.metadata_hash,
            'event_hash': row.event_hash,
            'occurred_at': row.occurred_at,
        }
        for row in rows
    ]


@router.post('/users', response_model=UserRead, status_code=201)
def create_user(payload: UserCreateRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.role not in {'attending','resident','app','administrator'}:
        raise HTTPException(status_code=422, detail='Invalid role')
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail='Email already exists')
    user = User(organization_id=admin.organization_id, email=email, display_name=payload.display_name, role=payload.role, password_hash=hash_password(payload.password))
    db.add(user); db.flush()
    audit(db, user=admin, event_type='user_created', object_type='user', object_id=user.id, metadata={'role': payload.role})
    db.commit(); db.refresh(user)
    return user
