from datetime import date, datetime, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import (
    Organization, User, Patient, Encounter, SourceDocument,
    ClinicalFact, ClinicalProblem, Medication, MedicationState,
    ConsultantRecommendation, Contradiction, Procedure, DispositionState,
)
from app.services.analysis_service import analyze_encounter
from app.services.overview_service import build_patient_overview

UTC = timezone.utc


def make_db():
    engine = create_engine('sqlite+pysqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    org = Organization(name='Torture Test Group'); db.add(org); db.flush()
    user = User(organization_id=org.id, email='attending@example.test', display_name='Attending', role='attending', active=True); db.add(user); db.flush()
    patient = Patient(organization_id=org.id, mrn='TORTURE-001', first_name='Synthetic', last_name='Torture', date_of_birth=date(1950,1,1), sex='male'); db.add(patient); db.flush()
    enc = Encounter(patient_id=patient.id, organization_id=org.id, admission_datetime=datetime(2026,8,18,8,tzinfo=UTC), service='Hospital Medicine', attending_user_id=user.id); db.add(enc); db.commit()
    return db, enc, user


def source(db, enc, user, dtype, when, text, service=None):
    row = SourceDocument(encounter_id=enc.id, document_type=dtype, source_datetime=when, raw_text=text, author_service=service, source_system='step42', imported_by=user.id)
    db.add(row); db.commit(); return row


def test_step42_multiday_chart_torture_state_reconciliation():
    db, enc, user = make_db()
    # Admission with an erroneous problem-list diagnosis, duplicate home-med formatting, pending culture, and planned procedure.
    source(db, enc, user, 'hp', datetime(2026,8,18,8,tzinfo=UTC),
           'Pneumonia. Acute kidney injury. Sepsis. Cr 2.5. Currently on 4 L NC. '
           'Home medications include losartan 50 mg daily, losartan, apixaban. Blood cultures pending. Biopsy planned.')
    analyze_encounter(db, enc.id)

    # Explicitly rule out sepsis and cancel the procedure.
    source(db, enc, user, 'progress_note', datetime(2026,8,18,12,tzinfo=UTC),
           'Sepsis ruled out. Pneumonia improving. Acute kidney injury improving. Cr 2.0. Biopsy cancelled.')
    analyze_encounter(db, enc.id)

    # Conflicting consultant recommendations at the same period.
    source(db, enc, user, 'consult_note', datetime(2026,8,19,9,tzinfo=UTC), 'Cardiology recommends continue furosemide.', 'Cardiology')
    source(db, enc, user, 'consult_note', datetime(2026,8,19,9,tzinfo=UTC), 'Nephrology recommends hold furosemide.', 'Nephrology')

    # Same-timestamp stale copied-forward progress vs nursing current state. Nursing should win under governance hierarchy.
    t = datetime(2026,8,19,10,tzinfo=UTC)
    source(db, enc, user, 'progress_note', t, 'Copied forward: currently on 4 L NC. Sepsis. Biopsy planned.')
    source(db, enc, user, 'nursing_note', t, 'Patient is on room air.')

    # Destination evolves; latest documented plan must win.
    source(db, enc, user, 'therapy', datetime(2026,8,19,13,tzinfo=UTC), 'PT recommends SNF. Patient ambulates 40 feet with rolling walker and assistance.')
    source(db, enc, user, 'therapy', datetime(2026,8,20,9,tzinfo=UTC), 'PT recommends home with home health. Patient ambulates 150 feet with rolling walker and supervision.')

    # Later objective result amends an earlier value; final culture resolves pending.
    source(db, enc, user, 'lab', datetime(2026,8,20,6,tzinfo=UTC), 'Cr 1.4.')
    source(db, enc, user, 'lab', datetime(2026,8,20,7,tzinfo=UTC), 'Amended laboratory result: Cr 1.2.')
    source(db, enc, user, 'microbiology', datetime(2026,8,20,8,tzinfo=UTC), 'Blood cultures amended final: no growth.')

    # Late-arriving documentation has an old clinical timestamp and must not become current.
    source(db, enc, user, 'progress_note', datetime(2026,8,18,9,tzinfo=UTC), 'Late-entered note: Cr 2.4. Currently on 3 L NC.')
    analyze_encounter(db, enc.id)

    # Current oxygen should be room air (nursing outranks clinician narrative at equal timestamp; old late note cannot override time).
    current_o2 = list(db.scalars(select(ClinicalFact).where(ClinicalFact.encounter_id==enc.id, ClinicalFact.fact_type=='oxygen_support', ClinicalFact.is_current.is_(True))))
    assert len(current_o2) == 1
    assert current_o2[0].value_text == 'room_air'

    # Ruled-out sepsis must not be resurrected by copied-forward bare mention.
    sepsis = db.scalar(select(ClinicalProblem).where(ClinicalProblem.encounter_id==enc.id, ClinicalProblem.normalized_name=='sepsis'))
    assert sepsis is not None and sepsis.status == 'resolved'

    # Duplicate home entries normalize to a single medication identity.
    losartans = list(db.scalars(select(Medication).where(Medication.encounter_id==enc.id, Medication.normalized_name=='losartan')))
    assert len(losartans) == 1
    home_states = list(db.scalars(select(MedicationState).where(MedicationState.medication_id==losartans[0].id, MedicationState.domain=='home')))
    assert len(home_states) == 1

    # Conflicting consultants are preserved and flagged, but their recommendations do not become implemented medication states.
    furosemide = db.scalar(select(Medication).where(Medication.encounter_id==enc.id, Medication.normalized_name=='furosemide'))
    assert furosemide is None
    consults = list(db.scalars(select(ConsultantRecommendation).where(ConsultantRecommendation.encounter_id==enc.id)))
    assert {c.conflict_status for c in consults} == {'conflict'}
    conflicts = list(db.scalars(select(Contradiction).where(Contradiction.encounter_id==enc.id, Contradiction.category=='consultant_recommendation_conflict')))
    assert len(conflicts) == 1

    # Canceled procedure remains canceled despite later stale copied-forward 'planned'.
    proc = db.scalar(select(Procedure).where(Procedure.encounter_id==enc.id, Procedure.procedure_name=='biopsy'))
    assert proc is not None and proc.status == 'cancelled'

    overview = build_patient_overview(db, enc.id)
    labs = {x['test_name']: float(x['value_numeric']) for x in overview['latest_labs'] if x['value_numeric'] is not None}
    assert labs['creatinine'] == 1.2
    assert overview['attention_counts']['pending_items'] == 0
    assert overview['disposition']['anticipated_destination'].lower() == 'home with home health'


def test_step42_procedure_and_ruled_out_parsing_is_conservative():
    from app.mcif import analyze_source_text
    bundle = analyze_source_text('Sepsis ruled out. Biopsy cancelled. Blood cultures amended final: no growth.')
    assert any(p.normalized_name=='sepsis' and p.status=='resolved' for p in bundle.problems)
    assert any(p.procedure_name.lower()=='biopsy' and p.status=='cancelled' for p in bundle.procedures)
    assert any(r.description.lower()=='blood cultures' and r.result_text.lower()=='no growth' for r in bundle.resolved_items)
