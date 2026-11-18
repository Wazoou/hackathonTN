const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements=new Map(),storage=new Map(),frames=new Map(),updates=[];
let next=0;
const el=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',open:false,replaceChildren(){},add(){}});return elements.get(id);};
const context=vm.createContext({document:{getElementById:el,body:{dataset:{}}},
 DailyLogic:require('../dashboard/risk_component/daily_logic.js'),Option:class{},
 performance:{now:()=>0},requestAnimationFrame:fn=>{frames.set(++next,fn);return next;},cancelAnimationFrame:id=>frames.delete(id),
 setTimeout:()=>1,clearTimeout(){},sessionStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)}});
vm.runInContext(fs.readFileSync('dashboard/risk_component/daily_controls.js','utf8'),context);
const controls=context.DailyControls({onDay:day=>updates.push(day)});
const model={dates:['2022-07-12','2022-07-13','2022-07-14'],stations:1,z:new Float32Array([0,1,2]),fwi:new Float32Array([10,20,30]),
 coefficient:1,commune_station:new Int32Array([0]),commune_terrain:new Float64Array([0]),cell_commune:new Int32Array([0]),cell_share:new Float64Array([1]),
 expected:new Float64Array([.5,.7,.9]),fires:{'2022-07-12':[[1,2,'33']]},bdiff_end:'2022-07-13',legend:[],meta:{meteo:{stations:1}}};
const flush=()=>{const callbacks=[...frames.values()];frames.clear();callbacks.forEach(fn=>fn());};
controls.install(model);
assert.equal(updates[0].key,'2022-07-14');
for(const value of ['1','2','0']){el('daily-slider').value=value;el('daily-slider').oninput();}
assert.equal(updates.length,1);assert.equal(frames.size,1);
flush();assert.equal(updates.length,2);assert.equal(updates[1].key,'2022-07-12');
assert.equal(el('daily-date').value,'2022-07-12');
el('daily-date').value='2022-07-13';el('daily-date').onchange();flush();
assert.equal(updates.at(-1).key,'2022-07-13');assert.equal(el('daily-slider').value,1);
el('daily-date').value='1900-01-01';el('daily-date').onchange();
assert.equal(el('daily-date').value,'2022-07-13');
controls.clear();controls.install(model);
assert.equal(updates.at(-1).key,'2022-07-13'); // Session persists when returning to the map.
el('daily-latest').onclick();flush();
assert.equal(updates.at(-1).key,'2022-07-14');
el('daily-slider').value='2';el('daily-slider').oninput();controls.clear();
assert.equal(frames.size,0);assert.equal(el('time-controls').hidden,true);
console.log('Native timeline: coalesced input, calendar, latest day and session persistence OK');
