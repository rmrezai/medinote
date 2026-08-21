from app.services.validation_service import evaluate

def test_validation_metric_perfect():
    gt={'facts':['a','b'],'medication_states':['losartan:hospital:held'],'diagnostic_certainty':{'aki':'confirmed'},'must_not_claim':['sepsis']}
    obs={'facts':['a','b'],'medication_states':['losartan:hospital:held'],'diagnostic_certainty':{'aki':'confirmed'},'claims':['aki improving']}
    m=evaluate(gt,obs,'draft','draft')
    assert m['fact_precision']==1 and m['fact_recall']==1
    assert m['medication_accuracy']==1 and m['certainty_accuracy']==1
    assert m['consequential_errors']==0 and m['physician_edit_ratio']==0

def test_validation_catches_prohibited_claim():
    m=evaluate({'must_not_claim':['sepsis']},{'claims':['sepsis']})
    assert m['unsupported_claims']==1
    assert m['consequential_errors']==1

def test_physician_edit_ratio():
    m=evaluate({}, {}, 'Patient stable.', 'Patient improving.')
    assert m['physician_edit_ratio'] > 0

def test_validation_routes_registered():
    from app.main import app
    paths={r.path for r in app.routes}
    assert '/api/v1/validation/cases' in paths
    assert '/api/v1/validation/dashboard' in paths
