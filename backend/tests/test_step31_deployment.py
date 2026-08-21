from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]


def test_pilot_compose_does_not_publish_database_or_api_ports():
    text = (ROOT / 'docker-compose.pilot.yml').read_text()
    db_block = text.split('  db:', 1)[1].split('\n  api:', 1)[0]
    api_block = text.split('  api:', 1)[1].split('\n  frontend:', 1)[0]
    assert 'ports:' not in db_block
    assert 'ports:' not in api_block
    assert 'expose:' in api_block


def test_pilot_compose_forces_auth_and_has_health_checks():
    text = (ROOT / 'docker-compose.pilot.yml').read_text()
    assert 'TEST_BYPASS_AUTH: "false"' in text
    assert '/api/v1/health' in text
    assert 'pg_isready' in text


def test_env_template_contains_no_real_secrets():
    text = (ROOT / '.env.pilot.example').read_text()
    assert 'CHANGE_ME' in text
    assert 'BACKUP_PASSPHRASE=' in text
    assert 'TEST_BYPASS_AUTH=false' in text


def test_reverse_proxy_has_tls_security_headers():
    text = (ROOT / 'deploy/caddy/Caddyfile').read_text()
    assert 'Strict-Transport-Security' in text
    assert 'X-Content-Type-Options' in text
    assert 'X-Frame-Options "DENY"' in text
    assert 'reverse_proxy api:8000' in text


def test_backup_is_encrypted_and_plain_temp_removed():
    text = (ROOT / 'deploy/scripts/backup.sh').read_text()
    assert 'openssl enc -aes-256-cbc' in text
    assert '-pbkdf2' in text
    assert 'rm -f "$TMP"' in text
