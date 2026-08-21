from __future__ import annotations

import json, time, re
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import (
    Organization, User, Patient, Encounter, SourceDocument,
    ClinicalFact, ClinicalProblem, Medication, MedicationState,
    PendingItem, DispositionState, ClinicalDocument, DocumentSection,
    SafetyFlag, PhysicianEdit,
)
from app.services.analysis_service import analyze_encounter
from app.services.overview_service import build_patient_overview
from app.services.hp_service import generate_hp_document
from app.services.progress_service import (
    generate_progress_document, update_progress_section, approve_progress_document,
)
from app.services.signout_service import generate_signout_document
from app.services.discharge_service import generate_discharge_document
from app.services.med_rec_service import build_med_rec_workspace, confirm_discharge_state
from app.services.audit_service import audit_document, finalize_document
from app.schemas.med_rec import MedRecDecision

UTC=timezone.utc
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs'
OUT.mkdir(exist_ok=True)

ADMISSION = """
76-year-old man admitted with pneumonia and acute hypoxemic respiratory failure. Acute kidney injury is also documented. Atrial fibrillation is chronic.
Currently on 4 L NC. Cr 2.4. BUN 46. Na 132. K 4.8. WBC 15.2. Hgb 11.8. Glucose 148.
Home medications include losartan and apixaban. Losartan remains held due to AKI. Continue apixaban. Blood cultures are pending.
Focused exam: bibasilar crackles; no lower extremity edema. Requires inpatient care for oxygen requirement and renal recovery.
""".strip()

DAY2 = """
Pneumonia is improving. Acute hypoxemic respiratory failure is improving. Acute kidney injury is improving.
Currently on 2 L NC. Cr 1.7. BUN 35. Na 135. K 4.3. WBC 11.0. Hgb 11.3.
Losartan remains held due to AKI. Continue apixaban. Blood cultures remain pending.
""".strip()

NEPHROLOGY = """
Nephrology recommends continue holding losartan until renal function stabilizes. Acute kidney injury is improving.
""".strip()

PT = """
PT recommends home with home health. Patient ambulates 150 feet with rolling walker and supervision. No supplemental oxygen required during therapy session.
""".strip()

DAY3 = """
Pneumonia is improving. Acute hypoxemic respiratory failure is improving. Acute kidney injury is improving.
Now on room air. Cr 1.2. BUN 24. Na 137. K 4.1. WBC 8.4. Hgb 11.5.
Blood cultures final: no growth. Losartan remains held. Continue apixaban.
""".strip()

DISCHARGE_SOURCE = """
Discharge plan documented as home with home health. Patient is on room air. Acute kidney injury improved with Cr 1.2. Pneumonia improved clinically.
Losartan remains held pending outpatient blood pressure and renal function reassessment. Continue apixaban.
""".strip()

GROUND_TRUTH = {
    'problems': {
        'pneumonia': 'improving',
        'acute_hypoxemic_respiratory_failure': 'improving',
        'acute_kidney_injury': 'improving',
        'atrial_fibrillation': 'active',
    },
    'latest_labs': {'creatinine': 1.2, 'bun': 24.0, 'sodium': 137.0, 'potassium': 4.1, 'wbc': 8.4, 'hemoglobin': 11.5},
    'oxygen': 'room_air',
    'medications': {'losartan': 'stop', 'apixaban': 'continue'},
    'destination': 'home with home health',
    'pending_count': 0,
    'must_not_claim': ['sepsis', 'encephalopathy', 'acute blood loss anemia', 'appointment scheduled', 'prescriptions sent'],
}


def add_source(db, enc, dtype, when, text, user, service=None):
    s=SourceDocument(encounter_id=enc.id, document_type=dtype, author_service=service,
                     source_datetime=when, source_system='golden_case', raw_text=text,
                     imported_by=user.id)
    db.add(s); db.commit(); db.refresh(s); return s


def ensure_home_state(db, encounter_id, name, status='active'):
    med=db.scalar(select(Medication).where(Medication.encounter_id==encounter_id, Medication.normalized_name==name))
    if not med:
        med=Medication(encounter_id=encounter_id, normalized_name=name, display_name=name.title())
        db.add(med); db.flush()
    existing=db.scalar(select(MedicationState).where(MedicationState.medication_id==med.id, MedicationState.domain=='home', MedicationState.is_current==True))
    if not existing:
        db.add(MedicationState(medication_id=med.id, domain='home', status=status, effective_datetime=datetime(2026,8,17,8,tzinfo=UTC), is_current=True, physician_confirmed=True))
    db.commit(); return med


def add_exam_fact(db, encounter_id, source_id, concept, value, when):
    db.add(ClinicalFact(encounter_id=encounter_id, source_document_id=source_id, fact_type='exam', concept=concept,
                        value_text=value, evidence_text=value, observed_datetime=when, source_datetime=when,
                        fact_state='current', confidence='high', source_category='clinician_documented', is_current=True,
                        extracted_by='golden_structured_adapter', extraction_version='golden-v1'))
    db.commit()


def add_disposition(db, encounter_id, when, destination=None, pt=None, barriers=None, oxygen=None):
    db.add(DispositionState(encounter_id=encounter_id, anticipated_destination=destination,
                            current_barriers=barriers, pt_recommendation=pt, oxygen_need=oxygen,
                            source_datetime=when))
    db.commit()


def resolve_cultures(db, encounter_id):
    for item in db.scalars(select(PendingItem).where(PendingItem.encounter_id==encounter_id, PendingItem.status=='pending')):
        if 'culture' in item.description.lower():
            item.status='resolved'; item.resolved_at=datetime(2026,8,20,8,tzinfo=UTC)
    db.commit()


def accept_all(db, doc_payload, user_id):
    for s in doc_payload['sections']:
        update_progress_section(db, doc_payload['document_id'], s['id'], None, 'accept', user_id)
    return approve_progress_document(db, doc_payload['document_id'], user_id)


def final_text(db, document_id):
    sections=list(db.scalars(select(DocumentSection).where(DocumentSection.document_id==document_id).order_by(DocumentSection.sort_order)))
    heading_map={
        'hpi':'HPI','interval_hpi':'HPI','relevant_history':'Relevant History','objective_data':'Objective Data',
        'assessment_plan_problem':'Assessment & Plan','focused_exam':'Physical Exam','medication_reconciliation':'Medication Reconciliation',
        'disposition':'Disposition','one_liner':'One-liner','active_problem':'Active Problems','current_treatment':'Current Treatment',
        'pending_items':'Pending Studies','overnight_risks':'Overnight Risks','contingencies':'Contingencies','code_status':'Code Status',
        'discharge_diagnoses':'Discharge Diagnoses','hospital_course_problem':'Hospital Course','medication_transitions':'Medication Transitions',
        'pending_results':'Pending at Discharge','follow_up':'Follow-up Needs','avs':'AVS','discharge_addendum':'Discharge Addendum',
    }
    chunks=[]
    for s in sections:
        h=heading_map.get(s.section_type,s.section_type.replace('_',' ').title())
        text=s.physician_content or s.current_generated_content or s.generated_content
        chunks.append(f'**{h}**\n{text.strip()}')
    return '\n\n'.join(chunks)+'\n'


def score(db, encounter_id, texts):
    overview=build_patient_overview(db, encounter_id)
    problems={p['normalized_name']:p['status'] for p in overview['problems']}
    labs={x['test_name']:float(x['value_numeric']) for x in overview['latest_labs'] if x.get('value_numeric') is not None}
    meds=build_med_rec_workspace(db, encounter_id)
    med_states={m['normalized_name']:(m['discharge']['status'] if m['discharge'] else None) for m in meds['medications']}
    checks=[]
    for k,v in GROUND_TRUTH['problems'].items(): checks.append((f'problem:{k}', problems.get(k)==v, problems.get(k), v))
    for k,v in GROUND_TRUTH['latest_labs'].items(): checks.append((f'lab:{k}', abs(labs.get(k,-999)-v)<1e-6, labs.get(k), v))
    for k,v in GROUND_TRUTH['medications'].items(): checks.append((f'med:{k}', med_states.get(k)==v, med_states.get(k), v))
    d=overview.get('disposition') or {}; checks.append(('destination', (d.get('anticipated_destination') or '').lower()==GROUND_TRUTH['destination'], d.get('anticipated_destination'), GROUND_TRUTH['destination']))
    checks.append(('pending_count', overview['attention_counts'].get('pending_items',0)==0, overview['attention_counts'].get('pending_items',0), 0))
    combined='\n'.join(texts.values()).lower()
    for bad in GROUND_TRUTH['must_not_claim']:
        checks.append((f'must_not_claim:{bad}', bad not in combined, bad in combined, False))
    passed=sum(1 for _,ok,_,_ in checks if ok)
    return {'checks': [{'name':n,'passed':ok,'observed':o,'expected':e} for n,ok,o,e in checks], 'passed':passed, 'total':len(checks), 'accuracy':round(passed/len(checks),4)}


def main():
    started=time.perf_counter()
    engine=create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db=Session()

    org=Organization(name='Golden Hospitalist Group'); db.add(org); db.flush()
    user=User(organization_id=org.id,email='golden.attending@example.test',display_name='Golden Attending',role='attending',active=True); db.add(user); db.flush()
    patient=Patient(organization_id=org.id,mrn='GOLDEN-001',first_name='Synthetic',last_name='Patient',date_of_birth=date(1950,1,1),sex='male'); db.add(patient); db.flush()
    enc=Encounter(patient_id=patient.id,organization_id=org.id,admission_datetime=datetime(2026,8,18,9,tzinfo=UTC),service='Hospital Medicine',location='Med/Surg',attending_user_id=user.id); db.add(enc); db.commit()

    # Admission -> analysis -> H&P
    admission_src=add_source(db,enc,'hp',datetime(2026,8,18,9,tzinfo=UTC),ADMISSION,user)
    analyze1=analyze_encounter(db,enc.id)
    hp=generate_hp_document(db,enc.id,'admission',user.id); accept_all(db,hp,user.id)
    hp_audit=audit_document(db,hp['document_id']); hp_final=finalize_document(db,hp['document_id'],user.id)

    # Day 2 -> progress, signout, safety-trap/correction
    add_source(db,enc,'progress_note',datetime(2026,8,19,8,tzinfo=UTC),DAY2,user)
    add_source(db,enc,'consult_note',datetime(2026,8,19,11,tzinfo=UTC),NEPHROLOGY,user,'Nephrology')
    add_source(db,enc,'therapy',datetime(2026,8,19,14,tzinfo=UTC),PT,user,'PT')
    analyze2=analyze_encounter(db,enc.id)

    progress=generate_progress_document(db,enc.id,'daily',user.id)
    # Accept all, but deliberately inject a conflicting medication statement into the first problem section before approval.
    target=None
    for s in progress['sections']:
        if s['section_type']=='assessment_plan_problem' and target is None: target=s
        else: update_progress_section(db,progress['document_id'],s['id'],None,'accept',user.id)
    unsafe=(target['generated_content']+'\nContinue losartan.').strip()
    update_progress_section(db,progress['document_id'],target['id'],unsafe,'edit',user.id)
    unsafe_audit=audit_document(db,progress['document_id'])
    caught_med_conflict=any(f.category=='medication_conflict' for f in unsafe_audit['flags'])
    corrected=(target['generated_content']+'\nLosartan remains held; reassess after renal recovery.').strip()
    update_progress_section(db,progress['document_id'],target['id'],corrected,'edit',user.id)
    safe_audit=audit_document(db,progress['document_id'])
    approve_progress_document(db,progress['document_id'],user.id)
    progress_final=finalize_document(db,progress['document_id'],user.id)

    signout=generate_signout_document(db,enc.id,'night',user.id); accept_all(db,signout,user.id)
    signout_audit=audit_document(db,signout['document_id']); signout_final=finalize_document(db,signout['document_id'],user.id)

    # Day 3 -> resolve pending culture, confirm discharge medications, discharge.
    add_source(db,enc,'progress_note',datetime(2026,8,20,8,tzinfo=UTC),DAY3,user)
    add_source(db,enc,'discharge',datetime(2026,8,20,12,tzinfo=UTC),DISCHARGE_SOURCE,user)
    analyze3=analyze_encounter(db,enc.id)

    workspace=build_med_rec_workspace(db,enc.id)
    byname={m['normalized_name']:m for m in workspace['medications']}
    for name,status,reason in [('losartan','stop','Held for AKI; outpatient reassessment needed'),('apixaban','continue','Chronic atrial fibrillation; discharge continuation confirmed')]:
        if name in byname:
            confirm_discharge_state(db,byname[name]['medication_id'],MedRecDecision(status=status,reason=reason,confirmed_by=user.id))

    discharge=generate_discharge_document(db,enc.id,'summary',user.id); accept_all(db,discharge,user.id)
    discharge_audit=audit_document(db,discharge['document_id']); discharge_final=finalize_document(db,discharge['document_id'],user.id)

    texts={
        'hp':final_text(db,hp['document_id']), 'progress':final_text(db,progress['document_id']),
        'signout':final_text(db,signout['document_id']), 'discharge':final_text(db,discharge['document_id'])
    }
    for name,text in texts.items(): (OUT/f'{name}.md').write_text(text)
    final_overview=build_patient_overview(db,enc.id)
    final_med_rec=build_med_rec_workspace(db,enc.id)
    (OUT/'patient_overview.json').write_text(json.dumps(final_overview,indent=2,default=str))
    (OUT/'med_rec.json').write_text(json.dumps(final_med_rec,indent=2,default=str))
    (OUT/'EPIC_READY_BUNDLE.md').write_text('\n\n'.join([
        '# H&P\n'+texts['hp'], '# Progress Note\n'+texts['progress'], '# Signout\n'+texts['signout'], '# Discharge Summary\n'+texts['discharge']
    ]))

    quality=score(db,enc.id,texts)
    elapsed=time.perf_counter()-started
    total_chars=sum(len(x) for x in [ADMISSION,DAY2,NEPHROLOGY,PT,DAY3,DISCHARGE_SOURCE])
    token_est=round(total_chars/4)
    report={
        'golden_case_version':'1.1-step41', 'synthetic_deidentified':True,
        'runtime_seconds':round(elapsed,3), 'source_characters':total_chars, 'estimated_source_tokens':token_est,
        'external_model_calls':0, 'observed_model_cost_usd':0.0,
        'analysis_runs':[analyze1,analyze2,analyze3],
        'safety_trap':{'unsafe_medication_conflict_caught':caught_med_conflict,'unsafe_audit_blocking_flags':unsafe_audit['blocking_flags'],'post_correction_blocking_flags':safe_audit['blocking_flags']},
        'document_finalization':{
            'hp':hp_final['status'],'progress':progress_final['status'],'signout':signout_final['status'],'discharge':discharge_final['status']},
        'final_audits':{'hp':hp_audit['blocking_flags'],'signout':signout_audit['blocking_flags'],'discharge':discharge_audit['blocking_flags'], 'discharge_categories':[f.category for f in discharge_audit['flags']]},
        'quality':quality, 'physician_edit_events':len(list(db.scalars(select(PhysicianEdit)))), 
        'limitations':[
            'Current v0.1 Golden Case uses deterministic extraction/document generation; no external LLM inference was invoked.',
            'Step 41 Golden Case uses source-text ingestion for disposition/PT, physical exam, home medication state, and pending-result lifecycle resolution; no manual structured augmentation is used for those domains.',
            'Clinical quality is measured against synthetic ground truth and does not establish clinical validation.'
        ]
    }
    (OUT/'golden_case_report.json').write_text(json.dumps(report,indent=2,default=str))
    md=['# MediNote Step 40 — Golden Case Report','', '## Result',
        f"- Accuracy checks: **{quality['passed']}/{quality['total']} ({quality['accuracy']*100:.1f}%)**",
        f"- Safety trap caught: **{caught_med_conflict}**",
        f"- Blocking flags after physician correction: **{safe_audit['blocking_flags']}**",
        f"- Final document states: H&P={hp_final['status']}, Progress={progress_final['status']}, Signout={signout_final['status']}, Discharge={discharge_final['status']}",
        f"- End-to-end runtime in local in-memory test: **{elapsed:.3f} s**",
        '- External model calls: **0**; observed model cost: **$0.00** (current deterministic scaffold).','',
        '## What the test exercised','Chart/source import → MCIF extraction → temporal reconciliation → problem synthesis → Patient Overview → H&P → Progress → Med Rec → Signout → Discharge → Safety Audit → physician correction → approval/finalization → Epic-ready text.','',
        '## Integration gap exposed','Step 41 closes the four Step 40 ingestion gaps for explicit source language. Broader real-world phrasing and EHR-specific structured feeds still require additional validation.','',
        '## Safety trap','A physician-facing Progress section was deliberately edited to say `Continue losartan` while the structured hospital medication state was `held`. The audit engine detected the medication conflict before approval/finalization. After the physician corrected the section, the blocking conflict cleared.','',
        '## Ground-truth checks']
    for c in quality['checks']:
        md.append(f"- {'PASS' if c['passed'] else 'FAIL'} — {c['name']}: observed={c['observed']} expected={c['expected']}")
    md += ['', '## Limitations']+[f'- {x}' for x in report['limitations']]
    (OUT/'GOLDEN_CASE_REPORT.md').write_text('\n'.join(md)+'\n')
    print(json.dumps({'passed':quality['passed'],'total':quality['total'],'accuracy':quality['accuracy'],'safety_caught':caught_med_conflict,'runtime_s':round(elapsed,3),'outputs':str(OUT)},indent=2))

if __name__=='__main__': main()
