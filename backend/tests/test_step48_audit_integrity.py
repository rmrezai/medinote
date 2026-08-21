from datetime import date, datetime, timezone
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import (
    AuditEvent, ClinicalDocument, DocumentSection, Encounter, Organization, Patient,
    PhysicianEdit, SafetyFlag, SourceDocument, User,
)
from app.services.audit_ledger_service import encounter_forensic_export, verify_chain
from app.services.security_service import audit

UTC = timezone.utc


def make_db():
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def seed(db):
    org = Organization(name='Audit Test Group'); db.add(org); db.flush()
    user = User(organization_id=org.id, email='admin@audit.test', display_name='Audit Admin', role='administrator', active=True); db.add(user); db.flush()
    patient = Patient(organization_id=org.id, mrn='AUD123', first_name='Case', last_name='Audit', date_of_birth=date(1950,1,1), sex='female'); db.add(patient); db.flush()
    encounter = Encounter(patient_id=patient.id, organization_id=org.id, admission_datetime=datetime(2026,8,20,8,tzinfo=UTC), service='Hospital Medicine', attending_user_id=user.id, identity_status='created_verified'); db.add(encounter); db.flush()
    audit(db, user=user, event_type='encounter_created', encounter_id=encounter.id, object_type='encounter', object_id=encounter.id)
    db.commit()
    return org, user, encounter


def test_audit_chain_is_valid_and_forensic_export_is_phi_minimized():
    db=make_db(); org,user,enc=seed(db)
    source=SourceDocument(encounter_id=enc.id, document_type='progress_note', raw_text='Patient: Case Audit MRN AUD123. Creatinine 2.0. AKI improving.', content_hash='a'*64, imported_by=user.id, identity_status='matched')
    db.add(source); db.flush()
    audit(db,user=user,event_type='chart_source_imported',encounter_id=enc.id,object_type='source_document',object_id=source.id,metadata={'document_type':'progress_note'})
    audit(db,user=user,event_type='encounter_opened',encounter_id=enc.id,object_type='encounter',object_id=enc.id)
    db.commit()
    result=verify_chain(db,org.id)
    assert result['valid'] is True and result['events']==3
    export=encounter_forensic_export(db,org.id,enc.id)
    assert export['include_content'] is False
    assert 'raw_text' not in export['source_manifest'][0]
    assert export['source_manifest'][0]['content_hash']=='a'*64
    assert len(export['audit_chain'])==3 and export['export_sha256']
    full=encounter_forensic_export(db,org.id,enc.id,include_content=True)
    assert full['source_manifest'][0]['raw_text'].startswith('Patient: Case Audit')


def test_audit_rows_are_application_append_only():
    db=make_db(); org,user,enc=seed(db)
    event=db.scalar(select(AuditEvent).where(AuditEvent.encounter_id==enc.id))
    event.event_type='tampered'
    try:
        db.commit(); assert False, 'AuditEvent update should have been rejected'
    except ValueError as exc:
        assert 'append-only' in str(exc); db.rollback()


def test_direct_sql_tamper_is_detected_by_hash_chain():
    db=make_db(); org,user,enc=seed(db)
    audit(db,user=user,event_type='encounter_opened',encounter_id=enc.id,object_type='encounter',object_id=enc.id); db.commit()
    row=db.scalar(select(AuditEvent).where(AuditEvent.encounter_id==enc.id).order_by(AuditEvent.sequence_number.desc()))
    db.execute(text("UPDATE audit_events SET event_type='sql_tamper' WHERE sequence_number=:seq"), {'seq': row.sequence_number}); db.commit()
    result=verify_chain(db,org.id)
    assert result['valid'] is False
    assert any(i['issue']=='event_hash_mismatch' for i in result['issues'])


def test_forensic_export_reconstructs_document_hash_history():
    db=make_db(); org,user,enc=seed(db)
    doc=ClinicalDocument(encounter_id=enc.id, document_type='progress', variant='daily', status='finalized', generated_by=user.id, approved_by=user.id, generated_state_version=3, edit_version=4)
    db.add(doc); db.flush()
    sec=DocumentSection(document_id=doc.id,section_type='Assessment & Plan',sort_order=1,generated_content='AI original',physician_content='Physician final',approval_status='approved',approved_by=user.id)
    db.add(sec); db.flush()
    edit=PhysicianEdit(document_id=doc.id,section_id=sec.id,action='edit',original_generated_content='AI original',active_generated_content='AI original',final_physician_content='Physician final',edited_by=user.id)
    db.add(edit)
    flag=SafetyFlag(encounter_id=enc.id,document_id=doc.id,section_id=sec.id,category='medication_conflict',severity='high',description='test',status='resolved',audit_version='audit-deterministic-v0.1',resolved_by=user.id)
    db.add(flag)
    audit(db,user=user,event_type='document_generated',encounter_id=enc.id,object_type='clinical_document',object_id=doc.id,metadata={'document_type':'progress','generated_state_version':3})
    audit(db,user=user,event_type='document_section_updated',encounter_id=enc.id,object_type='document_section',object_id=sec.id,metadata={'content_sha256':'x'*64})
    audit(db,user=user,event_type='document_finalized',encounter_id=enc.id,object_type='clinical_document',object_id=doc.id,metadata={'status':'finalized'})
    db.commit()
    export=encounter_forensic_export(db,org.id,enc.id)
    d=export['documents'][0]
    assert d['generated_state_version']==3
    assert d['sections'][0]['generated_sha256']
    assert d['sections'][0]['physician_content_sha256']
    assert d['physician_edits'][0]['original_generated_sha256']
    assert d['physician_edits'][0]['final_physician_sha256']
    assert d['safety_flags'][0]['category']=='medication_conflict'
    assert d['final_text_sha256']
