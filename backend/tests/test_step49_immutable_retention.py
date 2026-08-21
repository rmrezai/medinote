from datetime import date, datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models import Encounter, Organization, Patient, User
from app.services.audit_ledger_service import verify_chain
from app.services.retention_service import (
    create_external_anchor, verify_external_anchors, place_legal_hold, release_legal_hold,
    create_retention_snapshot, retention_status, verify_retention_snapshot,
)
from app.services.security_service import audit

UTC=timezone.utc

def make_db():
    engine=create_engine('sqlite+pysqlite:///:memory:',future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()

def seed(db):
    org=Organization(name='Retention Test'); db.add(org); db.flush()
    user=User(organization_id=org.id,email='admin@ret.test',display_name='Admin',role='administrator',active=True); db.add(user); db.flush()
    patient=Patient(organization_id=org.id,mrn='RET001',first_name='Retain',last_name='Case',date_of_birth=date(1950,1,1),sex='female'); db.add(patient); db.flush()
    enc=Encounter(patient_id=patient.id,organization_id=org.id,admission_datetime=datetime(2026,8,20,8,tzinfo=UTC),service='Hospital Medicine',attending_user_id=user.id,identity_status='created_verified'); db.add(enc); db.flush()
    audit(db,user=user,event_type='encounter_created',encounter_id=enc.id,object_type='encounter',object_id=enc.id); db.commit()
    return org,user,enc

def setup_store(tmp_path):
    settings.immutable_store_path=str(tmp_path/'worm')
    settings.retention_encryption_key_hex='11'*32

def test_external_anchor_is_independent_and_tamper_detectable(tmp_path):
    setup_store(tmp_path); db=make_db(); org,user,enc=seed(db)
    a=create_external_anchor(db,user)
    assert Path(a['storage_uri']).exists()
    assert verify_external_anchors(db,org.id)['valid'] is True
    # Simulate privileged external-storage tampering.
    p=Path(a['storage_uri']); p.chmod(0o644); p.write_text('{}')
    result=verify_external_anchors(db,org.id)
    assert result['valid'] is False
    assert any(i['issue']=='artifact_hash_mismatch' for i in result['issues'])

def test_legal_hold_freezes_retention_and_release_restores_policy(tmp_path):
    setup_store(tmp_path); db=make_db(); org,user,enc=seed(db)
    hold=place_legal_hold(db,user,'MATTER-001','Preserve records for legal review',enc.id)
    snap=create_retention_snapshot(db,user,enc.id,retention_days=30)
    assert snap.legal_hold_active is True and snap.retention_until is None
    status=retention_status(db,org.id,enc.id)
    assert status['legal_hold_active'] is True and status['eligible_for_deletion'] is False
    release_legal_hold(db,user,hold.id,'Matter closed')
    snap2=create_retention_snapshot(db,user,enc.id,retention_days=30)
    assert snap2.legal_hold_active is False and snap2.retention_until is not None

def test_retention_snapshot_is_encrypted_and_verifiable(tmp_path):
    setup_store(tmp_path); db=make_db(); org,user,enc=seed(db)
    snap=create_retention_snapshot(db,user,enc.id,retention_days=90)
    raw=Path(snap.storage_uri).read_text()
    assert 'forensic_export' not in raw
    assert 'AES-256-GCM' in raw
    v=verify_retention_snapshot(db,org.id,snap.id,decrypt=False)
    assert v['valid'] is True and v['encrypted'] is True
    full=verify_retention_snapshot(db,org.id,snap.id,decrypt=True)
    assert full['payload']['encounter_id']==str(enc.id)

def test_anchor_refuses_invalid_audit_chain(tmp_path):
    setup_store(tmp_path); db=make_db(); org,user,enc=seed(db)
    # Chain valid first.
    assert verify_chain(db,org.id)['valid'] is True
    event=db.query(__import__('app.models',fromlist=['AuditEvent']).AuditEvent).first()
    db.execute(__import__('sqlalchemy').text("UPDATE audit_events SET event_type='tamper' WHERE sequence_number=:seq"),{'seq':event.sequence_number}); db.commit()
    try:
        create_external_anchor(db,user); assert False
    except ValueError as exc:
        assert 'invalid' in str(exc).lower()
