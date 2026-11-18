/* Calendar, slider, observed fires and comparison chart stay entirely in this iframe. */
function DailyControls({onDay}){
 const el=id=>document.getElementById(id),format=key=>key.split('-').reverse().join('/');
 const number=n=>n.toLocaleString('fr-FR',{minimumFractionDigits:1,maximumFractionDigits:1});
 let data=null,index=0,requested=0,frame=null,chartTimer=null,cache=new Map();
 function labels(){
  const key=data.dates[requested];el('daily-date').value=key;el('daily-slider').value=requested;el('daily-date-label').textContent=format(key);
 }
 function choose(next){
  if(!data)return;
  requested=Math.max(0,Math.min(data.dates.length-1,Math.round(next)));labels();
  if(frame===null)frame=requestAnimationFrame(render);
 }
 function render(){
  frame=null;index=requested;const start=performance.now();
  if(!cache.has(index)){
   if(cache.size>=12)cache.delete(cache.keys().next().value);
   cache.set(index,DailyLogic.computeDay(data,index));
  }
  const day=cache.get(index);
  onDay(day);
  try{sessionStorage.setItem('risk-weather-date',day.key);}catch{}
  document.body.dataset.dailyComputeMs=(performance.now()-start).toFixed(2);
  document.body.dataset.dailyUpdates=String(Number(document.body.dataset.dailyUpdates||0)+1);
  clearTimeout(chartTimer);chartTimer=setTimeout(chart,120);
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
 el('daily-slider').oninput=()=>choose(Number(el('daily-slider').value));
 el('daily-date').onchange=()=>{
  const key=el('daily-date').value,position=data?.dates.indexOf(key)??-1;
  if(position>=0)choose(position);else if(data)labels();
 };
 el('daily-latest').onclick=()=>choose(data.dates.length-1);
 el('daily-series').ontoggle=chart;
 return {
  install(model){
   if(frame!==null)cancelAnimationFrame(frame);frame=null;clearTimeout(chartTimer);data=model;cache.clear();
   let previous;try{previous=sessionStorage.getItem('risk-weather-date');}catch{}
   const position=data.dates.indexOf(previous);index=position>=0?position:data.dates.length-1;requested=index;
   el('time-controls').hidden=false;el('daily-series').hidden=false;
   el('daily-slider').max=data.dates.length-1;el('daily-slider').disabled=data.dates.length===1;
   el('daily-date').min=data.dates[0];el('daily-date').max=data.dates[data.dates.length-1];
   el('daily-first').textContent=format(data.dates[0]);el('daily-last').textContent=format(data.dates[data.dates.length-1]);
   const meta=data.meta,auc=meta.apprentissage?.auc_test;
   const trainingEnd=meta.bdiff?.fin?.slice(0,4);
   el('daily-validation').textContent=`${meta.meteo.stations} stations Météo-France · indice forêt-météo de Van Wagner (1987). Modèle entraîné ${trainingEnd?`jusqu’en ${trainingEnd}`:'sur la période historique'}. Observations BDIFF jusqu’au ${format(data.bdiff_end)}. Relecture historique.`+
    (auc?` AUC rapportée : ${auc.terrain_et_sous_indices.auc} avec météo, ${auc.terrain_seul.auc} avec terrain seul.`:'');
   labels();render();
  },
  clear(){if(frame!==null)cancelAnimationFrame(frame);frame=null;clearTimeout(chartTimer);data=null;cache.clear();el('time-controls').hidden=true;el('daily-series').hidden=true;}
 };
}
