import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.services.validation_service import build_dashboard, build_report, evaluate


def test_simulation_library_has_60_cases():
    path = Path(__file__).resolve().parents[1] / 'validation' / 'cases' / 'core_cases.json'
    data = json.loads(path.read_text())
    assert len(data) == 60
    assert all(c.get('module_targets') for c in data)
    assert all('ground_truth' in c for c in data)


def test_expected_safety_flag_recall_is_scored():
    gt={'must_flag':['consultant conflict'],'must_not_claim':[]}
    good=evaluate(gt, {'flags':['consultant conflict']})
    bad=evaluate(gt, {'flags':[]})
    assert good['expected_flag_recall'] == 1
    assert bad['expected_flag_recall'] == 0
    assert good['passed'] is True
    assert bad['passed'] is False


def test_dashboard_requires_50_cases_and_zero_consequential_errors():
    cases=[SimpleNamespace(id=uuid4()) for _ in range(60)]
    runs=[]
    for c in cases:
        runs.append(SimpleNamespace(
            validation_case_id=c.id, module='progress', physician_edit_ratio=0.05,
            consequential_error_count=0, adjudication_status='accepted', passed=True,
            metrics={'fact_precision':1,'fact_recall':1,'medication_accuracy':1,'certainty_accuracy':1,'unsupported_claim_rate':0}
        ))
    dash=build_dashboard(cases,runs)
    assert dash['pilot_gate']=='candidate'
    assert dash['unique_cases_run']==60
    assert dash['module_summaries'][0]['pass_rate']==1


def test_report_contains_explicit_non_clearance_language():
    cid=uuid4()
    cases=[SimpleNamespace(id=cid, slug='x', category='Safety')]
    runs=[SimpleNamespace(validation_case_id=cid,module='hp',consequential_error_count=0,passed=True,
        physician_edit_ratio=0.0,metrics={'fact_precision':1,'fact_recall':1,'medication_accuracy':1,'certainty_accuracy':1,'unsupported_claim_rate':0},adjudication_status='accepted')]
    dash=build_dashboard(cases,runs)
    report=build_report(cases,runs,dash)
    assert 'does not establish clinical validation' in report['report_markdown']
    assert report['study_name'].startswith('MediNote')


def test_step29_routes_registered():
    from app.main import app
    paths={r.path for r in app.routes}
    assert '/api/v1/validation/runs/{run_id}/adjudicate' in paths
    assert '/api/v1/validation/report' in paths
