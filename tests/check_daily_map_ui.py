"""Exercise date controls with a small, isolated weather fixture; no production data is written."""
import base64
import gzip
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

sys.path.insert(0, '/app')
import risk_map as m

with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory)
    meta = {'modele_retenu': 'final',
            'modeles': {'final': {'coefficients': {'log_terrain': 1}}},
            'bdiff': {'fin': '2022-07-12'}, 'meteo': {'stations': 1},
            'apprentissage': {'validation': 'relecture historique de test',
                             'auc_test': {'terrain_et_sous_indices': {'auc': .9}, 'terrain_seul': {'auc': .8}}}}
    (folder / 'modele.json').write_text(json.dumps(meta))
    (folder / 'communes.json').write_text(json.dumps({'33001': ['station', 0]}))
    (folder / 'mailles.json').write_text(json.dumps({'a': ['33001', .25], 'b': ['33001', .75]}))
    np.savez(folder / 'meteo.npz', dates=['2022-07-12', '2022-07-13'], stations=['station'],
             z=np.array([[0.], [np.log(3.)]]), fwi=np.array([[10.], [20.]]))
    pd.DataFrame([{'code_insee': '33001', 'date': '2022-07-12', 'lon': -1., 'lat': 45.}]).to_csv(folder / 'feux_bdiff.csv.gz', index=False)
    payload = {'payload': base64.b64encode(gzip.compress(b'{}')).decode(), 'version': 'isolated-weather-fixture', 'ids': ['a', 'b']}
    with patch.object(m, 'METEO_DIR', folder), patch.object(m, 'cached_payload', return_value=payload):
        m.load_daily.clear()
        app = AppTest.from_file('/app/app.py', default_timeout=60).run()
        assert not app.exception, app.exception
        assert app.button(key='mode_risk_map') and app.button(key='mode_fire_history')
        assert len(app.date_input) == 1
        assert not any(x.label == 'Mode' for x in app.radio)
        first = json.loads(app.get('component_instance')[0].proto.json_args)
        assert first['daily']['key'] == '2022-07-13'
        assert first['version'] == payload['version']
        app.date_input[0].set_value(pd.Timestamp('2022-07-12').date()).run()
        assert not app.exception, app.exception
        second = json.loads(app.get('component_instance')[0].proto.json_args)
        assert second['daily']['key'] == '2022-07-12'
        assert second['version'] == first['version']
        assert second['payload'] == first['payload']
        assert second['daily']['values'] != first['daily']['values']
        assert len(second['daily']['fires']) == 1
        app.button(key='mode_fire_history').click().run()
        assert not app.exception, app.exception
        assert len(app.get('iframe')) == 1
        app.button(key='mode_risk_map').click().run()
        assert not app.exception, app.exception
        assert app.date_input[0].value == pd.Timestamp('2022-07-12').date()
print('Date controls, daily values, stable map payload, top navigation and fire history: OK')
