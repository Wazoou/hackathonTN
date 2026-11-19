// Run with node tests/test_risk_focus.cjs. Exercise the real map handlers.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map(), listeners = {}, frames = new Map();
let now=0, nextFrame=0, reducedMotion=false;
const context=vm.createContext({
 document:{body:{dataset:{}},getElementById:id=>{
  if(!elements.has(id))elements.set(id,{addEventListener:(event,fn)=>{listeners[id+':'+event]=fn;}});
  return elements.get(id);
 }},
 parent:{postMessage(){}},window:{addEventListener(){},matchMedia:()=>({matches:reducedMotion})},
 ResizeObserver:class{observe(){}},performance:{now:()=>now},
 requestAnimationFrame:fn=>{frames.set(++nextFrame,fn);return nextFrame;},
 cancelAnimationFrame:id=>frames.delete(id),
 RiskLogic:{escape:text=>text.replaceAll('&','&amp;').replaceAll('<','&lt;')},
});
vm.runInContext(fs.readFileSync('dashboard/risk_component/app.js','utf8'),context);
const run=code=>vm.runInContext(code,context);
const advance=ms=>{now+=ms;const callbacks=[...frames.values()];frames.clear();callbacks.forEach(fn=>fn(now));};
run(`
 dataset={department_names:{'33':'Gironde','40':'Landes'},layers:{score:'Indice de sensibilité territoriale',p_feu:'Probabilité annuelle d’incendie'}};
 stats=()=>({high:.152});
 dataset.fire_history={years:Array.from({length:19},(_,i)=>2006+i),complete:true,departments:{'33':{annual_mean:100.5}}};
 rows=new Map([['33',[]],['40',[]]]);
 map={setProps(){}};
 let details=0;
 updateDepartmentDetails=()=>details++;
 renderLayers=()=>{};updateDepartmentHighlight=()=>{};
 featureHTML=f=>'<b>Indicateurs '+f.properties.dept+'</b>';
 viewBounds=()=>({longitude:-.5,latitude:45,zoom:8});
 const cell={properties:{dept:'33'}},other={properties:{dept:'40'}};
 setView({longitude:2,latitude:46,zoom:5,pitch:0,bearing:0});
`);
assert.match(run('tooltipFor({object:cell}).html'),/Gironde \(33\).*100,5 départs de feu par an.*2006–2024.*15,2 % des mailles/s);
run("selectDepartment('33')");
assert.equal(run('details'),1);
assert.equal(run('view.zoom'),5); // Flight is asynchronous, not a jump.
advance(400);
assert.equal(run('view.zoom'),6.5);
assert.match(run('tooltipFor({object:cell}).html'),/Gironde \(33\).*100,5 départs de feu par an.*2006–2024.*15,2 % des mailles/s);
advance(200);
assert.ok(run('view.zoom')>7);
assert.match(run('tooltipFor({object:cell}).html'),/Indicateurs 33/);
advance(200);
assert.equal(run('view.zoom'),8);
assert.equal(frames.size,0);
// Crossing a department border, or leaving/re-entering the map, keeps details.
run('hoverMap({object:other});hoverMap({object:null});hoverMap({object:other})');
assert.match(run('tooltipFor({object:other}).html'),/Indicateurs 40/);
assert.equal(run('selectedDept'),'33');
run('manualView({...view,zoom:6.99})');
assert.match(run('tooltipFor({object:cell}).html'),/Gironde \(33\).*100,5 départs de feu par an.*2006–2024.*15,2 % des mailles/s);
run('manualView({...view,zoom:7})');
assert.match(run('tooltipFor({object:other}).html'),/Indicateurs/);
assert.match(run('tooltipFor({object:{properties:{code:"40"}}}).html'),/Landes \(40\).*0,0 départs/s);
assert.equal(run('tooltipFor({object:null})'),null);
// New flights and direct interaction cancel pending animation frames.
run('animateView({...view,zoom:10})');advance(100);
run('animateView({...view,zoom:9})');
assert.equal(frames.size,1);
run('manualView({...view,zoom:6})');advance(1000);
assert.equal(run('view.zoom'),6);
assert.equal(frames.size,0);
run('animateView({...view,zoom:10})');listeners['map:wheel']();
assert.equal(frames.size,0);
run('animateView({...view,zoom:10})');listeners['map:pointerdown']();
assert.equal(frames.size,0);
reducedMotion=true;run('animateView({...view,zoom:8})');
assert.equal(run('view.zoom'),8);
assert.equal(frames.size,0);
assert.equal(run('document.body.dataset.detailMode'),'cells');
console.log('Zoom threshold, cross-department details, smooth flight, interruption and reduced motion: OK');

run("state.layer='p_feu';manualView({...view,zoom:6})");
assert.match(run('tooltipFor({object:cell}).html'),/Modèle BDIFF/);
run('dataset.fire_history={years:[],departments:{}}');
assert.match(run('tooltipFor({object:cell}).html'),/Historique BDIFF indisponible/);
run('dataset.fire_history={years:[2024],complete:false,departments:{}}');
assert.match(run('tooltipFor({object:cell}).html'),/couverture partielle/);
