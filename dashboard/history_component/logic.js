/* Rows: year, month, latitude, longitude, precision, commune, surface m², cause. */
(function(root){
'use strict';
const seasons={Hiver:[12,1,2],Printemps:[3,4,5],'Été':[6,7,8],Automne:[9,10,11]};
function summarize(rows,state){
 const groups=new Map();let count=0,unmapped=0,approximate=0;
 for(const r of rows){
  if(r[0]!==state.year||(state.period==='month'&&r[1]!==state.month))continue;
  if(state.season!=='all'&&!seasons[state.season].includes(r[1]))continue;
  if(state.cause!=='all'&&r[7]!==state.cause)continue;
  count++;
  if(r[2]===null||r[3]===null){unmapped++;continue;}
  if(r[4]==='département')approximate++;
  const key=JSON.stringify([r[2],r[3],r[4]]);
  if(!groups.has(key))groups.set(key,{key,latitude:r[2],longitude:r[3],precision:r[4],incident_count:0,burned_area_m2:0,names:new Set()});
  const g=groups.get(key);g.incident_count++;g.burned_area_m2+=r[6];if(r[5]!==null)g.names.add(r[5]);
 }
 const points=[...groups.values()].map(g=>({...g,names:undefined,locations:[...g.names].sort().join(', '),radius_px:Math.min(20,Math.max(4,Math.sqrt(g.burned_area_m2/Math.PI)*.15))}));
 return {count,unmapped,approximate,points};
}
if(typeof module==='object'&&module.exports)module.exports={summarize};else root.FireHistory={summarize};
})(typeof window==='object'?window:globalThis);
