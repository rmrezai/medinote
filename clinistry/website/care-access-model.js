export const SERVICES = Object.freeze({
 general_telemedicine: 'Adult & geriatric primary care',
 weight_management: 'Weight management',
 sleep_medicine: 'Sleep medicine · planned',
});
export function normalizeService(value) {
 return Object.hasOwn(SERVICES, value) ? value : 'general_telemedicine';
}
export function schedulingChecks(values) {
 return [
  ['North Carolina location', values.north_carolina === true],
  ['A private visit space', values.private_space === true],
  ['Video and audio access', values.video_audio === true],
  ['Non-emergency use', values.non_emergency === true],
 ];
}
export function stepRequest(step, values) {
 const service = normalizeService(values.service);
 if(step === 0) {
  if(values.adult !== true || values.non_emergency !== true) throw new Error('Please confirm adult-only and non-emergency use.');
  return {path:'/api/v1/patient-registration/start', flag:'registration_open', body:{service_interest:service, accepts_non_emergency_notice:true}};
 }
 if(step === 1) {
  if(values.identity !== true || values.consent !== true || values.non_emergency !== true) throw new Error('Please review the account and consent requirements.');
  return {path:'/api/v1/patient-intake/readiness', flag:'intake_open', body:{identity_verification_understood:true, consent_required_understood:true, non_emergency_notice_understood:true}};
 }
 if(step === 2) return {path:'/api/v1/patient-scheduling/readiness', flag:'scheduling_open', body:{visit_type:service, located_in_north_carolina:values.north_carolina === true, private_space_available:values.private_space === true, video_audio_available:values.video_audio === true, non_emergency_notice_understood:values.non_emergency === true}};
 throw new Error('Unknown care step.');
}
export async function submitPreview(step, values, fetcher = fetch) {
 const request = stepRequest(step, values);
 const response = await fetcher(request.path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(request.body), signal:AbortSignal.timeout(10000)});
 if(!response.ok) throw new Error('This step is temporarily unavailable. Your progress is still on this page; please try again.');
 const result = await response.json();
 if(result.synthetic !== true || result[request.flag] !== false) throw new Error('This response could not be verified as a preview. Please try again later.');
 if(step === 2 && (result.visit_type !== request.body.visit_type || typeof result.ready_for_future_scheduling !== 'boolean')) throw new Error('The scheduling response could not be verified.');
 return result;
}
