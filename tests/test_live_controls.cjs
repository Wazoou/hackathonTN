// The production controls and model merge, with a fixed clock and a tiny DOM adapter.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const D=require('../dashboard/risk_component/daily_logic.js');
const elements=new Map(),storage=new Map(),frames=new Map(),updates=[],loading=[];let next=0;
const el=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',open:false,setAttribute(key,value){this[key]=value;}});return elements.get(id);};
class Clock extends Date{constructor(...args){super(...(args.length?args:['2026-07-03T12:00:00Z']));}static now(){return Date.parse('2026-07-03T12:00:00Z');}}
const context=vm.createContext({document:{getElementById:el,body:{dataset:{}}},DailyLogic:D,Date:Clock,Intl,
 performance:{now:()=>0},requestAnimationFrame:fn=>{frames.set(++next,fn);return next;},cancelAnimationFrame:id=>frames.delete(id),
 setTimeout:()=>1,clearTimeout(){},sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)}});
vm.runInContext(fs.readFileSync('dashboard/risk_component/daily_controls.js','utf8'),context);
const controls=context.DailyControls({onDay:day=>updates.push(day),onLoading:value=>loading.push(value)});
const flushFrame=()=>{const callbacks=[...frames.values()];frames.clear();callbacks.forEach(fn=>fn());};
const flush=()=>{let count=0;while(frames.size){assert.ok(++count<10,'Animation must complete');flushFrame();}};
const history={model_version:'same-model',station_ids:['station'],dates:['2026-07-01'],stations:1,z:new Float32Array([0]),fwi:new Float32Array([10]),
 coefficient:1,commune_station:new Int32Array([0]),commune_terrain:new Float64Array([0]),cell_commune:new Int32Array([0]),cell_share:new Float64Array([1]),
 expected:new Float64Array([.5]),fires:{},bdiff_end:'2025-12-31',legend:[],meta:{meteo:{stations:1}}};
const forecast={model_version:'same-model',stations:['station'],dates:['2026-07-01','2026-07-02','2026-07-03','2026-07-04','2026-07-05'],
 z:[[99],[0],[1],[2],[3]],fwi:[[99],[10],[20],[30],[40]],provenance:Array.from({length:5},()=>({issued_at:'2026-07-03T10:00:00Z',consolidated:false})),source:'Open-Meteo'};
controls.install(history);assert.equal(el('daily-live').disabled,true);assert.equal(el('daily-forecast').disabled,true);
let merged=D.withOperational(history,forecast);
assert.equal(merged.z[0],0);assert.equal(merged.fwi[0],10); // Never overwrite station observations.
assert.equal(D.computeDay(merged,2).known,false);assert.equal(D.computeDay(merged,2).fires.length,0);
controls.install(merged);assert.equal(el('daily-live').disabled,false);assert.equal(el('daily-forecast').disabled,false);
el('daily-live').onclick();assert.equal(loading.at(-1),true);
const beforePaint=updates.length;flushFrame();assert.equal(updates.length,beforePaint); // Veil paints before calculation.
flushFrame();assert.equal(loading.at(-1),true); // Await the map redraw.
flush();assert.equal(loading.at(-1),false);
assert.equal(updates.at(-1).key,'2026-07-03');assert.equal(updates.at(-1).kind,'live');assert.equal(updates.at(-1).activate,true);
assert.equal(el('daily-slider').disabled,true);assert.equal(el('daily-date').disabled,true);
el('daily-forecast').onclick();flush();
assert.equal(updates.at(-1).key,'2026-07-04');assert.equal(updates.at(-1).kind,'forecast');assert.equal(el('daily-slider').max,1);
el('daily-slider').value='1';el('daily-slider').oninput();flush();assert.equal(updates.at(-1).key,'2026-07-05');
el('daily-date').value='2026-07-02';el('daily-date').onchange();assert.equal(el('daily-date').value,'2026-07-05');
el('daily-live').onclick();flush();const old=updates.at(-1).values[0];
forecast.z[2]=[3];forecast.provenance[2]={issued_at:'2026-07-03T11:30:00Z'};
merged=D.withOperational(history,forecast);controls.install(merged);
assert.equal(updates.at(-1).key,'2026-07-03');assert.notEqual(updates.at(-1).values[0],old);assert.equal(updates.at(-1).revision,'2026-07-03T11:30:00Z');
controls.setStatus({retrieved_at:'2026-07-03T11:30:00Z',next_check:'2026-07-03T13:00:00Z'});
controls.setStatus({error:'réseau absent'});assert.match(el('daily-live-status').textContent,/03\/07 13:30/);assert.match(el('daily-live-status').textContent,/dernière carte conservée/);
el('daily-archives').onclick();flush();assert.equal(updates.at(-1).key,'2026-07-01');
el('daily-latest').onclick();flush();assert.equal(updates.at(-1).key,'2026-07-02');assert.equal(updates.at(-1).kind,'archive');
el('daily-live').onclick();flushFrame();flushFrame();
assert.equal(loading.at(-1),true);
el('daily-forecast').onclick();flush();assert.equal(updates.at(-1).kind,'forecast');assert.equal(loading.at(-1),false);
el('daily-live').onclick();assert.equal(loading.at(-1),true);controls.clear();
assert.equal(loading.at(-1),false);assert.equal(frames.size,0);
assert.throws(()=>D.withOperational(history,{...forecast,model_version:'different-model'}),/correspondent/);
assert.throws(()=>D.withOperational(history,{...forecast,stations:['wrong-station']}),/correspondent/);
assert.throws(()=>D.withOperational(history,{...forecast,z:[[NaN],...[...forecast.z].slice(1)]}),/incomplète/);
console.log('LIVE/PREDICTION: date ranges, daily state, revised probabilities, provenance, stale data and model compatibility OK');
