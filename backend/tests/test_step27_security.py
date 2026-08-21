from pathlib import Path
from app.core.security import hash_password, verify_password
from app.services.security_service import FINALIZER_ROLES


def test_password_hash_is_salted_and_verifiable():
    one = hash_password('VeryStrongPass123!')
    two = hash_password('VeryStrongPass123!')
    assert one != two
    assert verify_password('VeryStrongPass123!', one)
    assert not verify_password('wrong-password', one)


def test_only_attending_and_admin_finalize():
    assert FINALIZER_ROLES == {'attending', 'administrator'}


def test_security_middleware_protects_api_resources():
    root = Path(__file__).resolve().parents[1] / 'app'
    text = (root / 'core' / 'security_middleware.py').read_text()
    assert "'encounters'" in text
    assert "'documents'" in text
    assert "'medications'" in text
    assert "'safety-flags'" in text
    assert 'Resource not found' in text


def test_frontend_has_login_and_bearer_token():
    root = Path(__file__).resolve().parents[2] / 'frontend'
    js = (root / 'app.js').read_text()
    assert '/auth/login' in js
    assert '/auth/bootstrap' in js
    assert 'Authorization' in js
    assert 'Bearer' in js
    assert 'Sign out' in js
