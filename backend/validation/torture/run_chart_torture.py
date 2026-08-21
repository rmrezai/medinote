from __future__ import annotations
import json, time
from datetime import date, datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import Organization, User, Patient, Encounter, SourceDocument, ClinicalFact, ClinicalProblem, Medication, MedicationState, ConsultantRecommendation, Contradiction, Procedure
from app.services.analysis_service import analyze_encounter
from app.services.overview_service import build_patient_overview
from app.services.progress_service import generate_progress_document
from app.services.signout_service import generate_signout_document
from app.services.audit_service import audit_document

UTC=timezone.utc
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs'; OUT.mkdir(exist_ok=True)

SOURCES=[
('hp','Hospital Medicine',datetime(2026,8,18,8,tzinfo=UTC),'Pneumonia. Acute kidney injury. Sepsis. Cr 2.5. Currently on 4 L NC. Home medications include losartan 50 mg daily, losartan, apixaban. Blood cultures pending. Biopsy planned.'),
('progress_note','Hospital Medicine',datetime(2026,8,18,12,tzinfo=UTC),'Sepsis ruled out. Pneumonia improving. Acute kidney injury improving. Cr 2.0. Biopsy cancelled.'),
('consult_note','Cardiology',datetime(2026,8,19,9,tzinfo=UTC),'Cardiology recommends continue furosemide.'),
('consult_note','Nephrology',datetime(2026,8,19,9,tzinfo=UTC),'Nephrology recommends hold furosemide.'),
('progress_note','Hospital Medicine',datetime(2026,8,19,10,tzinfo=UTC),'Copied forward: currently on 4 L NC. Sepsis. Biopsy planned.'),
('nursing_note','Nursing',datetime(2026,8,19,10,tzinfo=UTC),'Patient is on room air.'),
('therapy','PT',datetime(2026,8,19,13,tzinfo=UTC),'PT recommends SNF. Patient ambulates 40 feet with rolling walker and assistance.'),
('therapy','PT',datetime(2026,8,20,9,tzinfo=UTC),'PT recommends home with home health. Patient ambulates 150 feet with rolling walker and supervision.'),
('lab','Lab',datetime(2026,8,20,6,tzinfo=UTC),'Cr 1.4.'),
('lab','Lab',datetime(2026,8,20,7,tzinfo=UTC),'Amended laboratory result: Cr 1.2.'),
('microbiology','Microbiology',datetime(2026,8,20,8,tzinfo=UTC),'Blood cultures amended final: no growth.'),
# Imported last, but clinically old. The old source timestamp must keep it from becoming current.
('progress_note','Hospital Medicine',datetime(2026,8,18,9,tzinfo=UTC),'Late-entered note: Cr 2.4. Currently on 3 L NC.'),
]

def add_source(db,enc,user,dtype,service,when,text):
    row=SourceDocument(encounter_id=enc.id,document_type=dtype,author_service=service,source_datetime=when,source_system='step42_torture',raw_text=text,imported_by=user.id)
    db.add(row); db.commit(); return row

def main():
    started=time.perf_counter()
    engine=create_engine('sqlite+pysqlite:///:memory:',future=True)
    Base.metadata.create_all(engine)
    Session=sessionmaker(bind=engine)
    db=Session()
    org=Organization(name='Step42 Torture Group'); db.add(org); db.flush()
    user=User(organization_id=org.id,email='step42@example.test',display_name='Step42 Attending',role='attending',active=True); db.add(user); db.flush()
    patient=Patient(organization_id=org.id,mrn='TORTURE-001',first_name='Synthetic',last_name='Torture',date_of_birth=date(1950,1,1),sex='male'); db.add(patient); db.flush()
    enc=Encounter(patient_id=patient.id,organization_id=org.id,admission_datetime=datetime(2026,8,18,8,tzinfo=UTC),service='Hospital Medicine',attending_user_id=user.id); db.add(enc); db.commit()
    reports=[]
    for dtype,service,when,text in SOURCES:
        add_source(db,enc,user,dtype,service,when,text)
        reports.append(analyze_encounter(db,enc.id))

    overview=build_patient_overview(db,enc.id)
    problems={p['normalized_name']:p['status'] for p in overview['problems']}
    labs={x['test_name']:float(x['value_numeric']) for x in overview['latest_labs'] if x.get('value_numeric') is not None}
    current_o2=list(db.scalars(select(ClinicalFact).where(ClinicalFact.encounter_id==enc.id,ClinicalFact.fact_type=='oxygen_support',ClinicalFact.is_current.is_(True))))
    losartan=list(db.scalars(select(Medication).where(Medication.encounter_id==enc.id,Medication.normalized_name=='losartan')))
    consults=list(db.scalars(select(ConsultantRecommendation).where(ConsultantRecommendation.encounter_id==enc.id)))
    proc=db.scalar(select(Procedure).where(Procedure.encounter_id==enc.id,Procedure.procedure_name=='biopsy'))
    contradictions=list(db.scalars(select(Contradiction).where(Contradiction.encounter_id==enc.id,Contradiction.status=='unresolved')))

    checks=[
        ('current oxygen is room air',len(current_o2)==1 and current_o2[0].value_text=='room_air'),
        ('sepsis remains ruled out','sepsis' not in problems),
        ('duplicate losartan normalized',len(losartan)==1),
        ('consultant conflict preserved',sum(1 for c in consults if c.conflict_status=='conflict')==2),
        ('consultant contradiction created',any(c.category=='consultant_recommendation_conflict' for c in contradictions)),
        ('biopsy remains cancelled',proc is not None and proc.status=='cancelled'),
        ('amended creatinine is current',labs.get('creatinine')==1.2),
        ('blood cultures no longer pending',overview['attention_counts'].get('pending_items')==0),
        ('latest disposition wins',(overview.get('disposition') or {}).get('anticipated_destination','').lower()=='home with home health'),
        ('late old documentation does not override current state',labs.get('creatinine')==1.2 and current_o2[0].value_text=='room_air'),
    ]

    progress=generate_progress_document(db,enc.id,'daily',user.id)
    progress_audit=audit_document(db,progress['document_id'])
    signout=generate_signout_document(db,enc.id,'night',user.id)
    signout_audit=audit_document(db,signout['document_id'])

    report={
        'step':'42','test':'multi_day_chart_ingestion_torture','synthetic_deidentified':True,
        'source_documents':len(SOURCES),'analysis_runs':len(reports),
        'checks':[{'name':n,'passed':ok} for n,ok in checks],
        'passed':sum(ok for _,ok in checks),'total':len(checks),
        'accuracy':sum(ok for _,ok in checks)/len(checks),
        'unresolved_contradictions':[{'category':c.category,'severity':c.severity,'description':c.description} for c in contradictions],
        'progress_audit':{'status':progress_audit['status'],'blocking_flags':progress_audit['blocking_flags'],'categories':[f.category for f in progress_audit['flags']]},
        'signout_audit':{'status':signout_audit['status'],'blocking_flags':signout_audit['blocking_flags'],'categories':[f.category for f in signout_audit['flags']]},
        'expected_review_behavior':'Consultant disagreement remains unresolved and should require physician review rather than silent auto-resolution.',
        'runtime_seconds':round(time.perf_counter()-started,3),
        'limitations':['Deterministic synthetic torture test; does not establish clinical validation.','Consultant conflict detection currently targets explicit opposing action/medication language.','Ruled-out diagnosis tombstone is deliberately conservative and requires future explicit recurrence logic.'],
    }
    (OUT/'chart_torture_report.json').write_text(json.dumps(report,indent=2,default=str))
    (OUT/'patient_overview.json').write_text(json.dumps(overview,indent=2,default=str))
    lines=['# MediNote Step 42 — Multi-Day Chart Ingestion Torture Test','',f"**Result:** {report['passed']}/{report['total']} checks passed ({report['accuracy']*100:.1f}%).",'', '## Assertions']
    lines += [f"- {'PASS' if x['passed'] else 'FAIL'} — {x['name']}" for x in report['checks']]
    lines += ['', '## Deliberately unresolved conflicts']
    lines += [f"- [{x['severity']}] {x['category']}: {x['description']}" for x in report['unresolved_contradictions']] or ['- None']
    lines += ['', '## Document safety behavior',f"- Progress audit: {report['progress_audit']['status']} ({report['progress_audit']['blocking_flags']} blocking flags)",f"- Signout audit: {report['signout_audit']['status']} ({report['signout_audit']['blocking_flags']} blocking flags)",'', 'The unresolved consultant disagreement is expected to remain visible for physician review rather than being silently resolved.']
    (OUT/'CHART_TORTURE_REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'passed':report['passed'],'total':report['total'],'progress_audit':report['progress_audit'],'signout_audit':report['signout_audit']},indent=2))
    if report['passed'] != report['total']:
        raise SystemExit(1)

if __name__=='__main__': main()
