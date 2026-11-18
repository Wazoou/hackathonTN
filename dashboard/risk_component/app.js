'use strict';
const $=id=>document.getElementById(id), R=RiskLogic;
const send=(type,extra={})=>parent.postMessage({isStreamlitMessage:true,type,...extra},'*');
const state={dept:'all',layer:'score',mode:'multiplicatif',weight:12};
let dataset=null,map=null,version=null,pending=null,frame=null,view=null,selectedDept=null,hoveredDept=null;
const CELL_DETAILS_ZOOM=7;
let cameraFrame=null;
let rows=new Map(),bounds=new Map(),deptNumbers=new Map(),statsCache=new Map(),colorsCache=new Map();
let filterExtension=null,currentColors=null,renderedLayers=[],loadCount=0;
const indicatorKeys=['s_combustible','s_humain','foret_frac','resineux_frac','wui_frac','route_ponderee_km'];
let nationalIndicators={},indicatorCache=new Map();
const fmt=(n,d=0)=>Number(n).toLocaleString('fr-FR',{minimumFractionDigits:d,maximumFractionDigits:d});
const score=f=>dataset.scores[R.scoreKey(state)][f._index]/10;
const value=f=>R.value(f,state,dataset.scores);
const percent=v=>v==null?'Non disponible':`${fmt(v*100)} %`;
function fail(error){$('error').hidden=false;$('error').textContent=`La carte n’a pas pu être affichée : ${error.message||error}`;$('status').hidden=true;}
function viewBounds(b){
 const width=$('map').clientWidth,height=$('map').clientHeight;
 return new deck.WebMercatorViewport({width,height}).fitBounds([[b[0],b[1]],[b[2],b[3]]],{padding:40,maxZoom:12});
}
function setView(next){
 const zoomChanged=view?.zoom!==next.zoom;
 view=next;
 document.body.dataset.view=JSON.stringify(view);
 document.body.dataset.detailMode=view.zoom>=CELL_DETAILS_ZOOM?'cells':'departments';
 // Keep the camera controlled: reapplying initialViewState is ignored when its
 // values match the previous reset, even after the user has panned or zoomed.
 if(map){
  // Only the 96 outlines change with zoom; retain the national risk layer.
  if(zoomChanged&&renderedLayers.length){
   renderedLayers=renderedLayers.map(current=>current.id==='department-outlines'?departmentLayers(true):current);
   map.setProps({viewState:view,layers:renderedLayers});
  }else map.setProps({viewState:view});
 }
}
function cancelCameraAnimation(){
 if(cameraFrame!==null)cancelAnimationFrame(cameraFrame);
 cameraFrame=null;
}
function animateView(target){
 cancelCameraAnimation();
 if(!view||window.matchMedia('(prefers-reduced-motion: reduce)').matches){setView(target);return;}
 const start={...view},started=performance.now(),duration=800;
 const tick=now=>{
  const progress=Math.min(1,(now-started)/duration);
  const eased=progress<.5?4*progress**3:1-(-2*progress+2)**3/2;
  const next={...target};
  for(const key of ['longitude','latitude','zoom','pitch','bearing']){
   next[key]=(start[key]??0)+((target[key]??0)-(start[key]??0))*eased;
  }
  setView(next);
  cameraFrame=progress<1?requestAnimationFrame(tick):null;
 };
 cameraFrame=requestAnimationFrame(tick);
}
function fit(dept=state.dept){
 if(!dataset||!map)return;
 const b=bounds.get(dept),v=viewBounds(b);
 animateView({longitude:v.longitude,latitude:v.latitude,zoom:v.zoom,pitch:0,bearing:0});
}
function manualView(next){cancelCameraAnimation();setView(next);}
function hoveredDepartment(object){
 return object?(object.properties.dept||object.properties.code||null):null;
}
function tooltipFor({object}){
 const dept=hoveredDepartment(object);
 if(!dept)return null;
 const html=view?.zoom>=CELL_DETAILS_ZOOM&&!object.properties.code?featureHTML(object)
  :departmentTooltipHTML(dept);
 return {html,style:{backgroundColor:'white',color:'#253747',fontSize:'12px',maxWidth:'360px'}};
}
function departmentTooltipHTML(dept){
 const history=dataset.fire_history,years=history?.years||[];
 const observed=history?.departments[dept];
 const annual=years.length?`${fmt(observed?.annual_mean??0,1)} départs de feu par an en moyenne`:'Historique BDIFF indisponible';
 const period=history?.complete?'2006–2024':years.join(', ');
 const riskLayer=dataset.layers.p_feu?'p_feu':'score',s=stats(dept,riskLayer);
 return `<strong>${R.escape(dataset.department_names[dept]||dept)} (${R.escape(dept)})</strong><br>`+
  `<b>${annual}</b><br>`+
  (years.length?`<span style="font-size:11px">Historique BDIFF ${R.escape(period)}${history.complete?'':' · couverture partielle'}</span><br>`:'')+
  `<b>${fmt(s.high*100,1)} % des mailles</b> à risque élevé ou très élevé<br>`+
  `<span style="font-size:11px">${riskLayer==='p_feu'?'Modèle BDIFF · sans météo du jour':'Score expert · sans météo du jour'}</span>`;
}
function hoverMap({object}){
 const dept=hoveredDepartment(object);
 if(dept!==hoveredDept){hoveredDept=dept;updateDepartmentHighlight();}
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
// Stable accessors and data references: changing filters does not rebuild geometry or colors.
const getColor=f=>currentColors.subarray(f._index*4,f._index*4+4);
const getFilter=f=>deptNumbers.get(f.properties.dept);
function layer(colorKey){
 const n=deptNumbers.get(state.dept),range=state.dept==='all'?[-1,999]:[n,n];
 return new deck.GeoJsonLayer({id:'national-risk',data:dataset.features,pickable:true,
  filled:true,stroked:true,getFillColor:getColor,getLineColor:[255,255,255,60],lineWidthMinPixels:.3,
  opacity:1,autoHighlight:true,highlightColor:[33,110,85,200],
  extensions:[filterExtension],getFilterValue:getFilter,filterRange:range,
  updateTriggers:{getFillColor:colorKey}});
}
function departmentLayers(outline=false){
 // Fade national boundaries progressively; keep the selected department distinct.
 const detail=Math.max(0,Math.min(1,((view?.zoom??5.5)-5.5)/3.5));
 const alpha=Math.round(55+135*detail),width=.45+.55*detail;
 return new deck.GeoJsonLayer({id:outline?'department-outlines':'department-picking',
  data:dataset.department_boundaries.features,pickable:!outline,
  filled:!outline,stroked:outline,getFillColor:[0,0,0,0],
  getLineColor:f=>f.properties.code===selectedDept?[210,35,35,255]:[45,64,79,alpha],
  getLineWidth:f=>f.properties.code===selectedDept?3:width,lineWidthUnits:'pixels',
  parameters:{depthTest:false},updateTriggers:{getLineColor:[selectedDept,alpha],getLineWidth:[selectedDept,width]}});
}
function departmentHighlightLayer(){
 return new deck.GeoJsonLayer({id:'department-highlights',
  data:dataset.department_boundaries.features,pickable:false,filled:true,stroked:false,
  getFillColor:f=>f.properties.code===selectedDept?[230,35,35,75]:
   f.properties.code===hoveredDept?[30,110,255,70]:[0,0,0,0],
  parameters:{depthTest:false},updateTriggers:{getFillColor:[selectedDept,hoveredDept]}});
}
function updateDepartmentHighlight(){
 if(!map||!renderedLayers.length)return;
 renderedLayers=renderedLayers.map(current=>current.id==='department-highlights'?departmentHighlightLayer():current);
 map.setProps({layers:renderedLayers});
}
function renderLayers(){
 renderedLayers=[departmentLayers(),layer(colors()),departmentHighlightLayer(),departmentLayers(true)];
 map.setProps({layers:renderedLayers});
}
function stats(dept=state.dept,layer=state.layer){
 const selection={...state,layer};
 const key=`${dept}|${layer}|${layer==='score'?R.scoreKey(selection):''}`;
 if(!statsCache.has(key)){
  if(statsCache.size>=64)statsCache.delete(statsCache.keys().next().value);
  statsCache.set(key,R.summary(rows.get(dept),selection,dataset.scores));
 }
 return statsCache.get(key);
}
function meanIndicators(features){
 const totals=Object.fromEntries(indicatorKeys.map(key=>[key,{sum:0,count:0}]));
 for(const feature of features)for(const key of indicatorKeys){
  const value=feature.properties[key];
  if(typeof value==='number'&&Number.isFinite(value)){
   totals[key].sum+=value;totals[key].count++;
  }
 }
 return Object.fromEntries(indicatorKeys.map(key=>[
  key,totals[key].count?totals[key].sum/totals[key].count:null
 ]));
}
function departmentInsightsHTML(dept){
 if(!indicatorCache.has(dept))indicatorCache.set(dept,meanIndicators(rows.get(dept)||[]));
 const indicators=indicatorCache.get(dept),factors=[],advice=[];
 const forestHigh=indicators.foret_frac!==null&&nationalIndicators.foret_frac!==null&&indicators.foret_frac>=nationalIndicators.foret_frac+.1;
 const coniferHigh=indicators.resineux_frac!==null&&nationalIndicators.resineux_frac!==null&&indicators.resineux_frac>=nationalIndicators.resineux_frac+.05;
 const wuiHigh=indicators.wui_frac!==null&&nationalIndicators.wui_frac!==null&&indicators.wui_frac>=Math.max(.02,nationalIndicators.wui_frac*1.5);
 const roadsHigh=indicators.route_ponderee_km!==null&&nationalIndicators.route_ponderee_km!==null&&indicators.route_ponderee_km>=Math.max(.25,nationalIndicators.route_ponderee_km*1.25);
 if(forestHigh)factors.push(`Couverture forestière moyenne élevée : ${fmt(indicators.foret_frac*100,1)} % contre ${fmt(nationalIndicators.foret_frac*100,1)} % en France.`);
 if(coniferHigh)factors.push(`Part de résineux moyenne élevée : ${fmt(indicators.resineux_frac*100,1)} % contre ${fmt(nationalIndicators.resineux_frac*100,1)} % en France.`);
 if(wuiHigh)factors.push(`Davantage d’habitations proches de végétation (interface habitat-forêt) : ${fmt(indicators.wui_frac*100,1)} % contre ${fmt(nationalIndicators.wui_frac*100,1)} % en France.`);
 if(roadsHigh)factors.push(`Présence de routes pondérées plus importante : ${fmt(indicators.route_ponderee_km,2)} km par maille en moyenne contre ${fmt(nationalIndicators.route_ponderee_km,2)} km en France.`);
 if(indicators.s_combustible!==null&&nationalIndicators.s_combustible!==null&&indicators.s_combustible>=nationalIndicators.s_combustible+5&&!forestHigh&&!coniferHigh)
  factors.push(`Le sous-score combustible moyen dépasse la moyenne nationale (${fmt(indicators.s_combustible,1)} contre ${fmt(nationalIndicators.s_combustible,1)} / 100) ; les lisières et le relief contribuent aussi au calcul.`);
 if(indicators.s_humain!==null&&nationalIndicators.s_humain!==null&&indicators.s_humain>=nationalIndicators.s_humain+5&&!wuiHigh&&!roadsHigh)
  factors.push(`Le sous-score de pression humaine moyen dépasse la moyenne nationale (${fmt(indicators.s_humain,1)} contre ${fmt(nationalIndicators.s_humain,1)} / 100) ; plusieurs indicateurs humains entrent dans le calcul.`);
 if(forestHigh||coniferHigh)advice.push('Près des bois, éviter mégots, brûlages et feux en plein air ; vérifier les restrictions locales avant un barbecue.');
 if(wuiHigh)advice.push('Près des habitations bordées de végétation, éloigner les barbecues des plantes et respecter les interdictions en période à risque.');
 if(roadsHigh)advice.push('Aux abords des routes, ne pas jeter de mégots et éviter de stationner ou d’utiliser des outils chauds dans l’herbe sèche.');
 if(!factors.length)factors.push('Forêt, résineux, routes et interface habitat-végétation ne dépassent pas nettement leurs références nationales.');
 if(!advice.length)advice.push('Rester vigilant près de la végétation et respecter les consignes locales de prévention.');
 const e=R.escape;
 const scoreText=(value,reference)=>value===null?'non disponible':
  fmt(value,1)+' / 100'+(reference===null?'':` (France : ${fmt(reference,1)})`);
 return '<div class="department-insights" style="border-top:1px solid var(--line);margin-top:10px;padding-top:10px">'+
  `<p><strong>Sous-scores moyens</strong> — combustible : ${scoreText(indicators.s_combustible,nationalIndicators.s_combustible)} ; pression humaine : ${scoreText(indicators.s_humain,nationalIndicators.s_humain)}.</p>`+
  '<strong>Facteurs qui peuvent augmenter la sensibilité</strong><ul style="margin:5px 0 10px;padding-left:18px">'+
  factors.map(item=>`<li>${e(item)}</li>`).join('')+
  '</ul><strong>Conseils de vigilance</strong><ul style="margin:5px 0 10px;padding-left:18px">'+
  advice.map(item=>`<li>${e(item)}</li>`).join('')+
  '</ul><span class="muted">Comparaison aux moyennes des mailles nationales ; cela décrit la sensibilité du terrain, pas le risque du jour.</span></div>';
}
function departmentHTML(dept){
 const s=stats(dept),e=R.escape,unit=state.layer==='p_feu'?' %/an':' / 100';
 return `<strong>${e(dataset.department_names[dept]||dept)} (${e(dept)})</strong><br>`+
  `${fmt(s.count)} mailles de 2 km<br>`+
  `${e(dataset.layers[state.layer])} : médiane <b>${fmt(s.median,state.layer==='p_feu'?2:1)}${unit}</b><br>`+
  `Mailles en classe élevée ou plus : <b>${fmt(s.high*100,1)} %</b><br>`+
  '<span class="muted">Synthèse des mailles du département, sans météo du jour.</span>';
}
function updateDepartmentDetails(){
 $('department-details').hidden=!selectedDept;
 if(selectedDept)$('department-summary').innerHTML=departmentHTML(selectedDept)+departmentInsightsHTML(selectedDept);
}
function selectDepartment(dept){
 if(!rows.has(dept))return;
 const alreadyDetailed=selectedDept===dept&&view?.zoom>=CELL_DETAILS_ZOOM;
 selectedDept=dept;updateDepartmentDetails();renderLayers();
 if(!alreadyDetailed)fit(dept);
}
function controls(){
 $('modes').disabled=state.layer!=='score';$('weight').disabled=state.layer!=='score'||state.mode!=='additif';
 $('weight-value').textContent=`${state.weight*5} %`;
}
function update(kind='layer'){
 if(!dataset||!map)return;
 const start=performance.now();
 if(kind==='department'){
  selectedDept=state.dept==='all'?null:state.dept;
 }
 renderLayers();controls();
 $('legend').replaceChildren();
 for(const [name,low,high,rgb] of dataset.legends[state.layer]){
  const span=document.createElement('span'),swatch=document.createElement('i');swatch.style.background=`rgb(${rgb})`;
  span.append(swatch,document.createTextNode(`${name} (${high?low+'–'+high:'≥ '+low})`));$('legend').append(span);
 }
 $('explanation').textContent=state.layer==='p_feu'?''
  :'Indice de sensibilité du terrain, relatif aux départements calculés ensemble. Végétation, relief et pression humaine ; sans météo, ce score n’est pas une probabilité.';
 updateDepartmentDetails();
 if(kind==='department'){
  fit();
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
 nationalIndicators=meanIndicators(data.features);indicatorCache.clear();
 cancelCameraAnimation();
 selectedDept=null;hoveredDept=null;renderedLayers=[];
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
 selectedDept=state.dept==='all'?null:state.dept;
 if(!['multiplicatif','additif'].includes(state.mode))state.mode='multiplicatif';
 state.weight=Math.max(0,Math.min(20,Math.round(Number(state.weight)||0)));
 $('department').replaceChildren();
 for(const [v,label] of [['all','Tous les départements'],...data.departments.map(d=>[d,`${data.department_names[d]||'Département'} (${d})`])]){const o=new Option(label,v);$('department').add(o);}
 $('department').value=state.dept;$('department').disabled=false;
 $('layers').innerHTML='<legend>Couche affichée</legend>';
 for(const [v,label] of Object.entries(data.layers)){
  const l=document.createElement('label');l.className='choice';const input=document.createElement('input');input.type='radio';input.name='layer';input.value=v;input.checked=v===state.layer;
  input.onchange=()=>{state.layer=v;update('layer');};l.append(input,document.createTextNode(label));$('layers').append(l);
 }
 $('layers').disabled=false;$('weight').value=state.weight;
 document.querySelectorAll('input[name=mode]').forEach(el=>{el.checked=el.value===state.mode;el.onchange=()=>{state.mode=el.value;update('mode');};});
 filterExtension=new deck.DataFilterExtension({filterSize:1});
 const initial=viewBounds(bounds.get(state.dept));
 view={longitude:initial.longitude,latitude:initial.latitude,zoom:initial.zoom,pitch:0,bearing:0};
 document.body.dataset.view=JSON.stringify(view);
 if(map)map.finalize();
 map=new deck.DeckGL({container:'map',map:maplibregl,mapStyle:{
  version:8,
  sources:{openstreetmap:{type:'raster',
   tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,
   attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'}},
  layers:[{id:'openstreetmap-raster',type:'raster',source:'openstreetmap'}]},
  viewState:view,controller:true,
  onViewStateChange:({viewState})=>manualView(viewState),
  getTooltip:tooltipFor,
  onHover:hoverMap,
  onClick:({object})=>{if(object){
   selectDepartment(object.properties.dept||object.properties.code);
  }},
  onError:fail});
 update();$('status').hidden=true;document.body.dataset.ready='true';document.body.dataset.loadCount=String(++loadCount);
}
$('department').onchange=()=>{state.dept=$('department').value;update('department');};
$('explore-department').onclick=()=>{if(selectedDept){state.dept=selectedDept;$('department').value=state.dept;update('department');}};
$('weight').oninput=()=>{state.weight=Number($('weight').value);schedule('weight');};
$('fit').onclick=()=>fit();
// Direct manipulation interrupts the flight immediately.
for(const event of ['pointerdown','wheel'])$('map').addEventListener(event,cancelCameraAnimation,{passive:true});
for(const [id,delta] of [['zoom-in',1],['zoom-out',-1]])$(id).onclick=()=>{if(map)animateView({...view,zoom:Math.max(0,Math.min(18,view.zoom+delta))});};
$('fullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('map').requestFullscreen();}catch(e){fail(e);}};
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
