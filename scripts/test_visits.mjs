// Test telemetry without a browser, network, cookies or real visitor data.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
const code=fs.readFileSync(new URL('../static/js/visits.js',import.meta.url),'utf8');
function setup(visible=true, fail=false){
  const events={}, calls=[];
  const document={visibilityState:visible?'visible':'hidden',addEventListener:(k,f)=>events[k]=f};
  const context={document,crypto:webcrypto,location:{pathname:'/lyrics/少女/',search:'?private=1',hash:'#private'},
    fetch:(url,options)=>{calls.push({url,options});return fail?Promise.reject(Error('offline')):Promise.resolve({status:204});}};
  vm.runInNewContext(code,context);
  return {document,events,calls};
}
const a=setup();assert.equal(a.calls.length,1);
const call=a.calls[0], body=JSON.parse(call.options.body);
assert.equal(call.url,'/community/api/visits/');
assert.equal(call.options.credentials,'omit');
assert.equal(call.options.mode,'same-origin');
assert.deepEqual(Object.keys(body).sort(),['event_id','path']);
assert.equal(body.path,'/lyrics/少女/');
assert.match(body.event_id,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
a.events.visibilitychange();assert.equal(a.calls.length,1);
const b=setup(false);assert.equal(b.calls.length,0);
b.document.visibilityState='visible';b.events.visibilitychange();assert.equal(b.calls.length,1);
b.events.visibilitychange();assert.equal(b.calls.length,1);
assert.notEqual(JSON.parse(b.calls[0].options.body).event_id,body.event_id);
setup(true,true);await new Promise(resolve=>setTimeout(resolve,0));
console.log('PASS: one private page-load event, visibility gating, unique IDs, no query/hash or cookies, offline isolation');
