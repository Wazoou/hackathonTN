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
         fires:data.fires[key]||[],known:key<=data.bdiff_end,legend:data.legend};
}
const api={unpack,computeDay};
if(typeof module==='object'&&module.exports)module.exports=api;else root.DailyLogic=api;
})(typeof window==='object'?window:globalThis);
