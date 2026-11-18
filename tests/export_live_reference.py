"""Append the actual operational collection to the national Python/browser reference test."""
exec(compile(open('/tmp/export_daily_reference.py').read(), '/tmp/export_daily_reference.py', 'exec'))
import requests
manifest = requests.get('http://localhost:8501/app/static/weather/current.json', timeout=20).json()
bundle = requests.get('http://localhost:8501/app/static/weather/'+manifest['bundle'], timeout=20).json()
operational = json.loads(gzip.decompress(base64.b64decode(bundle['payload'])))
(folder/'operational.json').write_text(json.dumps(operational))
d = {**d, 'dates': pd.DatetimeIndex(operational['dates']),
     'z': np.asarray(operational['z'], dtype=np.float32), 'fwi': np.asarray(operational['fwi'], dtype=np.float32)}
references = []
for key in operational['dates']:
    day, expected, count = daily_layer(d, pd.Timestamp(key))
    for name in ['values', 'fwi']:
        (folder/f'{key}-{name}.bin').write_bytes(base64.b64decode(day[name]))
    references.append({'key': key, 'expected': expected, 'fires': day['fires'], 'count': count})
(folder/'live-reference.json').write_text(json.dumps(references))
print(f'{len(references)} operational national days exported for Python/browser comparison')
