// node tests/test_fire_history_logic.cjs /tmp/fire-history-reference.json
const assert=require('node:assert/strict'),fs=require('node:fs');
const {summarize}=require('../dashboard/history_component/logic.js');
const key=p=>JSON.stringify([p.latitude,p.longitude,p.precision]);
const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
for(const {state,expected} of data.cases){
 const actual=summarize(data.records,state);
 for(const k of ['count','unmapped','approximate'])assert.equal(actual[k],expected[k],JSON.stringify(state));
 const points=new Map(actual.points.map(p=>[key(p),p]));assert.equal(points.size,expected.points.length);
 for(const p of expected.points){
  const q=points.get(key(p));assert.ok(q);
  for(const k of ['incident_count','locations'])assert.equal(q[k],p[k]);
  for(const k of ['burned_area_m2','radius_px'])assert.ok(Math.abs(q[k]-p[k])<1e-6);
 }
}
console.log(`${data.cases.length} selections match Python: counts, locations, surfaces, radii and precision.`);
