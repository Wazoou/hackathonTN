/* Pure functions, independent of the map and Streamlit. */
(function(root){
'use strict';
const CLASSES=['Très faible','Faible','Modéré','Élevé','Très élevé'];
const BOUNDS={p_feu:[0,2,5,10,20,40],p_jour:[0,0.5,2,5,15,50]}; // %/an ; pour 10 000 par jour
function scale(value,layer){
 const b=BOUNDS[layer];
 if(!b)return value;
 for(let i=0;i<5;i++)if(value<b[i+1])return 20*i+20*(value-b[i])/(b[i+1]-b[i]);
 return 100;
}
function riskClass(value,layer){return CLASSES[Math.min(4,Math.max(0,Math.floor(scale(value,layer)/20)))];}
function scoreKey(state){return state.mode==='multiplicatif'?'multiplicatif':`additif:${state.weight}`;}
function value(feature,state,scores){return state.layer==='score'?scores[scoreKey(state)][feature._index]/10:feature.properties[state.layer];}
function summary(features,state,scores){
 const values=[],top=[];
 let high=0,total=0;
 for(let i=0;i<features.length;i++){
  const f=features[i],v=value(f,state,scores);
  if(v==null||!Number.isFinite(v)||v<0)continue;
  values.push(v);total+=v;
  if(scale(v,state.layer)>=60)high++;
  // Keep only the best 15 instead of sorting every feature a second time.
  if(top.length<15||v>top[top.length-1].v){
   let j=top.length;while(j>0&&(v>top[j-1].v||(v===top[j-1].v&&f._index<top[j-1].f._index)))j--;
   top.splice(j,0,{f,v});if(top.length>15)top.pop();
  }
 }
 const n=values.length,sorted=Float64Array.from(values).sort();
 const median=n?(sorted[Math.floor((n-1)/2)]+sorted[Math.floor(n/2)])/2:null;
 return {count:n,total_count:features.length,mean:n?total/n:null,median,high:n?high/n:null,top:top.map(t=>t.f)};
}
function escape(value){return String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
const api={scale,riskClass,scoreKey,value,summary,escape};
if(typeof module==='object'&&module.exports)module.exports=api;else root.RiskLogic=api;
})(typeof window==='object'?window:globalThis);
