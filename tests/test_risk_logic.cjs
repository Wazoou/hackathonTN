// Run with Node.js: node tests/test_risk_logic.cjs
// Optional exhaustive validation: append payload.json.gz and Python-reference.json.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const zlib = require('node:zlib');
const R = require('../dashboard/risk_component/risk_logic.js');
assert.equal(R.scale(7.5,'p_feu'),50);
assert.equal(R.riskClass(10,'p_feu'),'Élevé');
assert.equal(R.riskClass(60,'score'),'Élevé');
assert.equal(R.escape('<script>'),'&lt;script&gt;');
// Ties must preserve file order, including the 15th place, as pandas.nlargest does.
const features = Array.from({length:40},(_,i)=>({_index:i,properties:{id:String(i),s_combustible:i%4*20}}));
const scores={multiplicatif:features.map(f=>f.properties.s_combustible*10)};
const state={layer:'score',mode:'multiplicatif',weight:12};
const actual=R.summary(features,state,scores);
const expected=features.slice().sort((a,b)=>b.properties.s_combustible-a.properties.s_combustible||a._index-b._index).slice(0,15);
assert.equal(JSON.stringify(actual.top.map(f=>f._index)),JSON.stringify(expected.map(f=>f._index)));
assert.equal(actual.mean,30);assert.equal(actual.median,30);assert.equal(actual.high,.25);
assert.equal(R.summary([],state,scores).count,0);
assert.equal(R.summary([],state,scores).mean,null);
const unequal=[1,2,9].map((v,i)=>({_index:i,properties:{p_feu:v}}));
assert.equal(R.summary(unequal,{layer:"p_feu"},{}).mean,4);
assert.equal(R.summary(unequal,{layer:"p_feu"},{}).median,2);
if(process.argv[2]){
 const data=JSON.parse(zlib.gunzipSync(fs.readFileSync(process.argv[2])));
 const reference=JSON.parse(fs.readFileSync(process.argv[3]));
 const groups=new Map([['all',data.features]]);
 for(const d of data.departments)groups.set(d,[]);
 data.features.forEach((f,i)=>{f._index=i;groups.get(f.properties.dept).push(f);});
 for(const e of reference){
  const a=R.summary(groups.get(e.state.dept),e.state,data.scores);
  assert.equal(a.count,e.count);assert.equal(a.median,e.median);assert.equal(a.high,e.high);
  assert.equal(JSON.stringify(a.top.map(f=>f.properties.id)),JSON.stringify(e.top));
 }
 console.log(`${reference.length} configurations identiques à Python sur ${data.features.length} mailles`);
}
console.log('Tests JS : classes, probabilités, médiane, classement, ex aequo, vide et échappement OK');
