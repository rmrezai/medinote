from uuid import UUID
from datetime import timezone
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from app.core.security import hash_session_token, utcnow
from app.db.session import SessionLocal
from app.models import AuthSession, ClinicalDocument, Encounter, Medication, SafetyFlag, SourceDocument, User
from app.core.config import settings

PUBLIC_PATHS = {
    '/api/v1/health',
    '/api/v1/ready',
    '/api/v1/auth/login',
    '/api/v1/auth/bootstrap',
    '/docs', '/openapi.json', '/redoc',
}


def _uuid(value: str):
    try: return UUID(value)
    except Exception: return None


def _resource_org(db, path: str):
    parts = [p for p in path.split('/') if p]
    # api/v1/encounters/{id}
    if len(parts) >= 4 and parts[2] == 'encounters':
        rid = _uuid(parts[3])
        obj = db.get(Encounter, rid) if rid else None
        return obj.organization_id if obj else None
    if len(parts) >= 4 and parts[2] == 'documents':
        rid = _uuid(parts[3]); doc = db.get(ClinicalDocument, rid) if rid else None
        enc = db.get(Encounter, doc.encounter_id) if doc else None
        return enc.organization_id if enc else None
    if len(parts) >= 4 and parts[2] == 'medications':
        rid = _uuid(parts[3]); med = db.get(Medication, rid) if rid else None
        enc = db.get(Encounter, med.encounter_id) if med else None
        return enc.organization_id if enc else None
    if len(parts) >= 4 and parts[2] == 'safety-flags':
        rid = _uuid(parts[3]); flag = db.get(SafetyFlag, rid) if rid else None
        enc = db.get(Encounter, flag.encounter_id) if flag else None
        return enc.organization_id if enc else None
    if len(parts) >= 4 and parts[2] == 'sources':
        rid = _uuid(parts[3]); source = db.get(SourceDocument, rid) if rid else None
        enc = db.get(Encounter, source.encounter_id) if source else None
        return enc.organization_id if enc else None
    return None


async def security_middleware(request: Request, call_next):
    path = request.url.path.rstrip('/') or '/'
    if settings.test_bypass_auth:
        return await call_next(request)
    if path in PUBLIC_PATHS or not path.startswith('/api/v1'):
        return await call_next(request)
    auth = request.headers.get('authorization', '')
    if not auth.lower().startswith('bearer '):
        return JSONResponse(status_code=401, content={'detail': 'Authentication required'})
    raw = auth.split(' ', 1)[1].strip()
    with SessionLocal() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_session_token(raw), AuthSession.revoked == False))  # noqa: E712
        expires = session.expires_at.replace(tzinfo=session.expires_at.tzinfo or timezone.utc) if session else None
        if not session or expires <= utcnow():
            return JSONResponse(status_code=401, content={'detail': 'Session expired or invalid'})
        user = db.get(User, session.user_id)
        if not user or not user.active:
            return JSONResponse(status_code=401, content={'detail': 'User inactive'})
        resource_org = _resource_org(db, path)
        if resource_org is not None and resource_org != user.organization_id:
            # Return 404 to avoid leaking cross-tenant object existence.
            return JSONResponse(status_code=404, content={'detail': 'Resource not found'})
        request.state.current_user = user
        response = await call_next(request)
        return response
