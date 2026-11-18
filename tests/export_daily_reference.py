"""Export real weather and Python reference arrays inside the dashboard container."""
import base64
import gzip
import json
import sys
from pathlib import Path
import pandas as pd
import numpy as np
sys.path.insert(0, '/app')
from risk_map import cached_payload, file_signature, history_signature, RISK_DIR, BDIFF_DIR, meteo_signature, load_daily, daily_layer, cached_weather, observation_signature
folder = Path('/tmp/pyro-daily-reference'); folder.mkdir(exist_ok=True)
p = cached_payload(file_signature(RISK_DIR), history_signature(BDIFF_DIR))
d = load_daily(meteo_signature(), tuple(p['ids']), observation_signature())
weather = cached_weather(meteo_signature(), tuple(p['ids']), observation_signature())
(folder/'weather.bin').write_bytes(gzip.decompress(base64.b64decode(weather['payload'])))
references=[]
for key in ['2006-01-01','2010-02-21','2015-07-15','2022-01-15','2022-07-12','2022-08-10','2024-12-29','2025-08-13','2025-12-31','2026-11-16']:
    day, expected, count = daily_layer(d, pd.Timestamp(key))
    for name in ['values','fwi']:
        (folder/f'{key}-{name}.bin').write_bytes(base64.b64decode(day[name]))
    references.append({'key':key,'expected':expected,'fires':day['fires'],'count':count})
(folder/'reference.json').write_text(json.dumps(references))
print(f"Weather bundle: {weather['compressed_bytes']/1e6:.2f} MB compressed; {len(references)} national reference days exported")
