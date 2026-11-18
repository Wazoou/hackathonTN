// node tests/test_live_logic.cjs /tmp/pyro-daily-reference
const fs=require('node:fs'),assert=require('node:assert/strict');
const D=require('../dashboard/risk_component/daily_logic.js');
const dir=process.argv[2],file=fs.readFileSync(dir+'/weather.bin');
const history=D.unpack(file.buffer.slice(file.byteOffset,file.byteOffset+file.byteLength));
const operational=JSON.parse(fs.readFileSync(dir+'/operational.json','utf8'));
const data=D.withOperational(history,operational);
const references=JSON.parse(fs.readFileSync(dir+'/live-reference.json','utf8'));
for(const reference of references){
 const actual=D.computeDay(data,data.dates.indexOf(reference.key));
 for(const name of ['values','fwi']){
  const bytes=fs.readFileSync(`${dir}/${reference.key}-${name}.bin`),expected=new Float32Array(bytes.buffer,bytes.byteOffset,bytes.byteLength/4);
  assert.equal(actual[name].length,expected.length);
  for(let i=0;i<expected.length;i++)assert.ok(Math.abs(actual[name][i]-expected[i])<=Math.max(2e-6,Math.abs(expected[i])*2e-7),`${reference.key} ${name} ${i}`);
 }
 assert.ok(Math.abs(actual.expected-reference.expected)<1e-4);
 assert.equal(actual.known,false);assert.equal(actual.fires.length,0);
}
console.log(`${references.length} real LIVE/forecast days × ${data.cell_commune.length} cells match Python, without altering historical dates`);
