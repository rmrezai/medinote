import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

PBKDF2_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PBKDF2_ITERATIONS)
    return f'pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        scheme, iterations, salt_hex, digest_hex = encoded.split('$', 3)
        if scheme != 'pbkdf2_sha256':
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def issue_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    return token, hashlib.sha256(token.encode('utf-8')).hexdigest()


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def session_expiry(hours: int | None = None) -> datetime:
    if hours is None:
        from app.core.config import settings
        hours = settings.session_hours
    return utcnow() + timedelta(hours=hours)
