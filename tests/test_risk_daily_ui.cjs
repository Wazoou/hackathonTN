// Integration of daily updates with the main map's layers, tooltips and camera.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const R=require('../dashboard/risk_component/risk_logic.js');
const elements=new Map();
const el=id=>{if(!elements.has(id))elements.set(id,{addEventListener(){}});return elements.get(id);};
const context=vm.createContext({document:{body:{dataset:{}},getElementById:el,querySelector:()=>null},RiskLogic:R,
 parent:{postMessage(){}},window:{addEventListener(){}},ResizeObserver:class{observe(){}},
 atob:s=>Buffer.from(s,'base64').toString('binary'),
 deck:{GeoJsonLayer:class{constructor(props){this.id=props.id;this.props=props;}},
       ScatterplotLayer:class{constructor(props){this.id=props.id;this.props=props;}}},
});
vm.runInContext(fs.readFileSync('dashboard/risk_component/app.js','utf8'),context);
const run=code=>vm.runInContext(code,context);
run(`
 dataset={layers:{score:'Score expert',p_feu:'Probabilité annuelle'},legends:{},
  department_names:{'33':'Gironde'},fire_history:{years:[2024],complete:false,departments:{'33':{annual_mean:10}}},
  department_boundaries:{features:[{properties:{code:'33'}}]},
  scores:{multiplicatif:[100,200]},probability_colors:[[1,2,3,255],[4,5,6,255]],
  colors:Array.from({length:1001},()=>[255,220,0,255]),
  features:[{_index:0,properties:{id:'a',dept:'33',p_feu:5}},{_index:1,properties:{id:'b',dept:'33',p_feu:20}}]};
 rows=new Map([['all',dataset.features],['33',dataset.features]]);
 deptNumbers=new Map([['33',0]]);
 view={longitude:2,latitude:46,zoom:6};selectedDept='33';loadCount=1;
 map={setProps:props=>{if(props.layers)renderedLayers=props.layers;}};
 let updates=0,controlsRendered=0;
 renderLayerControls=()=>controlsRendered++;
 update=()=>{renderLayers();updates++;};
 state.layer='p_feu';
`);
const originalFeatures=run('dataset.features'),originalView=run('view');
const pack=arr=>Buffer.from(new Float32Array(arr).buffer).toString('base64');
function apply(key,values,fires=[]){context.input={key,label:key,values:pack(values),fwi:pack(values.map(v=>v<0?-1:30)),fires,legend:[]};run('applyDaily(input)');}
assert.equal(run('stats("33").median'),12.5);
apply('2022-07-12',[10,-1],[[1,2,'33']]);
assert.equal(run('state.layer'),'p_jour');
assert.equal(run('stats("33").count'),1);
assert.equal(run('stats("33").median'),10);
assert.equal(run('stats("33").high'),1);
assert.match(run('departmentTooltipHTML("33")'),/10,0 départs.*100,0 % des mailles renseignées.*2022-07-12/s);
assert.equal(run('dataset.features'),originalFeatures);
assert.equal(run('view'),originalView);
assert.equal(run('selectedDept'),'33');
assert.equal(run('loadCount'),1);
assert.deepEqual(Array.from(run('renderedLayers.map(l=>l.id)')),
 ['department-picking','national-risk','department-highlights','department-outlines','daily-fires']);
assert.equal(run('renderedLayers.find(l=>l.id==="national-risk").props.opacity'),1);
assert.equal(run('colorsCache.get(layerKey())[7]'),255); // Missing data opaque gray.
assert.equal(run('stats("33","p_feu").median'),12.5);
apply('2022-07-13',[0,0]);
assert.equal(run('stats("33").count'),2);
assert.equal(run('stats("33").median'),0);
assert.equal(run('stats("33").high'),0);
assert.ok(!Array.from(run('renderedLayers.map(l=>l.id)')).includes('daily-fires'));
run("state.layer='p_feu'");apply('2022-07-14',[5,5]);
assert.equal(run('state.layer'),'p_feu'); // Date change does not override chosen static layer.
run("state.layer='p_jour'");apply('2022-07-15',[-1,-1]);
assert.equal(run('stats("33").count'),0);
assert.equal(run('stats("33").median'),null);
assert.match(run('departmentTooltipHTML("33")'),/Météo indisponible/);
context.input={key:'wrong',values:pack([5]),fwi:null};
assert.throws(()=>run('applyDaily(input)'),/incompatibles/);
run('applyDaily(null)');
assert.equal(run('state.layer'),'p_feu');
assert.ok(!run('dataset.layers.p_jour'));
assert.ok(!run('dataset.features[0].properties.p_jour'));
assert.equal(run('selectedDept'),'33');assert.equal(run('view'),originalView);
console.log('Daily UI: dates, layers, opaque cells, missing weather, tooltips, camera and selection preserved: OK');
