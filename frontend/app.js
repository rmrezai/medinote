const DEFAULT_API_BASE = (location.hostname === 'localhost' || location.hostname === '127.0.0.1') ? 'http://localhost:8000/api/v1' : `${location.origin}/api/v1`;
const API_BASE = localStorage.getItem('medinote_api_base') || DEFAULT_API_BASE;

const state = {
  organizations: [], encounters: [], activeEncounterId: null, overview: null,
  module: 'overview', activeDocument: null, safetyFlags: [], medRec: null, identity: null,
  loading: false, modal: null,
  token: localStorage.getItem('medinote_token'), user: null, authMode: 'login',
};

const app = document.getElementById('app');
const toastRoot = document.getElementById('toast-root');

const esc = (v='') => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const fmtDate = v => v ? new Date(v).toLocaleString([], {month:'short', day:'numeric', hour:'numeric', minute:'2-digit'}) : '—';
const titleize = s => String(s || '').replaceAll('_',' ').replace(/\b\w/g, c => c.toUpperCase());

function toast(message, error=false) {
  toastRoot.innerHTML = `<div class="toast ${error?'error':''}">${esc(message)}</div>`;
  setTimeout(() => { toastRoot.innerHTML=''; }, 3200);
}

async function api(path, options={}) {
  const headers={'Content-Type':'application/json', ...(state.token ? {'Authorization': `Bearer ${state.token}`} : {}), ...(options.headers||{})};
  if(options.idempotencyKey) headers['Idempotency-Key']=options.idempotencyKey;
  let res;
  try { res = await fetch(`${API_BASE}${path}`, {...options, headers}); }
  catch (networkError) { const e=new Error(`Network unavailable. Your local draft is preserved. ${networkError.message||''}`.trim()); e.network=true; throw e; }
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const d = await res.json(); const detail=d.detail; msg = typeof detail==='string' ? detail : (detail?.message ? `${detail.message}${detail.current_version?` Current version: ${detail.current_version}.`:''}` : JSON.stringify(detail||d)); } catch {}
    const e=new Error(msg); e.status=res.status; throw e;
  }
  return res.status === 204 ? null : res.json();
}

function recoveryKey(scope){ const k=`medinote_op_${scope}`; let v=localStorage.getItem(k); if(!v){v=crypto.randomUUID();localStorage.setItem(k,v);} return v; }
function clearRecoveryKey(scope){ localStorage.removeItem(`medinote_op_${scope}`); }
function draftKey(id){return `medinote_draft_${state.activeDocument?.document_id||'none'}_${id}`;}

async function bootstrap() {
  state.loading = true; render();
  try {
    if (!state.token) { state.loading=false; render(); return; }
    state.user = await api('/auth/me');
    state.organizations = await api('/organizations');
    await loadEncounters();
  } catch (e) {
    localStorage.removeItem('medinote_token'); state.token=null; state.user=null;
    toast(`Session unavailable: ${e.message}`, true);
  }
  state.loading = false; render();
}

async function loadEncounters() {
  const orgId = state.organizations[0]?.id;
  state.encounters = await api(`/encounters${orgId ? `?organization_id=${orgId}` : ''}`);
}

async function selectEncounter(id) {
  state.activeEncounterId = id; state.module='overview'; state.activeDocument=null; state.safetyFlags=[]; state.medRec=null; state.identity=null;
  await refreshIdentity(); await refreshOverview(); render();
}


async function refreshIdentity() {
  if (!state.activeEncounterId) return;
  try { state.identity = await api(`/encounters/${state.activeEncounterId}/identity`); }
  catch (e) { state.identity = null; }
}

async function refreshOverview() {
  if (!state.activeEncounterId) return;
  try { state.overview = await api(`/encounters/${state.activeEncounterId}/overview`); }
  catch (e) { state.overview = null; toast(e.message, true); }
}

function shell(content) {
  const active = state.overview;
  return `<div class="app-shell">
    <aside class="sidebar">
      <div class="brand"><div class="brand-mark">M</div><div>MediNote</div></div>
      <div class="nav-label">Workspace</div>
      <button class="nav-button ${!state.activeEncounterId?'active':''}" data-action="dashboard">▦ Patient Dashboard</button>
      <button class="nav-button" data-action="new-patient">＋ New Patient</button>
      ${state.activeEncounterId ? `<div class="nav-label">Clinical</div>
        <button class="nav-button ${state.module==='overview'?'active':''}" data-module="overview">◫ Patient Overview</button>
        <button class="nav-button ${state.module==='hp'?'active':''}" data-module="hp">H&P</button>
        <button class="nav-button ${state.module==='progress'?'active':''}" data-module="progress">Progress Note</button>
        <button class="nav-button ${state.module==='discharge'?'active':''}" data-module="discharge">Discharge</button>
        <button class="nav-button ${state.module==='med-rec'?'active':''}" data-module="med-rec">Med Rec</button>
        <button class="nav-button ${state.module==='signout'?'active':''}" data-module="signout">Signout</button>
        <button class="nav-button ${state.module==='source'?'active':''}" data-module="source">Import Chart</button>` : ''}
      <div class="sidebar-footer"><strong>${esc(state.user?.display_name || state.user?.email || 'Signed in')}</strong><br>${esc(titleize(state.user?.role || ''))}<br><button class="btn small" style="margin-top:8px" data-action="logout">Sign out</button></div>
    </aside>
    <main class="main">
      <header class="topbar">
        <div><h1>${active ? esc(active.patient_display_name || 'Patient Encounter') : 'Patient Dashboard'}</h1><div class="topbar-sub">${active ? `${esc(active.service || 'Hospital Medicine')} · ${esc(active.location || 'Location not set')} · MRN ${esc(active.mrn || '—')}` : 'Small hospitalist group pilot workspace'}</div></div>
        <div class="actions">${state.activeEncounterId ? `<button class="btn" data-action="refresh">Refresh</button><button class="btn primary" data-module="source">Import Chart</button>` : `<button class="btn primary" data-action="new-patient">New Patient</button>`}</div>
      </header>
      <section class="content">${content}</section>
    </main>
  </div>${renderModal()}`;
}

function render() {
  if (!state.token) { app.innerHTML = authScreen(); bindAuth(); return; }
  if (state.loading && !state.encounters.length) { app.innerHTML = shell('<div class="empty"><span class="loader"></span><p>Loading MediNote…</p></div>'); bind(); return; }
  let content = !state.activeEncounterId ? dashboard() : patientWorkspace();
  app.innerHTML = shell(content); bind();
}

function dashboard() {
  const activeCount = state.encounters.filter(e => e.status==='active').length;
  return `<div class="grid three">
    <div class="card kpi"><div class="label">Active patients</div><div class="value">${activeCount}</div></div>
    <div class="card kpi"><div class="label">Recent encounters</div><div class="value">${state.encounters.length}</div></div>
    <div class="card kpi"><div class="label">Pilot organization</div><div class="value" style="font-size:18px">${esc(state.organizations[0]?.name || '—')}</div></div>
  </div>
  <div class="card" style="margin-top:18px"><div class="card-head"><h2>Patients</h2><button class="btn small" data-action="new-patient">＋ New</button></div>
  <div class="card-body">${state.encounters.length ? `<div class="patient-list">${state.encounters.map(e => `<button class="patient-row" data-encounter="${e.id}"><div><div class="patient-name">${esc(e.patient_display_name || 'Unnamed patient')}</div><div class="muted small">MRN ${esc(e.mrn || '—')}</div></div><div><strong>${esc(e.location || '—')}</strong><div class="muted small">${esc(e.service || '—')}</div></div><div><span class="status-pill ${e.status==='active'?'good':''}">${esc(e.status)}</span></div><div class="muted small">${fmtDate(e.admission_datetime)}</div></button>`).join('')}</div>` : '<div class="empty">No encounters yet. Create the first patient.</div>'}</div></div>`;
}

function patientWorkspace() {
  if (!state.overview && state.module !== 'source') return '<div class="empty">Patient overview unavailable. Import chart data and analyze the encounter.</div>';
  const tabs = `<div class="module-tabs">${[['overview','Overview'],['hp','H&P'],['progress','Progress Note'],['discharge','Discharge'],['med-rec','Med Rec'],['signout','Signout']].map(([k,l])=>`<button class="module-tab ${state.module===k?'active':''}" data-module="${k}">${l}</button>`).join('')}</div>`;
  if (state.module === 'source') return tabs + sourceImport();
  if (state.module === 'overview') return tabs + overview();
  if (state.module === 'med-rec') return tabs + medRecView();
  return tabs + documentView();
}

function identityPanel() {
  const i=state.identity; if(!i)return '';
  const bad=i.hard_stop;
  const sources=(i.sources||[]).filter(s=>['mismatch','ambiguous'].includes(s.identity_status));
  return `<div class="summary-box" style="margin-bottom:14px;${bad?'border-color:#b42318':''}"><strong>Patient Identity: ${esc(titleize(i.identity_status))}</strong>${bad?'<div class="status-pill bad" style="margin-left:8px">HARD STOP</div>':''}<div class="muted small" style="margin-top:6px">MRN ${esc(i.patient?.mrn||'—')} · DOB ${esc(i.patient?.date_of_birth||'—')}</div>${sources.map(s=>`<div class="intel-item ${s.identity_status==='mismatch'?'critical':'moderate'}" style="margin-top:8px"><div class="intel-title">${titleize(s.identity_status)} source · ${titleize(s.document_type)}</div><div class="small">${esc(s.identity_reason||'Identity review required.')}</div><div style="margin-top:7px">${s.identity_status==='ambiguous'?`<button class="btn small" data-verify-source="${s.source_id}">Verify source</button>`:''}<button class="btn small" data-remove-source="${s.source_id}">Remove source</button></div></div>`).join('')}</div>`;
}

function overview() {
  const o=state.overview;
  return `${identityPanel()}<div class="patient-header"><div><h2>${esc(o.patient_display_name || 'Patient')}</h2><div class="muted">Admitted ${fmtDate(o.admission_datetime)} · ${esc(o.encounter_status)}</div></div><div class="actions"><button class="btn" data-action="analyze">Analyze chart</button></div></div>
  <div class="summary-box"><strong>Current Clinical Picture</strong><div style="margin-top:6px">${esc(o.current_clinical_picture)}</div></div>
  <div class="grid two" style="margin-top:18px"><div class="grid">
    <div class="card"><div class="card-head"><h3>Active Problems</h3><span class="status-pill">${o.problems.length}</span></div><div class="card-body">${o.problems.length?o.problems.map(problemHtml).join(''):'<div class="muted">No active problems extracted.</div>'}</div></div>
    <div class="card"><div class="card-head"><h3>Latest Labs</h3></div><div class="card-body">${o.latest_labs.length?o.latest_labs.slice(0,12).map(l=>`<div class="lab-row"><strong>${esc(l.test_name)}</strong><div>${esc(l.value_numeric ?? l.value_text ?? '—')} ${esc(l.units||'')}</div><div class="muted small">${esc(l.trend||'')}</div></div>`).join(''):'<div class="muted">No labs extracted.</div>'}</div></div>
    <div class="card"><div class="card-head"><h3>Medications</h3><button class="btn small" data-module="med-rec">Open Med Rec</button></div><div class="card-body">${o.medications.length?o.medications.slice(0,10).map(m=>`<div class="med-row"><div><strong>${esc(m.name)}</strong><div class="muted small">${esc([m.dose,m.route,m.frequency].filter(Boolean).join(' · '))}</div></div><div>${m.states.map(s=>`<span class="chip">${titleize(s.domain)}: ${titleize(s.status)}</span>`).join(' ')} ${m.unresolved?'<span class="status-pill warn">Review</span>':''}</div></div>`).join(''):'<div class="muted">No medication state extracted.</div>'}</div></div>
  </div><div class="grid">
    <div class="card"><div class="card-head"><h3>MediNote Intelligence</h3></div><div class="card-body">${intelligenceHtml(o)}</div></div>
    <div class="card"><div class="card-head"><h3>Consultants</h3></div><div class="card-body">${o.consultants.length?o.consultants.map(c=>`<div class="consult-row"><strong>${esc(c.service)}</strong><div>${esc(c.recommendation||c.assessment||'No recommendation text')}<div class="muted small">${fmtDate(c.recommendation_datetime)}</div></div></div>`).join(''):'<div class="muted">No consultant recommendations.</div>'}</div></div>
    <div class="card"><div class="card-head"><h3>Pending / Disposition</h3></div><div class="card-body">${o.pending_items.map(p=>`<div class="pending-row"><span class="status-pill warn">${esc(p.item_type)}</span><div>${esc(p.description)}<div class="muted small">Owner: ${esc(p.owner||'not established')}</div></div></div>`).join('') || '<div class="muted">No pending items.</div>'}<div style="margin-top:14px"><strong>Anticipated destination:</strong> ${esc(o.disposition?.anticipated_destination || 'Not established')}</div></div></div>
  </div></div>`;
}

function problemHtml(p) {
  const evidence = p.evidence?.map(e=>`${e.concept}${e.value?`: ${e.value}`:''}`).slice(0,4) || [];
  return `<div class="problem"><div class="problem-title"><span>#${p.acuity_rank ?? '—'} ${esc(p.name)}</span><span><span class="status-pill">${esc(p.status)}</span> ${p.certainty!=='confirmed'?`<span class="status-pill warn">${esc(p.certainty)}</span>`:''}</span></div><div class="problem-evidence">${evidence.length?esc(evidence.join(' · ')):'No linked objective evidence'}</div></div>`;
}

function intelligenceHtml(o) {
  const items=[];
  o.contradictions.forEach(c=>items.push(`<div class="intel-item ${esc(c.severity)}"><div class="intel-title">${titleize(c.category)} · ${titleize(c.severity)}</div><div class="small">${esc(c.description||'Unresolved contradiction')}</div><div style="margin-top:8px"><button class="btn small" data-adjudicate-contradiction="${c.id}">Physician adjudication</button></div></div>`));
  o.medications.filter(m=>m.unresolved).forEach(m=>items.push(`<div class="intel-item moderate"><div class="intel-title">Medication decision</div><div class="small">${esc(m.name)} has an unresolved medication state.</div></div>`));
  o.pending_items.slice(0,5).forEach(p=>items.push(`<div class="intel-item"><div class="intel-title">Pending ${esc(p.item_type)}</div><div class="small">${esc(p.description)}</div></div>`));
  return items.join('') || '<div class="muted">No current review flags.</div>';
}

function sourceImport() {
  return `${identityPanel()}<div class="grid two"><div class="card"><div class="card-head"><h2>Import Clinical Information</h2></div><div class="card-body"><form id="source-form" class="form-grid">
    <div class="field"><label>Source type</label><select name="document_type"><option value="progress_note">Progress note</option><option value="hp">H&P</option><option value="consult_note">Consult note</option><option value="nursing_note">Nursing note</option><option value="lab">Labs</option><option value="radiology">Radiology</option><option value="mar">MAR</option><option value="orders">Orders</option><option value="therapy">Therapy</option><option value="case_management">Case management</option><option value="other">Other</option></select></div>
    <div class="field"><label>Source date/time</label><input type="datetime-local" name="source_datetime"></div>
    <div class="field"><label>Source MRN (optional)</label><input name="asserted_mrn" placeholder="From source header"></div>
    <div class="field"><label>Source DOB (optional)</label><input type="date" name="asserted_dob"></div>
    <div class="field full"><label>Source patient name (optional)</label><input name="asserted_name" placeholder="Use only if present in source"></div>
    <div class="field full"><label>Chart text</label><textarea name="raw_text" placeholder="Paste ED note, H&P, progress note, labs, imaging, medications, consultant recommendations, therapy or case-management data here…" required></textarea></div>
    <div class="field full"><div class="source-actions"><span class="muted small">Raw source is preserved before MCIF extraction.</span><div class="actions"><button type="submit" class="btn">Save Source</button><button type="button" class="btn primary" data-action="analyze">Analyze Patient</button></div></div></div>
  </form></div></div><div class="card"><div class="card-head"><h3>Workflow</h3></div><div class="card-body"><div class="summary-box">Raw chart → source preservation → MCIF extraction → reconciliation → synthesis → shared patient state.</div><p class="muted small">MediNote does not treat imported prose as physician-approved clinical action. Recommendations, medication states, and uncertainty remain separate until reviewed.</p></div></div></div>`;
}

function documentView() {
  const map={hp:['H&P','admission',['standard','admission','short','complex','updated','consult_style']],progress:['Progress Note','daily',['standard','daily','short','mini','complex','interval']],discharge:['Discharge','summary',['summary','short','clinical_course','med_reconciliation','avs','addendum']],signout:['Signout','standard',['standard','night','weekend','short','complex']]};
  const [label, def, variants]=map[state.module];
  const d=state.activeDocument;
  if (!d || d.document_type !== state.module.replace('progress','progress')) return `<div class="card"><div class="card-head"><h2>${label}</h2></div><div class="card-body"><div class="form-grid"><div class="field"><label>Variation</label><select id="variant-select">${variants.map(v=>`<option value="${v}" ${v===def?'selected':''}>${titleize(v)}</option>`).join('')}</select></div><div class="field" style="justify-content:end"><button class="btn primary" data-action="generate-document">Generate ${label}</button></div></div><div class="summary-box" style="margin-top:18px">Generated from the validated shared MCIF patient state. Every section remains physician-editable and is audited before finalization.</div></div></div>`;
  return noteEditor(d, label);
}

function noteEditor(d,label) {
  return `<div class="grid two"><div><div class="card"><div class="card-head"><div><h2>${label} · ${titleize(d.variant)}</h2><div class="muted small">${titleize(d.status)} · ${fmtDate(d.generated_at)}</div></div><div class="note-toolbar"><button class="btn small" data-action="approve-document" ${d.status==='approved'||d.status==='finalized'?'disabled':''}>Approve</button><button class="btn small" data-action="audit-document">Run Safety Review</button><button class="btn primary small" data-action="finalize-document" ${d.status!=='approved'?'disabled':''}>Finalize</button><button class="btn small" data-action="copy-final">Copy to Epic</button></div></div><div class="card-body">${d.review_reasons?.length?`<div class="summary-box" style="margin-bottom:14px"><strong>Review required</strong><div class="small">${d.review_reasons.map(esc).join(' · ')}</div></div>`:''}${d.sections.map(sectionEditor).join('')}</div></div></div>
  <div class="grid"><div class="card"><div class="card-head"><h3>Safety Review</h3><span class="status-pill ${state.safetyFlags.some(f=>['high','critical'].includes(f.severity)&&f.status==='open')?'bad':'good'}">${state.safetyFlags.filter(f=>f.status==='open').length} open</span></div><div class="card-body"><div class="safety-list">${safetyHtml()}</div></div></div><div class="card"><div class="card-head"><h3>Document Status</h3></div><div class="card-body"><p><strong>${titleize(d.status)}</strong></p><p class="muted small">Sections are independently reviewed. Finalization re-runs the audit against the current approved text and MCIF state.</p></div></div></div></div>`;
}

function sectionEditor(s) {
  const serverContent=s.physician_content ?? s.generated_content; const content=localStorage.getItem(draftKey(s.id)) ?? serverContent;
  return `<div class="section-card" data-section-card="${s.id}"><div class="section-head"><div><span class="section-title">${titleize(s.section_type)}</span> <span class="status-pill ${s.approval_status==='accepted'||s.approval_status==='edited'?'good':''}">${titleize(s.approval_status)}</span></div><div class="section-actions"><button class="btn small" data-section-action="accept" data-section="${s.id}">Accept</button><button class="btn small" data-section-action="save" data-section="${s.id}">Save Edit</button><button class="btn small" data-section-action="regenerate" data-section="${s.id}">Regenerate</button></div></div><div class="section-body"><textarea id="section-${s.id}">${esc(content)}</textarea>${s.evidence?.length?`<div class="evidence-chips">${s.evidence.map(e=>`<span class="chip">${esc(e.concept)}${e.value?`: ${esc(e.value)}`:''}</span>`).join('')}</div>`:''}</div></div>`;
}

function safetyHtml() {
  const open=state.safetyFlags.filter(f=>f.status==='open');
  if (!open.length) return '<div class="muted">Run Safety Review to validate the current document.</div>';
  return open.map(f=>`<div class="intel-item ${esc(f.severity)}"><div class="intel-title">${titleize(f.category)} · ${titleize(f.severity)}</div><div class="small">${esc(f.description)}</div>${f.claim_text?`<div class="small muted" style="margin-top:5px">Claim: ${esc(f.claim_text)}</div>`:''}<div style="margin-top:8px"><button class="btn small" data-resolve-flag="${f.id}">Acknowledge review</button></div></div>`).join('');
}

function medRecView() {
  if (!state.medRec) return `<div class="card"><div class="card-head"><h2>Medication Reconciliation</h2></div><div class="card-body"><button class="btn primary" data-action="load-med-rec">Open Med Rec</button></div></div>`;
  const w=state.medRec;
  return `<div class="card"><div class="card-head"><div><h2>Medication Reconciliation</h2><div class="muted small">Home → Hospital → Discharge</div></div><div><span class="status-pill warn">${w.unresolved_count} unresolved</span> <span class="status-pill">${w.high_risk_count} high risk</span></div></div><div class="card-body"><table class="med-table"><thead><tr><th>Medication</th><th>Home</th><th>Hospital</th><th>Discharge</th><th>Decision</th></tr></thead><tbody>${w.medications.map(m=>`<tr><td><strong>${esc(m.name)}</strong><div class="muted small">${esc([m.dose,m.route,m.frequency].filter(Boolean).join(' · '))}</div>${m.high_risk?'<span class="status-pill warn">High risk</span>':''}</td><td>${stateCell(m.home)}</td><td>${stateCell(m.hospital)}</td><td>${stateCell(m.discharge)}</td><td><select id="med-state-${m.medication_id}"><option value="">Choose…</option>${['continue','stop','resume','changed_dose','changed_route','changed_frequency','newly_started','inpatient_only','completed','unclear','requires_decision'].map(x=>`<option value="${x}">${titleize(x)}</option>`).join('')}</select><input id="med-reason-${m.medication_id}" placeholder="Reason" style="margin-top:6px"><button class="btn small" style="margin-top:6px" data-med-confirm="${m.medication_id}">Confirm</button></td></tr>`).join('')}</tbody></table></div></div>`;
}
function stateCell(s){ return s?`<strong>${titleize(s.status)}</strong><div class="muted small">${esc(s.reason||'')}</div>${s.physician_confirmed?'<span class="status-pill good">Confirmed</span>':''}`:'<span class="muted">—</span>'; }

function renderModal() {
  if (state.modal==='new-patient') return `<div class="overlay"><div class="modal"><div class="modal-head"><strong>New Patient Encounter</strong><button class="btn small" data-action="close-modal">×</button></div><form id="patient-form"><div class="modal-body form-grid"><div class="field"><label>First name</label><input name="first_name"></div><div class="field"><label>Last name</label><input name="last_name"></div><div class="field"><label>MRN</label><input name="mrn"></div><div class="field"><label>Date of birth</label><input type="date" name="date_of_birth"></div><div class="field"><label>Sex</label><input name="sex"></div><div class="field"><label>Admission date/time</label><input type="datetime-local" name="admission_datetime"></div><div class="field"><label>Service</label><input name="service" value="Hospital Medicine"></div><div class="field"><label>Location</label><input name="location" placeholder="e.g. 6 East"></div></div><div class="modal-foot"><button type="button" class="btn" data-action="close-modal">Cancel</button><button class="btn primary" type="submit">Create Encounter</button></div></form></div></div>`;
  return '';
}

function bind() {
  document.querySelectorAll('[data-action="logout"]').forEach(b=>b.onclick=logout);
  document.querySelectorAll('[data-action="dashboard"]').forEach(b=>b.onclick=()=>{state.activeEncounterId=null;state.overview=null;state.module='overview';render();});
  document.querySelectorAll('[data-action="new-patient"]').forEach(b=>b.onclick=()=>{state.modal='new-patient';render();});
  document.querySelectorAll('[data-action="close-modal"]').forEach(b=>b.onclick=()=>{state.modal=null;render();});
  document.querySelectorAll('[data-encounter]').forEach(b=>b.onclick=()=>selectEncounter(b.dataset.encounter));
  document.querySelectorAll('[data-module]').forEach(b=>b.onclick=async()=>{state.module=b.dataset.module;state.activeDocument=null;state.safetyFlags=[]; if(state.module==='med-rec') await loadMedRec(); render();});
  document.querySelectorAll('[data-action="refresh"]').forEach(b=>b.onclick=async()=>{await refreshOverview(); render();});
  document.querySelectorAll('[data-action="analyze"]').forEach(b=>b.onclick=analyzePatient);
  document.querySelectorAll('[data-action="generate-document"]').forEach(b=>b.onclick=generateDocument);
  document.querySelectorAll('[data-action="load-med-rec"]').forEach(b=>b.onclick=async()=>{await loadMedRec();render();});
  document.querySelectorAll('[data-section-action]').forEach(b=>b.onclick=()=>sectionAction(b.dataset.sectionAction,b.dataset.section));
  document.querySelectorAll('[data-section-card] textarea').forEach(t=>t.oninput=()=>localStorage.setItem(draftKey(t.id.replace('section-','')),t.value));
  document.querySelectorAll('[data-action="approve-document"]').forEach(b=>b.onclick=approveDocument);
  document.querySelectorAll('[data-action="audit-document"]').forEach(b=>b.onclick=auditDocument);
  document.querySelectorAll('[data-action="finalize-document"]').forEach(b=>b.onclick=finalizeDocument);
  document.querySelectorAll('[data-action="copy-final"]').forEach(b=>b.onclick=copyFinal);
  document.querySelectorAll('[data-adjudicate-contradiction]').forEach(b=>b.onclick=()=>adjudicateContradiction(b.dataset.adjudicateContradiction));
  document.querySelectorAll('[data-resolve-flag]').forEach(b=>b.onclick=()=>resolveFlag(b.dataset.resolveFlag));
  document.querySelectorAll('[data-med-confirm]').forEach(b=>b.onclick=()=>confirmMed(b.dataset.medConfirm));
  document.querySelectorAll('[data-verify-source]').forEach(b=>b.onclick=()=>verifySourceIdentity(b.dataset.verifySource));
  document.querySelectorAll('[data-remove-source]').forEach(b=>b.onclick=()=>removeSource(b.dataset.removeSource));
  const pf=document.getElementById('patient-form'); if(pf) pf.onsubmit=createPatient;
  const sf=document.getElementById('source-form'); if(sf) sf.onsubmit=saveSource;
}

async function createPatient(e){ e.preventDefault(); const f=new FormData(e.target); const org=state.organizations[0]; if(!org) return toast('No organization configured',true); const val=n=>f.get(n)||null; try { const enc=await api('/encounters',{method:'POST',body:JSON.stringify({organization_id:org.id,patient:{first_name:val('first_name'),last_name:val('last_name'),mrn:val('mrn'),date_of_birth:val('date_of_birth'),sex:val('sex')},admission_datetime:val('admission_datetime')?new Date(val('admission_datetime')).toISOString():null,service:val('service'),location:val('location')})}); state.modal=null; await loadEncounters(); await selectEncounter(enc.id); toast('Encounter created'); } catch(err){toast(err.message,true);} }

async function saveSource(e){ e.preventDefault(); const f=new FormData(e.target); try{await api(`/encounters/${state.activeEncounterId}/sources`,{method:'POST',body:JSON.stringify({document_type:f.get('document_type'),source_datetime:f.get('source_datetime')?new Date(f.get('source_datetime')).toISOString():null,source_system:'manual_paste',raw_text:f.get('raw_text'),asserted_mrn:f.get('asserted_mrn')||null,asserted_dob:f.get('asserted_dob')||null,asserted_name:f.get('asserted_name')||null})}); e.target.reset(); await refreshIdentity(); toast('Source saved');}catch(err){toast(err.message,true);} }

async function analyzePatient(){ if(!state.activeEncounterId)return; try{await refreshIdentity(); if(state.identity?.hard_stop){render(); return toast('Patient identity hard stop must be resolved before analysis.',true);} state.loading=true;const r=await api(`/encounters/${state.activeEncounterId}/analyze`,{method:'POST'});await refreshOverview();toast(`Analysis complete: ${r.facts_created} facts, ${r.problems_created} problems`);}catch(e){toast(e.message,true);}finally{state.loading=false;render();} }

async function generateDocument(){ const variant=document.getElementById('variant-select')?.value; const module=state.module; try{state.activeDocument=await api(`/encounters/${state.activeEncounterId}/documents/${module}`,{method:'POST',body:JSON.stringify({variant})});state.safetyFlags=[];render();toast(`${titleize(module)} draft generated`);}catch(e){toast(e.message,true);} }

async function sectionAction(action,id){
  const ta=document.getElementById(`section-${id}`); const sec=state.activeDocument?.sections?.find(s=>s.id===id);
  const scope=`section_${state.activeDocument?.document_id}_${id}_${action}`; const idem=recoveryKey(scope);
  if(ta) localStorage.setItem(draftKey(id),ta.value);
  try{
    if(action==='regenerate'){
      await api(`/documents/${state.activeDocument.document_id}/sections/${id}/regenerate`,{method:'POST',idempotencyKey:idem,body:JSON.stringify({instruction:null,expected_section_version:sec?.edit_version??null})});
    } else {
      await api(`/documents/${state.activeDocument.document_id}/sections/${id}`,{method:'PATCH',idempotencyKey:idem,body:JSON.stringify({action:action==='accept'?'accept':'edit',physician_content:action==='accept'?null:ta.value,expected_section_version:sec?.edit_version??null})});
    }
    clearRecoveryKey(scope); localStorage.removeItem(draftKey(id)); await reloadDocument(); toast(action==='regenerate'?'Section regenerated':action==='accept'?'Section accepted':'Edit saved');
  }catch(e){
    if(e.status===409){ toast(`Concurrent/recovery protection: ${e.message}`,true); await reloadDocument(); }
    else { toast(e.message,true); }
  }
}

async function reloadDocument(){ const d=state.activeDocument; if(!d)return; const type=d.document_type; state.activeDocument=await api(`/documents/${d.document_id}/${type}`); try{const lease=await api(`/edit-leases/document/${d.document_id}`,{method:'POST'}); if(!lease.acquired) toast(`Another clinician is editing this document: ${lease.holder_display_name||'another user'}`,true);}catch{} render(); }

async function approveDocument(){ try{const r=await api(`/documents/${state.activeDocument.document_id}/approve`,{method:'POST',body:JSON.stringify({actor_id:null,expected_document_version:state.activeDocument?.edit_version??null})}); if(r.pending_section_ids?.length) toast(`${r.pending_section_ids.length} sections still need review`,true); await reloadDocument();}catch(e){toast(e.message,true);} }
async function auditDocument(){ try{const r=await api(`/documents/${state.activeDocument.document_id}/audit`,{method:'POST'});state.safetyFlags=r.flags;render();toast(r.status==='pass'?'Safety review passed':`${r.blocking_flags+r.warning_flags} items require review`,r.blocking_flags>0);}catch(e){toast(e.message,true);} }
async function resolveFlag(id){ const resolution=prompt('Document your review/resolution:'); if(!resolution)return; try{await api(`/safety-flags/${id}/resolve`,{method:'POST',body:JSON.stringify({resolution,resolution_type:'physician_reviewed'})}); await auditDocument();}catch(e){toast(e.message,true);} }
async function adjudicateContradiction(id){
  try{
    const d=await api(`/contradictions/${id}`);
    const a=d.source_a?.text||'Source A unavailable';
    const b=d.source_b?.text||'Source B unavailable';
    const choice=prompt(`Resolve contradiction:\nA: ${a}\nB: ${b}\n\nEnter A, B, or NEW:`);
    if(!choice)return;
    let resolution_type, decision_text=null;
    if(choice.trim().toUpperCase()==='A') resolution_type='select_source_a';
    else if(choice.trim().toUpperCase()==='B') resolution_type='select_source_b';
    else if(choice.trim().toUpperCase()==='NEW'){ resolution_type='new_clinical_decision'; decision_text=prompt('Enter your current clinical decision/interpretation:'); if(!decision_text)return; }
    else { toast('Choose A, B, or NEW',true); return; }
    const reason=prompt('Document the clinical reason/source for this adjudication:');
    if(!reason)return;
    const result=await api(`/contradictions/${id}/adjudicate`,{method:'POST',body:JSON.stringify({resolution_type,reason,decision_text,expected_revision:d.revision??null})});
    await refreshOverview();
    if(state.activeDocument) await reloadDocument();
    toast(`Contradiction resolved; ${result.regenerated_section_ids?.length||0} section(s) regenerated`);
    render();
  }catch(e){toast(e.message,true);}
}


async function verifySourceIdentity(id){
  const reason=prompt('Document how you verified this source belongs to the selected patient:'); if(!reason)return;
  try{await api(`/sources/${id}/identity/verify`,{method:'POST',body:JSON.stringify({confirmed_match:true,reason})});await refreshIdentity();render();toast('Source identity physician-verified');}catch(e){toast(e.message,true);}
}
async function removeSource(id){
  if(!confirm('Remove this quarantined/untrusted source from the encounter?'))return;
  try{await api(`/sources/${id}`,{method:'DELETE'});await refreshIdentity();render();toast('Source removed');}catch(e){toast(e.message,true);}
}

async function finalizeDocument(){ const scope=`finalize_${state.activeDocument.document_id}`; const idem=recoveryKey(scope); try{const r=await api(`/documents/${state.activeDocument.document_id}/finalize`,{method:'POST',idempotencyKey:idem,body:JSON.stringify({actor_id:null,expected_document_version:state.activeDocument?.edit_version??null})});clearRecoveryKey(scope); if(r.blocking_flag_ids?.length){toast(`${r.blocking_flag_ids.length} blocking safety issue(s) remain`,true);await auditDocument();return;} await reloadDocument();toast('Document finalized');}catch(e){toast(e.message,true);} }
async function copyFinal(){ try{const r=await api(`/documents/${state.activeDocument.document_id}/final-text`);await navigator.clipboard.writeText(r.text);toast('Clinician-reviewed note copied');}catch(e){toast(`Copy failed: ${e.message}`,true);} }
async function loadMedRec(){ if(!state.activeEncounterId)return; try{state.medRec=await api(`/encounters/${state.activeEncounterId}/med-rec`);}catch(e){toast(e.message,true);} }
async function confirmMed(id){ const status=document.getElementById(`med-state-${id}`)?.value; const reason=document.getElementById(`med-reason-${id}`)?.value||null; const med=state.medRec?.medications?.find(m=>m.medication_id===id); if(!status)return toast('Choose a discharge state',true); const scope=`medrec_${id}_${med?.discharge?.state_id||'none'}`; const idem=recoveryKey(scope); try{await api(`/medications/${id}/confirm-discharge-state`,{method:'POST',idempotencyKey:idem,body:JSON.stringify({status,reason,restart_criteria:null,confirmed_by:null,expected_current_state_id:med?.discharge?.state_id??null})});clearRecoveryKey(scope);await loadMedRec();await refreshOverview();render();toast('Medication decision confirmed');}catch(e){toast(e.message,true);} }


function authScreen() {
  const setup = state.authMode === 'setup';
  return `<div class="auth-wrap"><div class="auth-card"><div class="brand" style="margin-bottom:18px"><div class="brand-mark">M</div><div>MediNote</div></div>
    <h1>${setup?'Initialize Pilot':'Physician Login'}</h1><p class="muted">${setup?'Create the first organization administrator. This endpoint disables itself after the first user is created.':'Secure access to the hospitalist pilot workspace.'}</p>
    <form id="auth-form" class="form-grid">
      ${setup?'<div class="field full"><label>Organization</label><input name="organization_name" value="MediNote Pilot" required></div><div class="field full"><label>Display name</label><input name="display_name"></div>':''}
      <div class="field full"><label>Email</label><input type="email" name="email" required autocomplete="username"></div>
      <div class="field full"><label>Password</label><input type="password" name="password" required minlength="${setup?12:8}" autocomplete="${setup?'new-password':'current-password'}"></div>
      <div class="field full"><button class="btn primary" type="submit">${setup?'Create Pilot Admin':'Sign In'}</button></div>
    </form>
    <button class="btn small" id="auth-switch">${setup?'Back to login':'First-time pilot setup'}</button>
  </div></div>`;
}
function bindAuth(){ const f=document.getElementById('auth-form'); if(f)f.onsubmit=submitAuth; const sw=document.getElementById('auth-switch'); if(sw)sw.onclick=()=>{state.authMode=state.authMode==='login'?'setup':'login';render();}; }
async function submitAuth(e){ e.preventDefault(); const f=new FormData(e.target); const setup=state.authMode==='setup'; const body=setup?{organization_name:f.get('organization_name'),display_name:f.get('display_name')||null,email:f.get('email'),password:f.get('password')}:{email:f.get('email'),password:f.get('password')}; try{ const r=await api(setup?'/auth/bootstrap':'/auth/login',{method:'POST',body:JSON.stringify(body)}); state.token=r.access_token; state.user=r.user; localStorage.setItem('medinote_token',state.token); state.organizations=await api('/organizations'); await loadEncounters(); render(); toast(setup?'Pilot administrator created':'Signed in'); }catch(err){toast(err.message,true);} }
async function logout(){ try{await api('/auth/logout',{method:'POST'});}catch{} localStorage.removeItem('medinote_token'); state.token=null; state.user=null; state.encounters=[]; state.activeEncounterId=null; render(); }

bootstrap();
