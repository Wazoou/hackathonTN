'use strict';
const $=id=>document.getElementById(id),fmt=n=>n.toLocaleString('fr-FR');
const months=['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];
const years=[...new Set(records.map(r=>r[0]))].sort((a,b)=>a-b),byYear=new Map(years.map(y=>[y,[]]));
records.forEach(r=>byYear.get(r[0]).push(r));
const state={year:years[years.length-1],month:12,period:'year',season:'all',cause:'all'};
const map=L.map('map',{scrollWheelZoom:true,preferCanvas:true}).setView([46.5,2.3],6);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',maxZoom:19}).addTo(map);
const renderer=L.canvas({padding:.3}),markers=new Map(),active=new Set(),cache=new Map();
let frame=null,updates=0;
map.on('moveend',()=>{document.body.dataset.view=JSON.stringify({center:map.getCenter(),zoom:map.getZoom()});});
function tooltip(p){
 const box=document.createElement('div');
 for(const [tag,text] of [['strong',p.locations],['div',`Incendies : ${fmt(p.incident_count)}`],['div',`Surface brûlée : ${fmt(p.burned_area_m2)} m²`],['div',`Position approximative : ${p.precision}`]]){const el=document.createElement(tag);el.textContent=text;box.append(el);}
 return box;
}
function labels(){
 $('year-value').textContent=state.year;$('month-value').textContent=`${months[state.month-1]} ${state.year}`;
 $('month').disabled=state.period!=='month';$('month-controls').classList.toggle('month-disabled',state.period!=='month');
}
function render(){
 frame=null;const start=performance.now(),key=JSON.stringify(state);labels();
 if(!cache.has(key)){if(cache.size>=64)cache.delete(cache.keys().next().value);cache.set(key,FireHistory.summarize(byYear.get(state.year)||[],state));}
 const result=cache.get(key),next=new Set(result.points.map(p=>p.key));
 for(const key of active)if(!next.has(key)){map.removeLayer(markers.get(key));active.delete(key);}
 for(const p of result.points){
  let marker=markers.get(p.key);
  if(!marker){marker=L.circleMarker([p.latitude,p.longitude],{renderer,radius:p.radius_px,color:'#7d0a14',weight:1,fillColor:'#cd232d',fillOpacity:.75});marker.bindTooltip(()=>tooltip(marker.fireData));markers.set(p.key,marker);}
  marker.fireData=p;marker.setRadius(p.radius_px);marker.closeTooltip();
  if(!active.has(p.key)){marker.addTo(map);active.add(p.key);}
 }
 $('count').textContent=`${fmt(result.count)} incendies correspondant à la sélection`;$('empty').hidden=result.count!==0;
 $('approximate').textContent=result.approximate?`${fmt(result.approximate)} incendies positionnés au centre de leur département faute de commune localisée.`:'';
 $('unmapped').textContent=result.unmapped?`${fmt(result.unmapped)} incendies sans coordonnées ne sont pas représentés sur la carte.`:'';
 document.body.dataset.year=state.year;document.body.dataset.count=result.count;document.body.dataset.markers=next.size;
 document.body.dataset.updateMs=(performance.now()-start).toFixed(2);document.body.dataset.updates=++updates;
 requestAnimationFrame(()=>requestAnimationFrame(()=>{document.body.dataset.frameMs=(performance.now()-start).toFixed(2);}));
}
function schedule(){labels();if(frame===null)frame=requestAnimationFrame(render);}
$('coverage').textContent=`Archives disponibles : ${years[0]}–${years[years.length-1]} · BDIFF`;
$('year').min=years[0];$('year').max=years[years.length-1];$('year').value=state.year;$('year').disabled=years.length===1;
$('first-year').textContent=years[0];$('last-year').textContent=years[years.length-1];
for(const id of ['year','month'])$(id).oninput=()=>{state[id]=Number($(id).value);schedule();};
for(const id of ['period','season','cause'])$(id).onchange=()=>{state[id]=$(id).value;schedule();};
new ResizeObserver(()=>map.invalidateSize({pan:false})).observe($('map'));
document.body.dataset.loadCount='1';render();document.body.dataset.ready='true';
