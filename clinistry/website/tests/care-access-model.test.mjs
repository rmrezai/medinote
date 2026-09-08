import test from 'node:test';
import assert from 'node:assert/strict';
import {SERVICES,normalizeService,schedulingChecks,stepRequest,submitPreview} from '../care-access-model.js';
const values = {service:'sleep_medicine',adult:true,non_emergency:true,identity:true,consent:true,north_carolina:true,private_space:true,video_audio:true};
test('every offered pathway stays consistent from registration to scheduling', () => {
 for(const service of Object.keys(SERVICES)) {
  assert.equal(stepRequest(0,{...values,service}).body.service_interest,service);
  assert.equal(stepRequest(2,{...values,service}).body.visit_type,service);
 }
 assert.equal(normalizeService('https://untrusted.example'), 'general_telemedicine');
 assert.equal(normalizeService('__proto__'), 'general_telemedicine');
});
test('required acknowledgments block advancement', () => {
 assert.throws(()=>stepRequest(0,{...values,adult:false}));
 assert.throws(()=>stepRequest(0,{...values,non_emergency:false}));
 assert.throws(()=>stepRequest(1,{...values,consent:false}));
 assert.throws(()=>stepRequest(3,values));
});
test('unchecked preparation is preserved rather than claimed as complete', async () => {
 const incomplete={...values,north_carolina:false,video_audio:false};
 assert.equal(schedulingChecks(incomplete).filter(([,ok])=>!ok).length,2);
 const result=await submitPreview(2,incomplete,async(path,options)=>{
  assert.equal(path,'/api/v1/patient-scheduling/readiness');
  const body=JSON.parse(options.body);
  assert.equal(body.located_in_north_carolina,false);
  assert.equal(body.video_audio_available,false);
  assert.equal(body.visit_type,'sleep_medicine');
  return {ok:true,json:async()=>({synthetic:true,scheduling_open:false,visit_type:'sleep_medicine',ready_for_future_scheduling:false})};
 });
 assert.equal(result.ready_for_future_scheduling,false);
});
test('request allowlist excludes any unexpected personal information', () => {
 const body=stepRequest(0,{...values,email:'must-not-send@example.com',medical_history:'must-not-send'}).body;
 assert.deepEqual(Object.keys(body).sort(),['accepts_non_emergency_notice','service_interest']);
});
test('failed or live responses cannot complete a preview step', async () => {
 await assert.rejects(submitPreview(0,values,async()=>({ok:false})),/temporarily unavailable/);
 for(const data of [{synthetic:true,registration_open:true},{synthetic:false,registration_open:false},{}]) {
  await assert.rejects(submitPreview(0,values,async()=>({ok:true,json:async()=>data})),/verified as a preview/);
 }
 await assert.rejects(submitPreview(2,values,async()=>({ok:true,json:async()=>({synthetic:true,scheduling_open:false,visit_type:'weight_management',ready_for_future_scheduling:true})})),/could not be verified/);
});
test('transport exceptions remain failures', async () => {
 await assert.rejects(submitPreview(0,values,async()=>{throw new Error('connection lost');}),/connection lost/);
});
