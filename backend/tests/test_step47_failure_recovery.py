from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
import pytest

from app.db.base import Base
from app.models import Organization, User, Patient, Encounter, ClinicalDocument, DocumentSection, PhysicianEdit, IdempotencyReceipt
from app.services.idempotency_service import begin, complete, IdempotencyConflict
from app.services.progress_service import generate_progress_document, update_progress_section


def make_db():
    engine=create_engine('sqlite+pysqlite:///:memory:',future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), engine


def seed(db):
    org=Organization(name='Step47'); db.add(org); db.flush()
    u=User(organization_id=org.id,email='step47@test',display_name='Recovery Attending',role='attending',active=True); db.add(u); db.flush()
    p=Patient(organization_id=org.id,mrn='R47',first_name='Recovery',last_name='Patient'); db.add(p); db.flush()
    e=Encounter(patient_id=p.id,organization_id=org.id,status='active',identity_status='created_verified'); db.add(e); db.commit()
    return org,u,e


def test_duplicate_section_save_returns_cached_result_and_does_not_duplicate_edit():
    db,_=make_db(); org,u,e=seed(db)
    d=generate_progress_document(db,e.id,'daily',u.id)
    doc=db.get(ClinicalDocument,d['document_id'])
    sec=db.scalar(select(DocumentSection).where(DocumentSection.document_id==doc.id).order_by(DocumentSection.sort_order))
    payload={'action':'edit','physician_content':'Recovered physician edit','expected_section_version':sec.edit_version,'expected_document_version':None}
    path=f'/api/v1/documents/{doc.id}/sections/{sec.id}'
    receipt,cached=begin(db,organization_id=org.id,user_id=u.id,key='save-1',method='PATCH',path=path,payload=payload)
    assert cached is None
    result=update_progress_section(db,doc.id,sec.id,payload['physician_content'],'edit',u.id,sec.edit_version,None)
    complete(db,receipt,result)
    edits_before=db.scalar(select(func.count()).select_from(PhysicianEdit).where(PhysicianEdit.section_id==sec.id))

    receipt2,cached2=begin(db,organization_id=org.id,user_id=u.id,key='save-1',method='PATCH',path=path,payload=payload)
    assert receipt2.status=='completed'
    assert cached2['physician_content']=='Recovered physician edit'
    edits_after=db.scalar(select(func.count()).select_from(PhysicianEdit).where(PhysicianEdit.section_id==sec.id))
    assert edits_before==edits_after==1


def test_same_key_cannot_be_reused_for_different_clinical_request():
    db,_=make_db(); org,u,e=seed(db)
    r,_=begin(db,organization_id=org.id,user_id=u.id,key='same-key',method='POST',path='/x',payload={'state':'stop'})
    complete(db,r,{'ok':True})
    with pytest.raises(IdempotencyConflict):
        begin(db,organization_id=org.id,user_id=u.id,key='same-key',method='POST',path='/x',payload={'state':'resume'})


def test_uncertain_in_progress_operation_is_not_reexecuted_after_retry():
    db,_=make_db(); org,u,e=seed(db)
    receipt,_=begin(db,organization_id=org.id,user_id=u.id,key='uncertain-1',method='POST',path='/clinical-action',payload={'x':1})
    assert receipt.status=='in_progress'
    with pytest.raises(IdempotencyConflict):
        begin(db,organization_id=org.id,user_id=u.id,key='uncertain-1',method='POST',path='/clinical-action',payload={'x':1})


def test_generation_commit_failure_can_be_rolled_back_without_partial_document(monkeypatch):
    db,engine=make_db(); org,u,e=seed(db)
    RealSession=sessionmaker(bind=engine)
    db2=RealSession()
    original_commit=db2.commit
    calls={'n':0}
    def fail_first_commit():
        calls['n']+=1
        if calls['n']==1:
            raise RuntimeError('simulated database failure')
        return original_commit()
    monkeypatch.setattr(db2,'commit',fail_first_commit)
    with pytest.raises(RuntimeError):
        generate_progress_document(db2,e.id,'daily',u.id)
    db2.rollback(); db2.close()
    verify=RealSession()
    assert verify.scalar(select(func.count()).select_from(ClinicalDocument).where(ClinicalDocument.encounter_id==e.id))==0
    assert verify.scalar(select(func.count()).select_from(DocumentSection))==0


def test_completed_receipt_stores_recoverable_response():
    db,_=make_db(); org,u,e=seed(db)
    r,_=begin(db,organization_id=org.id,user_id=u.id,key='finalize-retry',method='POST',path='/finalize',payload={'expected_document_version':4})
    complete(db,r,{'document_id':'abc','status':'finalized'})
    saved=db.get(IdempotencyReceipt,r.id)
    assert saved.status=='completed'
    assert saved.response_json['status']=='finalized'
    assert saved.completed_at is not None
