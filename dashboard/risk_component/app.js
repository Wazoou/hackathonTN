'use strict';
const $=id=>document.getElementById(id), R=RiskLogic;
const send=(type,extra={})=>parent.postMessage({isStreamlitMessage:true,type,...extra},'*');
const state={dept:'all',layer:'score',mode:'multiplicatif',weight:12,opacity:.7};
let dataset=null,map=null,version=null,pending=null,frame=null,selected=null,view=null;
let rows=new Map(),bounds=new Map(),deptNumbers=new Map(),statsCache=new Map(),colorsCache=new Map();
let filterExtension=null,currentColors=null,loadCount=0;
const fmt=(n,d=0)=>Number(n).toLocaleString('fr-FR',{minimumFractionDigits:d,maximumFractionDigits:d});
const score=f=>dataset.scores[R.scoreKey(state)][f._index]/10;
const value=f=>R.value(f,state,dataset.scores);
const percent=v=>v==null?'Non disponible':`${fmt(v*100)} %`;
function fail(error){$('error').hidden=false;$('error').textContent=`La carte n’a pas pu être affichée : ${error.message||error}`;$('status').hidden=true;}
function viewBounds(b){
 const width=$('map').clientWidth,height=$('map').clientHeight;
 return new deck.WebMercatorViewport({width,height}).fitBounds([[b[0],b[1]],[b[2],b[3]]],{padding:40,maxZoom:12});
}
function fit(){
 if(!dataset||!map)return;
 const b=bounds.get(state.dept),v=viewBounds(b);
 view={longitude:v.longitude,latitude:v.latitude,zoom:v.zoom,pitch:0,bearing:0};
 document.body.dataset.view=JSON.stringify(view);
 map.setProps({initialViewState:view});
}
function featureHTML(f){
 const p=f.properties, v=value(f), e=R.escape;
 return `<b>${e(p.commune)} (${e(p.dept)}) · ${e(p.id)}</b><br>`+
 `<b>${e(dataset.layers[state.layer])} : ${fmt(v,state.layer==='p_feu'?2:1)}${state.layer==='p_feu'?' %/an':' / 100'}</b> (${R.riskClass(v,state.layer)})<br>`+
 `Score : ${fmt(score(f),1)} · combustible ${fmt(p.s_combustible,1)} · humain ${fmt(p.s_humain,1)}<br>`+
 `Forêt ${percent(p.foret_frac)} · résineux ${percent(p.resineux_frac)} · WUI ${percent(p.wui_frac)}<br>`+
 `Agriculture ${percent(p.agri_frac)} · routes pondérées ${p.route_ponderee_km==null?'Non disponible':fmt(p.route_ponderee_km,3)+' km'}<br>`+
 `Pente moyenne ${p.pente_moy_deg==null?'Non disponible':fmt(p.pente_moy_deg,3)+'°'}`+
 (p.p_feu==null?'':`<br>Estimation BDIFF : ${fmt(p.p_feu,2)} %/an`);
}
function colors(){
 const key=state.layer==='score'?R.scoreKey(state):state.layer;
 if(!colorsCache.has(key)){
  const array=new Uint8ClampedArray(dataset.features.length*4);
  for(const f of dataset.features){
   const s=R.scale(value(f),state.layer),c=state.layer==='p_feu'?dataset.probability_colors[f._index]:dataset.colors[Math.min(1000,Math.max(0,Math.round(s*10)))];
   array.set(c,f._index*4);
  }
  colorsCache.set(key,array);
 }
 currentColors=colorsCache.get(key);
 return key;
}
// Stable accessors and data references: changing opacity/filter does not rebuild geometry or colors.
const getColor=f=>currentColors.subarray(f._index*4,f._index*4+4);
const getFilter=f=>deptNumbers.get(f.properties.dept);
function layer(colorKey){
 const n=deptNumbers.get(state.dept),range=state.dept==='all'?[-1,999]:[n,n];
 return new deck.GeoJsonLayer({id:'national-risk',data:dataset.features,pickable:true,
  filled:true,stroked:true,getFillColor:getColor,getLineColor:[255,255,255,60],lineWidthMinPixels:.3,
  opacity:Math.pow(state.opacity,2.2),autoHighlight:true,highlightColor:[33,110,85,200],
  extensions:[filterExtension],getFilterValue:getFilter,filterRange:range,
  updateTriggers:{getFillColor:colorKey}});
}
function stats(){
 const key=`${state.dept}|${state.layer}|${state.layer==='score'?R.scoreKey(state):''}`;
 if(!statsCache.has(key)){
  if(statsCache.size>=64)statsCache.delete(statsCache.keys().next().value);
  statsCache.set(key,R.summary(rows.get(state.dept),state,dataset.scores));
 }
 return statsCache.get(key);
}
function updateRanking(s){
 $('value-title').textContent=dataset.layers[state.layer];
 const proba=!!dataset.layers.p_feu&&state.layer!=='p_feu';$('probability-title').hidden=!proba;
 $('top').replaceChildren();
 for(const f of s.top){
  const p=f.properties,tr=document.createElement('tr');
  for(const [i,text] of [p.id,p.commune,p.dept,fmt(value(f),state.layer==='p_feu'?2:1),fmt(score(f),1),fmt(p.s_combustible,1),fmt(p.s_humain,1),...(proba?[fmt(p.p_feu,2)]:[])].entries()){
   const td=document.createElement('td');
   if(i===0){const button=document.createElement('button');button.textContent=text;button.onclick=()=>{selected=f;$('selected').innerHTML=featureHTML(f);};td.append(button);}
   else td.textContent=text;tr.append(td);
  }
  $('top').append(tr);
 }
}
function updateMetadata(){
 const m=dataset.metadata[state.dept==='all'?dataset.departments[0]:state.dept]||{};
 const meta=state.dept==='all'?{...m,departement:'ensemble affiché',carreaux:dataset.features.length}:m;
 $('metadata').textContent=JSON.stringify(meta,null,2);
 $('exclusions').textContent=(m.indicateurs_exclus||[]).includes('tmja_max')?
  'Le trafic mesuré est exclu du score national faute de couverture suffisante. Les poids de pression humaine sont renormalisés sur l’habitat, les routes et l’agriculture.':'';
}
function controls(){
 $('modes').disabled=state.layer!=='score';$('weight').disabled=state.layer!=='score'||state.mode!=='additif';
 $('weight-value').textContent=`${state.weight*5} %`;$('opacity-value').textContent=`${Math.round(state.opacity*100)} %`;
}
function update(kind='layer'){
 if(!dataset||!map)return;
 const start=performance.now();
 const key=colors();
 map.setProps({layers:[layer(key)]});controls();
 // Opacity only updates a GPU uniform: no sort, statistics, ranking or Python rerun.
 if(kind!=='opacity'){
  const s=stats();$('count').textContent=fmt(s.count);$('median').textContent=fmt(s.median,state.layer==='p_feu'?1:0)+(state.layer==='p_feu'?' %':'');$('high').textContent=fmt(s.high*100,1)+' %';
  $('legend').replaceChildren();
  for(const [name,low,high,rgb] of dataset.legends[state.layer]){
   const span=document.createElement('span'),swatch=document.createElement('i');swatch.style.background=`rgb(${rgb})`;
   span.append(swatch,document.createTextNode(`${name} (${high?low+'–'+high:'≥ '+low})`));$('legend').append(span);
  }
  $('explanation').textContent=state.layer==='p_feu'?
   'Estimation annuelle BDIFF issue d’un modèle appris à l’échelle des communes, puis extrapolé aux mailles. Sans météo, elle ne décrit pas le risque d’un jour donné.':
   'Indice de sensibilité du terrain, relatif aux départements calculés ensemble. Végétation, relief et pression humaine ; sans météo, ce score n’est pas une probabilité.';
  if($('ranking').open)updateRanking(s);
  if(selected)$('selected').innerHTML=featureHTML(selected);
 }
 if(kind==='department'){
  selected=null;$('selected').textContent='Survolez une maille pour ses indicateurs, ou cliquez pour conserver sa fiche.';
  updateMetadata();fit();
 }
 document.body.dataset.updateMs=(performance.now()-start).toFixed(2);
 document.body.dataset.lastAction=kind;
 // Two animation frames include the actual GPU redraw, not just JS preparation.
 requestAnimationFrame(()=>requestAnimationFrame(()=>{document.body.dataset.frameMs=(performance.now()-start).toFixed(2);}));
 try{sessionStorage.setItem('risk-controls',JSON.stringify(state));}catch{}
}
let scheduledKind=null;
function schedule(kind){scheduledKind=kind;if(frame)return;frame=requestAnimationFrame(()=>{frame=null;update(scheduledKind);});}
function initialize(data){
 dataset=data;rows=new Map([['all',data.features]]);bounds=new Map();deptNumbers=new Map();statsCache.clear();colorsCache.clear();
 data.departments.forEach((d,i)=>{deptNumbers.set(d,i);rows.set(d,[]);});
 data.features.forEach((f,i)=>{
  f._index=i;rows.get(f.properties.dept).push(f);
  const polygons=f.geometry.type==='Polygon'?[f.geometry.coordinates]:f.geometry.coordinates;
  for(const d of ['all',f.properties.dept]){
   let b=bounds.get(d)||[Infinity,Infinity,-Infinity,-Infinity];
   for(const polygon of polygons)for(const [x,y] of polygon[0]){b[0]=Math.min(b[0],x);b[1]=Math.min(b[1],y);b[2]=Math.max(b[2],x);b[3]=Math.max(b[3],y);}
   bounds.set(d,b);
  }
 });
 if(data.layers.p_feu)state.layer='p_feu'; // couche par défaut quand le modèle BDIFF est fourni
 try{Object.assign(state,JSON.parse(sessionStorage.getItem('risk-controls')||'{}'));}catch{}
 if(!rows.has(state.dept))state.dept='all';if(!data.layers[state.layer])state.layer='score';
 if(!['multiplicatif','additif'].includes(state.mode))state.mode='multiplicatif';
 state.weight=Math.max(0,Math.min(20,Math.round(Number(state.weight)||0)));state.opacity=Math.max(.2,Math.min(1,Number(state.opacity)||.7));
 $('department').replaceChildren();
 for(const [v,label] of [['all','Tous les départements'],...data.departments.map(d=>[d,`${data.department_names[d]||'Département'} (${d})`])]){const o=new Option(label,v);$('department').add(o);}
 $('department').value=state.dept;$('department').disabled=false;
 $('layers').innerHTML='<legend>Couche affichée</legend>';
 for(const [v,label] of Object.entries(data.layers)){
  const l=document.createElement('label');l.className='choice';const input=document.createElement('input');input.type='radio';input.name='layer';input.value=v;input.checked=v===state.layer;
  input.onchange=()=>{state.layer=v;update('layer');};l.append(input,document.createTextNode(label));$('layers').append(l);
 }
 $('layers').disabled=false;$('opacity').disabled=false;$('opacity').value=Math.round(state.opacity*100);$('weight').value=state.weight;
 document.querySelectorAll('input[name=mode]').forEach(el=>{el.checked=el.value===state.mode;el.onchange=()=>{state.mode=el.value;update('mode');};});
 $('coverage').textContent=`${data.departments.length} départements · ${fmt(data.features.length)} mailles de 2 km · même référence pour tous les scores`;
 filterExtension=new deck.DataFilterExtension({filterSize:1});
 const initial=viewBounds(bounds.get(state.dept));
 view={longitude:initial.longitude,latitude:initial.latitude,zoom:initial.zoom,pitch:0,bearing:0};
 document.body.dataset.view=JSON.stringify(view);
 if(map)map.finalize();
 map=new deck.DeckGL({container:'map',map:maplibregl,mapStyle:'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
  initialViewState:view,controller:true,
  onViewStateChange:({viewState})=>{view=viewState;document.body.dataset.view=JSON.stringify({longitude:view.longitude,latitude:view.latitude,zoom:view.zoom});},
  getTooltip:({object})=>object?{html:featureHTML(object),style:{backgroundColor:'white',color:'#253747',fontSize:'12px',maxWidth:'360px'}}:null,
  onClick:({object})=>{if(object){selected=object;$('selected').innerHTML=featureHTML(object);}},
  onError:fail});
 updateMetadata();update();$('status').hidden=true;document.body.dataset.ready='true';document.body.dataset.loadCount=String(++loadCount);
}
$('department').onchange=()=>{state.dept=$('department').value;update('department');};
$('opacity').oninput=()=>{state.opacity=Number($('opacity').value)/100;schedule('opacity');};
$('weight').oninput=()=>{state.weight=Number($('weight').value);schedule('weight');};
$('fit').onclick=fit;
for(const [id,delta] of [['zoom-in',1],['zoom-out',-1]])$(id).onclick=()=>{if(map){view={...view,zoom:Math.max(0,Math.min(18,view.zoom+delta))};document.body.dataset.view=JSON.stringify(view);map.setProps({initialViewState:view});}};
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('map').requestFullscreen();}catch(e){fail(e);}};
$('ranking').ontoggle=()=>{if(dataset&&$('ranking').open)updateRanking(stats());};
window.addEventListener('message',async event=>{
 if(event.source!==parent||event.data.type!=='streamlit:render')return;
 const args=event.data.args;if(args.version===version||args.version===pending)return;
 pending=args.version;$('status').hidden=false;$('error').hidden=true;
 try{
  const bytes=Uint8Array.from(atob(args.payload),c=>c.charCodeAt(0));
  const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  const data=JSON.parse(await new Response(stream).text());
  if(pending!==args.version)return;
  initialize(data);version=args.version;pending=null;
 }catch(e){pending=null;fail(e);}
});
new ResizeObserver(()=>send('streamlit:setFrameHeight',{height:document.body.scrollHeight+8})).observe(document.body);
send('streamlit:componentReady',{apiVersion:1});send('streamlit:setFrameHeight',{height:900});
