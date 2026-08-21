from difflib import SequenceMatcher
from collections import defaultdict
from datetime import datetime, timezone

MODULES = {'overview','hp','progress','discharge','med_rec','signout'}


def _set(items): return {str(x).strip().lower() for x in (items or []) if str(x).strip()}
def _pr(expected, observed):
    e, o = _set(expected), _set(observed)
    tp = len(e & o)
    return ((tp / len(o)) if o else (1.0 if not e else 0.0), (tp / len(e)) if e else 1.0)


def evaluate(gt: dict, obs: dict, generated_text=None, physician_final_text=None):
    fp, fr = _pr(gt.get('facts'), obs.get('facts'))
    expected_meds = _set(gt.get('medication_states'))
    observed_meds = _set(obs.get('medication_states'))
    med_acc = len(expected_meds & observed_meds) / len(expected_meds) if expected_meds else 1.0
    expected_cert = {str(k).lower(): str(v).lower() for k,v in gt.get('diagnostic_certainty', {}).items()}
    observed_cert = {str(k).lower(): str(v).lower() for k,v in obs.get('diagnostic_certainty', {}).items()}
    cert_acc = sum(observed_cert.get(k) == v for k,v in expected_cert.items()) / len(expected_cert) if expected_cert else 1.0
    prohibited = _set(gt.get('must_not_claim'))
    claims = _set(obs.get('claims'))
    unsupported = len(prohibited & claims)
    consequential = unsupported + int(obs.get('consequential_errors', 0) or 0)
    expected_flags = _set(gt.get('must_flag'))
    observed_flags = _set(obs.get('flags'))
    flag_recall = len(expected_flags & observed_flags) / len(expected_flags) if expected_flags else 1.0
    edit_ratio = None
    if generated_text is not None and physician_final_text is not None:
        edit_ratio = round(1.0 - SequenceMatcher(None, generated_text, physician_final_text).ratio(), 4)
    passed = consequential == 0 and fp >= .98 and med_acc >= .99 and cert_acc >= .99 and flag_recall >= .95
    return {
        'fact_precision': round(fp,4), 'fact_recall': round(fr,4),
        'medication_accuracy': round(med_acc,4), 'certainty_accuracy': round(cert_acc,4),
        'expected_flag_recall': round(flag_recall,4),
        'unsupported_claims': unsupported,
        'unsupported_claim_rate': round(unsupported / max(len(claims),1),4),
        'consequential_errors': consequential,
        'physician_edit_ratio': edit_ratio,
        'passed': passed,
    }


def build_dashboard(cases, runs):
    def mean(key, subset=None):
        rows = subset if subset is not None else runs
        return round(sum(float(r.metrics.get(key,0)) for r in rows)/len(rows),4) if rows else 0.0
    edits=[float(r.physician_edit_ratio) for r in runs if r.physician_edit_ratio is not None]
    errors=sum(r.consequential_error_count for r in runs)
    unique_cases=len({r.validation_case_id for r in runs})
    adjudicated=sum(1 for r in runs if r.adjudication_status in {'accepted','rejected','resolved'})
    reasons=[]
    if unique_cases < len(cases): reasons.append('Not every validation case has at least one completed run.')
    if len(cases) < 50: reasons.append('Simulation library contains fewer than 50 cases.')
    if runs and mean('fact_precision') < .98: reasons.append('Fact precision is below the 98% pilot target.')
    if runs and mean('medication_accuracy') < .99: reasons.append('Medication-state accuracy is below the 99% pilot target.')
    if runs and mean('certainty_accuracy') < .99: reasons.append('Diagnostic-certainty accuracy is below the 99% pilot target.')
    if errors: reasons.append('Consequential validation errors remain.')
    modules=[]
    for module in sorted(MODULES):
        rows=[r for r in runs if r.module == module]
        if not rows: continue
        modules.append({
            'module': module, 'runs': len(rows),
            'pass_rate': round(sum(1 for r in rows if r.passed)/len(rows),4),
            'consequential_errors': sum(r.consequential_error_count for r in rows),
            'mean_fact_precision': mean('fact_precision', rows),
            'mean_fact_recall': mean('fact_recall', rows),
            'mean_physician_edit_ratio': round(sum(float(r.physician_edit_ratio) for r in rows if r.physician_edit_ratio is not None)/max(sum(1 for r in rows if r.physician_edit_ratio is not None),1),4),
        })
    gate='candidate' if cases and unique_cases>=len(cases) and not reasons else 'not_ready'
    return {
        'cases': len(cases), 'runs': len(runs), 'unique_cases_run': unique_cases,
        'adjudicated_runs': adjudicated,
        'mean_fact_precision': mean('fact_precision'), 'mean_fact_recall': mean('fact_recall'),
        'mean_medication_accuracy': mean('medication_accuracy'), 'mean_certainty_accuracy': mean('certainty_accuracy'),
        'unsupported_claim_rate': mean('unsupported_claim_rate'),
        'consequential_errors_per_100_cases': round(errors/max(len(runs),1)*100,2),
        'mean_physician_edit_ratio': round(sum(edits)/len(edits),4) if edits else 0.0,
        'module_summaries': modules, 'pilot_gate': gate, 'gate_reasons': reasons,
    }


def build_report(cases, runs, dashboard):
    case_by_id={c.id:c for c in cases}
    failures=[]
    by_category=defaultdict(lambda:{'cases':set(),'runs':0,'errors':0,'passes':0})
    for r in runs:
        c=case_by_id.get(r.validation_case_id)
        if c:
            s=by_category[c.category]; s['cases'].add(c.id); s['runs']+=1; s['errors']+=r.consequential_error_count; s['passes']+=int(r.passed)
        if r.consequential_error_count or not r.passed:
            failures.append({'case': c.slug if c else str(r.validation_case_id), 'module': r.module, 'errors': r.consequential_error_count, 'metrics': r.metrics})
    cats=[]
    for category,s in sorted(by_category.items()):
        cats.append({'category':category,'cases':len(s['cases']),'runs':s['runs'],'pass_rate':round(s['passes']/max(s['runs'],1),4),'consequential_errors':s['errors']})
    lines=[
        '# MediNote Controlled Physician Simulation Study', '',
        '**Study version:** 1.0',
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}", '',
        '## Executive summary',
        f"- Validation cases: {dashboard['cases']}",
        f"- Completed runs: {dashboard['runs']}",
        f"- Unique cases tested: {dashboard['unique_cases_run']}",
        f"- Consequential errors per 100 runs: {dashboard['consequential_errors_per_100_cases']}",
        f"- Mean fact precision: {dashboard['mean_fact_precision']:.4f}",
        f"- Mean medication-state accuracy: {dashboard['mean_medication_accuracy']:.4f}",
        f"- Pilot engineering gate: {dashboard['pilot_gate'].upper()}", '',
        '## Interpretation',
        'This report is an internal engineering/clinical simulation artifact. It does not establish clinical validation, regulatory clearance, HIPAA compliance, or fitness for autonomous patient care.', '',
        '## Gate reasons',
    ]
    lines += [f'- {x}' for x in dashboard['gate_reasons']] or ['- No predefined engineering gate failures.']
    lines += ['', '## Module summary']
    for m in dashboard['module_summaries']:
        lines.append(f"- {m['module']}: {m['runs']} runs, pass rate {m['pass_rate']:.1%}, consequential errors {m['consequential_errors']}")
    lines += ['', '## High-risk failures']
    if failures:
        for f in failures[:50]: lines.append(f"- {f['case']} / {f['module']}: {f['errors']} consequential error(s)")
    else: lines.append('- None observed in recorded runs.')
    return {'study_name':'MediNote Controlled Physician Simulation Study','study_version':'1.0','generated_at':datetime.now(timezone.utc).isoformat(),'dashboard':dashboard,'high_risk_failures':failures,'category_summary':cats,'report_markdown':'\n'.join(lines)}
