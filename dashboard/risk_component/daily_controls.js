/* Calendar, slider, observed fires and comparison chart stay entirely in this iframe. */
function DailyControls({onDay,onLoading=()=>{}}){
 const el=id=>document.getElementById(id),format=key=>key.split('-').reverse().join('/');
 const number=n=>n.toLocaleString('fr-FR',{minimumFractionDigits:1,maximumFractionDigits:1});
 const parisDate=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Paris',year:'numeric',month:'2-digit',day:'2-digit'});
 let data=null,index=0,requested=0,frame=null,chartTimer=null,cache=new Map(),mode='archives',available=[],manifest=null,activate=false,displayedToday=null;
 let switching=false,settleFrame=null,loadingVersion=0;
 let rangeCache=null;
 function stopLoading(){
  if(settleFrame!==null)cancelAnimationFrame(settleFrame);settleFrame=null;
  loadingVersion++;
  if(switching){switching=false;onLoading(false);}
 }
 function today(){return parisDate.format(new Date());}
 function ranges(which){
  const boundary=today();
  if(!rangeCache||rangeCache.data!==data||rangeCache.today!==boundary){
   rangeCache={data,today:boundary,archives:[],live:[],forecast:[]};
   data.dates.forEach((key,i)=>rangeCache[key<boundary?'archives':key===boundary?'live':'forecast'].push(i));
  }
  return rangeCache[which];
 }
 function configure(previous){
  if(!data)return;
  displayedToday=today();
  for(const name of ['archives','live','forecast']){
   const button=el('daily-'+name);button.disabled=!ranges(name).length;
   button.setAttribute?.('aria-pressed',String(name===mode));
  }
  available=ranges(mode);
  if(!available.length){mode='archives';available=ranges(mode);}
  if(!available.length)return;
  const position=data.dates.indexOf(previous);
  index=available.includes(position)?position:(mode==='forecast'?available[0]:available.at(-1));requested=index;
  el('daily-slider').max=available.length-1;el('daily-slider').disabled=available.length===1;
  el('daily-date').min=data.dates[available[0]];el('daily-date').max=data.dates[available.at(-1)];
  el('daily-date').disabled=mode==='live';el('daily-latest').hidden=mode==='live';
  el('daily-first').textContent=format(data.dates[available[0]]);el('daily-last').textContent=format(data.dates[available.at(-1)]);
  for(const name of ['archives','live','forecast'])el('daily-'+name).setAttribute?.('aria-pressed',String(name===mode));
  labels();
 }
 function selectMode(next){
  if(!data||next===mode||!ranges(next).length)return;
  switching=true;onLoading(true);
  mode=next;activate=true;try{sessionStorage.setItem('risk-weather-mode',mode);}catch{}
  let previous;try{previous=sessionStorage.getItem('risk-weather-date-'+mode);}catch{}
  configure(previous);choose(index);
 }
 for(const name of ['archives','live','forecast'])el('daily-'+name).onclick=()=>selectMode(name);
 function status(){
  const line=el('daily-live-status');
  if(!manifest){line.textContent='LIVE et PRÉDICTION : attente du collecteur météo.';return;}
  const time=key=>key?new Date(key).toLocaleString('fr-FR',{timeZone:'Europe/Paris',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'indisponible';
  const age=manifest.retrieved_at?Date.now()-Date.parse(manifest.retrieved_at):Infinity;
  line.textContent=`Open-Meteo · météo modélisée · collecte ${time(manifest.retrieved_at)} · prochaine vérification ${time(manifest.next_check)}.`+
   (manifest.error?' Collecte interrompue : dernière carte conservée. '+manifest.error:age>3*3600000?' Données anciennes : actualisation en attente.':'');
  line.setAttribute?.('data-stale',String(age>3*3600000||!!manifest.error));
 }
 function labels(){
  const key=data.dates[requested];el('daily-date').value=key;el('daily-slider').value=available.indexOf(requested);el('daily-date-label').textContent=format(key);
 }
 function choose(next){
  if(!data)return;
  if(!available.includes(next))return;requested=next;labels();
  if(switching){loadingVersion++;if(settleFrame!==null)cancelAnimationFrame(settleFrame);settleFrame=null;}
  // Paint the veil before the synchronous calculation, without adding a timer.
  if(frame===null)frame=requestAnimationFrame(switching?()=>{frame=requestAnimationFrame(render);}:render);
 }
 function render(){
  frame=null;index=requested;const start=performance.now();
  const currentLoading=loadingVersion;
  try{
  if(!cache.has(index)){
   if(cache.size>=12)cache.delete(cache.keys().next().value);
   cache.set(index,DailyLogic.computeDay(data,index));
  }
  const day=cache.get(index);
  onDay({...day,kind:day.provenance?(mode==='live'?'live':mode==='forecast'?'forecast':'archive'):'observed',activate});activate=false;
  const trainingEnd=data.meta.bdiff?.fin?.slice(0,4);
  el('daily-validation').textContent=`Modèle entraîné ${trainingEnd?`jusqu’en ${trainingEnd}`:'sur la période historique'}. Observations BDIFF jusqu’au ${format(data.bdiff_end)}. `+
   (day.provenance?`Open-Meteo : météo modélisée, sélection automatique. ${mode==='archives'?(day.provenance.consolidated?'Archive quotidienne consolidée. ':'Archive provisoire, susceptible d’être révisée. '):''}Risque journalier estimé ; calibration avec cette source à vérifier.`:'Historique calculé à partir des stations Météo-France.');
  try{sessionStorage.setItem('risk-weather-date',day.key);sessionStorage.setItem('risk-weather-date-'+mode,day.key);}catch{}
  document.body.dataset.dailyComputeMs=(performance.now()-start).toFixed(2);
  document.body.dataset.dailyUpdates=String(Number(document.body.dataset.dailyUpdates||0)+1);
  clearTimeout(chartTimer);chartTimer=setTimeout(chart,120);
  }finally{
   // Keep the cue through the GPU redraw; a newer selection owns its own completion.
   if(switching)settleFrame=requestAnimationFrame(()=>{settleFrame=requestAnimationFrame(()=>{
    settleFrame=null;if(currentLoading===loadingVersion)stopLoading();
   });});
  }
 }
 function chart(){
  if(!data||!el('daily-series').open)return;
  const first=Math.max(0,index-45),last=Math.min(data.dates.length-1,index+45),items=[];
  let max=1;
  for(let i=first;i<=last;i++){
   const expected=data.expected[i],observed=data.dates[i]<=data.bdiff_end?(data.fires[data.dates[i]]||[]).length:null;
   max=Math.max(max,expected,observed||0);items.push({i,expected,observed});
  }
  const svg=el('daily-chart'),ns='http://www.w3.org/2000/svg',x=i=>55+900*(i-first)/Math.max(1,last-first),y=v=>205-175*v/max;
  svg.replaceChildren();
  const add=(tag,attributes,text)=>{const node=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attributes))node.setAttribute(k,v);if(text!==undefined)node.textContent=text;svg.append(node);return node;};
  for(let i=0;i<=4;i++){
   const v=max*i/4;add('line',{x1:55,x2:955,y1:y(v),y2:y(v),stroke:'#e1e8e3'});
   add('text',{x:45,y:y(v)+4,'text-anchor':'end',fill:'#60736c','font-size':11},number(v));
  }
  for(const [key,color] of [['expected','#216e55'],['observed','#d56a25']]){
   let path='',connected=false;
   for(const item of items){
    const v=item[key];if(v===null||!Number.isFinite(v)){connected=false;continue;}
    path+=`${connected?'L':'M'}${x(item.i).toFixed(2)},${y(v).toFixed(2)} `;connected=true;
   }
   add('path',{d:path,fill:'none',stroke:color,'stroke-width':2});
  }
  add('line',{x1:x(index),x2:x(index),y1:25,y2:205,stroke:'#61776b','stroke-dasharray':'3 4'});
  for(const i of [first,index,last])add('text',{x:x(i),y:228,'text-anchor':'middle',fill:'#60736c','font-size':11},format(data.dates[i]));
  svg.setAttribute('aria-label',`Risque et feux déclarés du ${format(data.dates[first])} au ${format(data.dates[last])}`);
 }
 el('daily-slider').oninput=()=>choose(available[Number(el('daily-slider').value)]);
 el('daily-date').onchange=()=>{
  const key=el('daily-date').value,position=data?.dates.indexOf(key)??-1;
  if(available.includes(position))choose(position);else if(data)labels();
 };
 el('daily-latest').onclick=()=>choose(available.at(-1));
 el('daily-series').ontoggle=chart;
 return {
  install(model){
   stopLoading();rangeCache=null;
   if(frame!==null)cancelAnimationFrame(frame);frame=null;clearTimeout(chartTimer);data=model;cache.clear();
   let previous;try{mode=sessionStorage.getItem('risk-weather-mode')||mode;previous=sessionStorage.getItem('risk-weather-date-'+mode)||sessionStorage.getItem('risk-weather-date');}catch{}
   if(!['archives','live','forecast'].includes(mode))mode='archives';
   el('time-controls').hidden=false;el('daily-series').hidden=false;
   configure(previous);status();
   labels();render();
  },
  setStatus(value){manifest=value?{...manifest,...value}:null;status();if(data&&displayedToday!==today()){configure(data.dates[index]);choose(index);}},
  clear(){stopLoading();rangeCache=null;if(frame!==null)cancelAnimationFrame(frame);frame=null;clearTimeout(chartTimer);data=null;cache.clear();el('time-controls').hidden=true;el('daily-series').hidden=true;}
 };
}
