import json, os, subprocess, sys
from pathlib import Path


def test_golden_case_runner_end_to_end():
    backend=Path(__file__).resolve().parents[1]
    env=os.environ.copy(); env['PYTHONPATH']=str(backend); env['DATABASE_URL']='sqlite+pysqlite:///:memory:'; env['TEST_BYPASS_AUTH']='true'
    script=backend/'validation'/'golden'/'run_golden_case.py'
    p=subprocess.run([sys.executable,str(script)],cwd=backend,env=env,text=True,capture_output=True)
    assert p.returncode==0, p.stdout+'\n'+p.stderr
    report=json.loads((backend/'validation'/'golden'/'outputs'/'golden_case_report.json').read_text())
    assert report['quality']['accuracy'] >= 0.95
    assert report['safety_trap']['unsafe_medication_conflict_caught'] is True
    assert report['safety_trap']['post_correction_blocking_flags'] == 0
    assert all(v=='finalized' for v in report['document_finalization'].values())
    assert report['external_model_calls']==0

def test_explicit_problem_trajectory_updates_existing_status():
    from app.mcif.analyzer import analyze_source_text
    b=analyze_source_text('Pneumonia is improving.')
    p=next(x for x in b.problems if x.normalized_name=='pneumonia')
    assert p.status=='improving'


def test_continue_holding_phrase_is_not_active_continuation():
    # Regression is covered end-to-end by the golden case: discharge follow-up contains
    # 'continue holding losartan' and must still finalize without a medication-conflict blocker.
    backend=Path(__file__).resolve().parents[1]
    report=json.loads((backend/'validation'/'golden'/'outputs'/'golden_case_report.json').read_text())
    assert 'medication_conflict' not in report['final_audits']['discharge_categories']
