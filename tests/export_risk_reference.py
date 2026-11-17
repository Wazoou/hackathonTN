"""Export Python references for test_risk_logic.cjs (run from the repository root)."""
import json,sys,base64,argparse
from pathlib import Path
import numpy as np
sys.path.insert(0,'dashboard')
from risk_data import combine
parser=argparse.ArgumentParser()
parser.add_argument('--out',type=Path,default=Path('/tmp/risk-validation'))
args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
from risk_payload import build_payload,file_signature
packed=build_payload(file_signature('risk-data'))
(args.out/'payload.json.gz').write_bytes(base64.b64decode(packed['payload']))
features=[]
for p in sorted(Path('risk-data').glob('*.geojson')):
 features.extend(json.loads(p.read_text())['features'])
props=[f['properties'] for f in features]
scenarios=[{'layer':'score','mode':'multiplicatif','weight':12},
 {'layer':'s_combustible','mode':'multiplicatif','weight':12},
 {'layer':'s_humain','mode':'multiplicatif','weight':12},
 *[{'layer':'score','mode':'additif','weight':w} for w in (0,12,20)]]
results=[]
for state in scenarios:
 vals=np.array([combine(p['s_combustible'],p['s_humain'],state['mode'],state['weight']/20) if state['layer']=='score' else p[state['layer']] for p in props])
 for dept in ['all']+sorted({p['dept'] for p in props}):
  ids=[i for i,p in enumerate(props) if dept=='all' or p['dept']==dept]
  a=vals[ids]; top=sorted(ids,key=lambda i:(-vals[i],i))[:15]
  results.append({'state':{**state,'dept':dept},'count':len(ids),'median':float(np.median(a)),
   'high':float(np.mean(a>=60)),'top':[props[i]['id'] for i in top]})
(args.out/'reference.json').write_text(json.dumps(results))
print(len(results),'références Python (97 périmètres × 6 configurations)')
