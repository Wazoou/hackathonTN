"""Daily file loading and date updates: run in the dashboard container."""
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
import risk_map as m


class DailyMapTests(unittest.TestCase):
    def test_alignment_missing_cells_date_updates_and_observation_cutoff(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            meta = {'modeles': {'final': {'coefficients': {'log_terrain': 1}}},
                    'modele_retenu': 'final', 'bdiff': {'fin': '2022-07-12'}}
            (folder / 'modele.json').write_text(json.dumps(meta))
            (folder / 'communes.json').write_text(json.dumps({'33001': ['station', 0]}))
            (folder / 'mailles.json').write_text(json.dumps({'a': ['33001', .25], 'b': ['33001', .75]}))
            np.savez(folder / 'meteo.npz', dates=['2022-07-12', '2022-07-13'],
                     stations=['station'], z=np.array([[0.], [np.log(3.)]]), fwi=np.array([[10.], [20.]]))
            pd.DataFrame([{'code_insee': '33001', 'date': '2022-07-12', 'lon': -1., 'lat': 45.}]).to_csv(folder / 'feux_bdiff.csv.gz', index=False)
            with patch.object(m, 'METEO_DIR', folder):
                m.load_daily.clear()
                d = m.load_daily(m.meteo_signature(), ('b', 'unmapped', 'a'))
            first, expected, fires = m.daily_layer(d, pd.Timestamp('2022-07-12'))
            values = np.frombuffer(base64.b64decode(first['values']), dtype=np.float32)
            np.testing.assert_allclose(values, [3750, -1, 1250])
            self.assertAlmostEqual(expected, .5)
            self.assertEqual(fires, 1)
            self.assertEqual(first['fires'][0][2], '33')
            second, expected, fires = m.daily_layer(d, pd.Timestamp('2022-07-13'))
            self.assertAlmostEqual(expected, .75)
            self.assertEqual(fires, 0)
            self.assertNotEqual(first['key'], second['key'])
            chart = m.series(d, pd.Timestamp('2022-07-12'))
            self.assertTrue(pd.isna(chart['Feux BDIFF déclarés'].iloc[-1]))
            self.assertEqual(chart['Feux BDIFF déclarés'].iloc[0], 1)


if __name__ == '__main__':
    unittest.main()
