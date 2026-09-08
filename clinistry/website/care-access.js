import {SERVICES, normalizeService, schedulingChecks, stepRequest, submitPreview} from './care-access-model.js';
const form = document.querySelector('#access-form');
const fields = ['choose','prepare','visit'].map(id => document.getElementById(id));
const next = document.querySelector('#next');
const back = document.querySelector('#back');
const complete = document.querySelector('#complete');
const error = document.querySelector('#error');
const retry = document.querySelector('#retry');
const connection = document.querySelector('#connection');
const mode = document.body.dataset.serviceMode;
let step = 0;
let ready = false;
let busy = false;
form.elements.service.value = normalizeService(new URLSearchParams(location.search).get('service'));
function values() {
 const result = {service:form.elements.service.value};
 for(const name of ['adult','non_emergency','identity','consent','north_carolina','private_space','video_audio']) result[name] = form.elements[name].checked;
 return result;
}
function showSelection() { document.querySelector('#chosen-care').textContent = SERVICES[normalizeService(form.elements.service.value)]; }
showSelection();
form.elements.service.forEach(input => input.addEventListener('change', showSelection));
function controls() {
 next.disabled = !ready || busy;
 back.disabled = busy;
 next.textContent = busy ? 'Checking…' : step === 2 ? 'Review preparation' : 'Continue';
}
function setStep(value) {
 step = value;
 fields.forEach((field,index) => { field.hidden = index !== value; field.disabled = index !== value; });
 back.hidden = value === 0;
 form.hidden = value === 3; complete.hidden = value !== 3;
 document.querySelectorAll('.steps li').forEach((item,index) => { item.classList.toggle('active', index === value); if(index === value) item.setAttribute('aria-current','step'); else item.removeAttribute('aria-current'); });
 controls();
 if(value === 3) complete.focus(); else fields[value].querySelector('input').focus();
}
async function connect() {
 ready = false; retry.hidden = true; error.textContent = ''; next.disabled = true;
 if(mode === 'walkthrough') {
  ready = true; connection.textContent = 'Website walkthrough only. Your choices stay on this page and are cleared when you leave.'; controls(); return;
 }
 try {
  if(mode !== 'connected') throw new Error('Unknown service mode.');
  const response = await fetch('/api/v1/care-access/journey', {signal:AbortSignal.timeout(10000)});
  if(!response.ok) throw new Error('Unavailable');
  const data = await response.json();
  if(data.synthetic !== true || data.live_care_enabled !== false || data.patient_data_enabled !== false || !Array.isArray(data.stages) || data.stages.length !== 3 || data.stages.some(item => item.mode !== 'preview' || item.live !== false)) throw new Error('Unavailable');
  ready = true;
  connection.textContent = 'Preparation service connected. Enrollment remains closed; no medical information is collected.';
 } catch {
  connection.textContent = 'Preparation service unavailable. Enrollment remains closed.';
  error.textContent = 'We could not load the preparation service. Please try again.';
  retry.hidden = false;
 }
 controls();
}
function summarize(v, result) {
 const missing = schedulingChecks(v).filter(([,ok]) => !ok).map(([name]) => name);
 document.querySelector('#selection').textContent = SERVICES[normalizeService(v.service)];
 const assessedReady = result ? result.ready_for_future_scheduling : missing.length === 0;
 document.querySelector('#preparation-result').textContent = assessedReady ? 'Your preparation checklist is complete. An appointment has not been booked.' : 'There are preparation items still to review. An appointment has not been booked.';
 document.querySelector('#remaining').replaceChildren(...missing.map(name => { const li = document.createElement('li'); li.textContent = name; return li; }));
}
form.addEventListener('submit', async event => {
 event.preventDefault();
 if(!ready || busy || !form.reportValidity()) return;
 error.textContent = ''; busy = true; controls();
 const v = values();
 try {
  stepRequest(step, v);
  const result = mode === 'connected' ? await submitPreview(step, v) : null;
  if(step === 2) summarize(v, result);
  setStep(step + 1);
 } catch(err) { error.textContent = err.name === 'TimeoutError' ? 'The service took too long to respond. Your choices remain here; please try again.' : err.message; }
 finally { busy = false; controls(); }
});
back.addEventListener('click', () => { if(!busy) { error.textContent = ''; setStep(step - 1); } });
document.querySelector('#edit-preparation').addEventListener('click', () => setStep(2));
document.querySelector('#restart').addEventListener('click', () => { form.reset(); showSelection(); error.textContent = ''; setStep(0); });
retry.addEventListener('click', connect);
connect();
