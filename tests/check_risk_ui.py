"""Server smoke test. Browser controls are tested in the persistent component.
Run: docker compose exec -T dashboard python - < tests/check_risk_ui.py
"""
import sys,time,json,base64,gzip
from streamlit.testing.v1 import AppTest
sys.path.insert(0,'/app')
from risk_map import cached_payload,RISK_DIR
from risk_payload import file_signature
start=time.perf_counter()
payload=cached_payload(file_signature(RISK_DIR))
data=json.loads(gzip.decompress(base64.b64decode(payload['payload'])))
assert len(data['features'])==payload['count']
assert all(len(s)==payload['count'] for s in data['scores'].values())
app=AppTest.from_file('/app/app.py',default_timeout=120).run()
app.sidebar.radio[0].set_value('Carte de risque').run()
assert not app.exception,app.exception
assert not app.error,app.error
assert len(app.get('component_instance'))==1
start=time.perf_counter();app.run();elapsed=time.perf_counter()-start
assert not app.exception,app.exception
print(f"Carte persistante : {payload['departments']} départements, {payload['count']} mailles, "
      f"{payload['compressed_bytes']/1e6:.2f} Mo compressés ; rerun chaud {elapsed:.3f}s")
