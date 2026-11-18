/* Lossless browser counterpart of risk_map.daily_layer; no map or UI dependencies. */
(function(root){
'use strict';
function unpack(buffer){
 const size=new DataView(buffer).getUint32(0,true);
 const header=JSON.parse(new TextDecoder().decode(new Uint8Array(buffer,4,size)));
 if(header.format!==1)throw new Error('Format météo incompatible');
 const types={'<f4':Float32Array,'<f8':Float64Array,'<i4':Int32Array};
 for(const [name,spec] of Object.entries(header.arrays)){
  const Type=types[spec.dtype];if(!Type)throw new Error('Type météo incompatible');
  header[name]=new Type(buffer,4+size+spec.offset,spec.length);
 }
 const days=header.dates.length,stations=header.stations;
 if(header.z.length!==days*stations||header.fwi.length!==header.z.length||
    header.cell_commune.length!==header.cell_share.length||
    header.commune_station.length!==header.commune_terrain.length||header.expected.length!==days)
  throw new Error('Dimensions météo incompatibles');
 return header;
}
function computeDay(data,index){
 if(!Number.isInteger(index)||index<0||index>=data.dates.length)throw new Error('Date météo hors limites');
 const probabilities=new Float64Array(data.commune_station.length),offset=index*data.stations;
 for(let c=0;c<probabilities.length;c++){
  const z=data.z[offset+data.commune_station[c]]+data.coefficient*data.commune_terrain[c];
  probabilities[c]=1/(1+Math.exp(-z));
 }
 const values=new Float32Array(data.cell_commune.length),fwi=new Float32Array(values.length);
 let expected=0;
 for(let i=0;i<values.length;i++){
  const c=data.cell_commune[i];
  const v=c>=0?1e4*probabilities[c]*data.cell_share[i]:NaN;
  values[i]=Number.isFinite(v)?v:-1;
  const w=c>=0?data.fwi[offset+data.commune_station[c]]:NaN;
  fwi[i]=Number.isFinite(w)?w:-1;
  if(values[i]>=0)expected+=values[i]/1e4;
 }
 const key=data.dates[index];
 return {key,label:key.split('-').reverse().join('/'),values,fwi,expected,
         fires:data.fires[key]||[],known:key<=data.bdiff_end,legend:data.legend,
         revision:data.revisions?.[index]||'history',provenance:data.provenance?.[index]||null};
}
function withOperational(history,operational){
 if(!operational)return history;
 if(operational.model_version!==history.model_version||
    JSON.stringify(operational.stations)!==JSON.stringify(history.station_ids))
  throw new Error('Le modèle LIVE et les stations ne correspondent pas à cet historique');
 const count=history.stations,byDate=new Map(history.dates.map((key,index)=>[key,{index,history:true}]));
 if(operational.dates.length!==operational.z.length||operational.dates.length!==operational.fwi.length||
    operational.dates.length!==operational.provenance.length)throw new Error('Dates LIVE incompatibles');
 for(let i=0;i<operational.dates.length;i++){
  const key=operational.dates[i];
  if(!/^\d{4}-\d{2}-\d{2}$/.test(key)||operational.z[i].length!==count||operational.fwi[i].length!==count||
     !operational.z[i].every(v=>typeof v==='number'&&Number.isFinite(v))||
     !operational.fwi[i].every(v=>typeof v==='number'&&Number.isFinite(v)))throw new Error('Météo LIVE incomplète');
  // Never overwrite the original station-observation history with modelled weather.
  if(key>history.dates.at(-1))byDate.set(key,{index:i,history:false});
 }
 const dates=[...byDate.keys()].sort(),z=new Float32Array(dates.length*count),fwi=new Float32Array(z.length),
  expected=new Float64Array(dates.length),provenance=[],revisions=[];
 for(let i=0;i<dates.length;i++){
  const row=byDate.get(dates[i]),j=row.index;
  if(row.history){
   z.set(history.z.subarray(j*count,(j+1)*count),i*count);fwi.set(history.fwi.subarray(j*count,(j+1)*count),i*count);
   expected[i]=history.expected[j];provenance.push(null);revisions.push('history');
  }else{
   z.set(operational.z[j],i*count);fwi.set(operational.fwi[j],i*count);
   let sum=0;for(let c=0;c<history.commune_station.length;c++)sum+=1/(1+Math.exp(-z[i*count+history.commune_station[c]]-history.coefficient*history.commune_terrain[c]));
   expected[i]=sum;provenance.push({source:operational.source,...operational.provenance[j]});
   revisions.push(operational.provenance[j].issued_at);
  }
 }
 return {...history,dates,z,fwi,expected,provenance,revisions};
}
const api={unpack,computeDay,withOperational};
if(typeof module==='object'&&module.exports)module.exports=api;else root.DailyLogic=api;
})(typeof window==='object'?window:globalThis);
